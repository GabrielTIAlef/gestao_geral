"""Regressões ETL com HTTP e navegador simulados; SQL local somente em SQLite."""
from datetime import date
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
import requests
from sqlalchemy import create_engine, text

from etl_support import ETLError, dates, numeric_key, read_snapshot_pair, stage_csv, publish_files
import database
import pipeline
from extracao import base_notion as notion
from extracao import gestta_relatorios as gestta
from transformacao import PBI_OS as bi
from transformacao import CS
from automacao import powerbi_refresh as powerbi


def response(payload, status=200):
    result = Mock(status_code=status)
    result.json.return_value = payload
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError("synthetic failure")
    return result


def gestta_frame():
    return pd.DataFrame([{
        "id": "synthetic-task", "name": "Etapa demonstrativa 01", "status": "OPEN",
        "owner.name": "Pessoa Fictícia", "type": "SERVICE_ORDER", "subtype": "TEMPLATE",
        "created_at": "2026-01-02T10:00:00-03:00", "customer.code": 1,
        "customer.cnpj": "00123456000199", "customer.name": "Cliente Fictício",
        "customer.active": True, "notify_customer": False,
    }])


def notion_frame():
    values = {name: None for name in notion.VISIBLE_COLUMNS}
    values.update({"Código Cliente": 1, "Gestão de Clientes": "Equipe Demo (A)",
                   "CNPJ": "00123456000199", "Primeira Competência": date(2026, 1, 1)})
    return pd.DataFrame([values])


def notion_page():
    props = {name: {"type": "rich_text", "rich_text": []} for name in notion.VISIBLE_COLUMNS}
    props["Código Cliente"] = {"type": "number", "number": 1}
    props["CNPJ"] = {"type": "rich_text", "rich_text": [{"plain_text": "00123456000199"}]}
    props["Gestão de Clientes"] = {"type": "rich_text", "rich_text": [{"plain_text": "Equipe Demo"}]}
    props["Primeira Competência"] = {"type": "date", "date": {"start": "2026-01-01"}}
    return {"id": "synthetic-page", "properties": props}


class IsolatedTest(unittest.TestCase):
    def setUp(self):
        self.network = patch("requests.sessions.Session.request",
                             side_effect=AssertionError("Real HTTP is forbidden in tests"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)


class TransformationTests(IsolatedTest):
    def test_cnpj_text_and_zeros_preserved(self):
        frame = bi.transformar_gestta(gestta_frame())
        self.assertEqual(frame.loc[0, "cliente__cnpj"], "00123456000199")
        self.assertEqual(frame.loc[0, "cliente__código"], 1)
        self.assertEqual(frame.loc[0, "cliente__ativo"], "Sim")
        self.assertEqual(frame.loc[0, "tarefa__notifica_cliente"], "Não")

    def test_numeric_cnpj_rejected_instead_of_guessing_zeroes(self):
        frame = gestta_frame()
        frame["customer.cnpj"] = 123456000199
        with self.assertRaises(ETLError):
            bi.transformar_gestta(frame)

    def test_notion_csv_roundtrip_preserves_cnpj(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notion.csv"
            publish_files([stage_csv(notion_frame(), path)])
            frame = pd.read_csv(path, dtype="string", keep_default_na=False)
            self.assertEqual(bi.transformar_notion(frame).loc[0, "cnpj"], "00123456000199")

    def test_duplicate_notion_key_rejected(self):
        with self.assertRaises(ETLError):
            bi.transformar_notion(pd.concat([notion_frame(), notion_frame()]))

    def test_duplicate_task_rejected(self):
        with self.assertRaises(ETLError):
            bi.transformar_gestta(pd.concat([gestta_frame(), gestta_frame()]))

    def test_missing_columns_rejected(self):
        with self.assertRaises(ETLError):
            bi.transformar_gestta(pd.DataFrame({"id": ["synthetic"]}))

    def test_invalid_numeric_key_rejected(self):
        with self.assertRaises(ETLError):
            numeric_key(pd.Series(["bad"]), "synthetic")

    def test_invalid_date_rejected(self):
        with self.assertRaises(ETLError):
            dates(pd.Series(["not-a-date"]), "synthetic")

    def test_local_calendar_date_preserved(self):
        self.assertEqual(dates(pd.Series(["2026-01-01T00:30:00+10:00"]), "synthetic")[0],
                         date(2026, 1, 1))

    def test_left_join_preserves_unmatched_task(self):
        g = bi.transformar_gestta(gestta_frame())
        n = notion_frame()
        n["Código Cliente"] = 2
        bi.validate_join(g, bi.transformar_notion(n))

    def test_business_filters_remain_compatible(self):
        frame = bi.transformar_gestta(gestta_frame())
        self.assertEqual(bi.cs_targets(frame)["tarefa__id"].tolist(), ["synthetic-task"])
        self.assertEqual(CS.checklist, [f"Etapa demonstrativa {i:02d}" for i in range(1, 13)])
        self.assertEqual(len(gestta.periods(2026)), 12)


class ExtractionTests(IsolatedTest):
    def test_gestta_failure_stops_periods(self):
        http = Mock()
        http.post.side_effect = [response(gestta_frame().to_dict("records")),
                                 requests.Timeout("synthetic")]
        with self.assertRaises(ETLError):
            gestta.collect(http=http, token="synthetic", requested_periods=gestta.periods(2026))
        self.assertEqual(http.post.call_count, 2)

    def test_gestta_malformed_response_rejected(self):
        http = Mock()
        http.post.return_value = response({})
        with self.assertRaises(ETLError):
            gestta.collect(http=http, token="synthetic", requested_periods=[("a", "b")])

    def test_empty_period_valid_but_total_empty_rejected(self):
        http = Mock()
        http.post.side_effect = [response([]), response(gestta_frame().to_dict("records"))]
        self.assertEqual(len(gestta.collect(http=http, token="synthetic",
                                          requested_periods=[("a", "b"), ("c", "d")])), 1)
        http.post.side_effect = None
        http.post.return_value = response([])
        with self.assertRaises(ETLError):
            gestta.collect(http=http, token="synthetic", requested_periods=[("a", "b")])

    def client(self, http):
        return notion.NotionClient(token="synthetic", database_id="synthetic", http=http)

    def test_missing_notion_contract_rejected(self):
        http = Mock()
        http.post.return_value = response({})
        with self.assertRaises(ETLError):
            self.client(http).pages()

    def test_notion_missing_cursor_rejected(self):
        http = Mock()
        http.post.return_value = response({"results": [], "has_more": True})
        with self.assertRaises(ETLError):
            self.client(http).pages()

    def test_notion_repeated_cursor_rejected(self):
        http = Mock()
        http.post.return_value = response({"results": [], "has_more": True, "next_cursor": "same"})
        with self.assertRaises(ETLError):
            self.client(http).pages()
        self.assertEqual(http.post.call_count, 2)

    def test_notion_two_page_response(self):
        http = Mock()
        http.post.side_effect = [response({"results": [notion_page()], "has_more": True,
                                          "next_cursor": "next"}),
                                 response({"results": [], "has_more": False})]
        self.assertEqual(len(self.client(http).pages()), 1)
        self.assertEqual(http.post.call_args_list[1].kwargs["json"], {"start_cursor": "next"})

    def test_notion_empty_does_not_publish(self):
        http = Mock()
        http.post.return_value = response({"results": [], "has_more": False})
        with self.assertRaises(ETLError):
            notion.collect(client=self.client(http))

    def test_notion_normalizes_text_identifiers(self):
        http = Mock()
        frame = notion.normalize_visible_only([notion_page()], client=self.client(http))
        self.assertEqual(frame.loc[0, "CNPJ"], "00123456000199")
        self.assertEqual(frame.loc[0, "Primeira Competência"], date(2026, 1, 1))

    def test_failed_related_page_cannot_turn_into_empty_text(self):
        http = Mock()
        http.get.return_value = response({}, 403)
        with self.assertRaises(ETLError):
            self.client(http).title("synthetic")

    def test_paginates_relation_properties_and_titles(self):
        http = Mock()
        http.get.side_effect = [
            response({"results": [{"relation": {"id": "related-1"}}],
                      "has_more": True, "next_cursor": "next"}),
            response({"results": [{"relation": {"id": "related-2"}}], "has_more": False}),
            response({"properties": {"name": {"type": "title", "title": [{"plain_text": "Demo A"}]}}}),
            response({"properties": {"name": {"type": "title", "title": [{"plain_text": "Demo B"}]}}}),
        ]
        value = self.client(http).relation("page", {"id": "property", "has_more": True, "relation": []})
        self.assertEqual(value, "Demo A; Demo B")
        self.assertEqual(http.get.call_count, 4)

    def test_checklist_failure_blocks_partial_publication(self):
        targets = pd.DataFrame({"tarefa__nome": ["Etapa demonstrativa 01"] * 2,
                                "tarefa__id": ["synthetic-1", "synthetic-2"]})
        http = Mock()
        http.get.side_effect = [
            response({"customer_task_steps": [{"name": "Demo", "order": 1, "done": True}]}),
            requests.Timeout("synthetic"),
        ]
        with self.assertRaises(ETLError):
            CS.collect(targets, http=http, token="synthetic")

    def test_checklist_string_false_is_not_accepted_as_true(self):
        http = Mock()
        http.get.return_value = response({"customer_task_steps": [
            {"name": "Demo", "order": 1, "done": "false"}]})
        targets = pd.DataFrame({"tarefa__nome": ["Etapa demonstrativa 01"],
                                "tarefa__id": ["synthetic"]})
        with self.assertRaises(ETLError):
            CS.collect(targets, http=http, token="synthetic")


class DatabaseTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        database.publish_tables(self.engine, {
            "gestta_relatorios": pd.DataFrame({"id": ["old"]}),
            "notion_dados": pd.DataFrame({"id": ["old"]})})

    def rows(self, table):
        with self.engine.connect() as conn:
            return conn.execute(text(f"SELECT id FROM {table}")).scalars().all()

    def test_empty_frame_cannot_clear_table(self):
        with self.assertRaises(ETLError):
            database.publish_tables(self.engine, {"gestta_relatorios": pd.DataFrame(columns=["id"])})
        self.assertEqual(self.rows("gestta_relatorios"), ["old"])

    def test_failure_in_second_table_rolls_back_first(self):
        with self.assertRaises(ETLError):
            database.publish_tables(self.engine, {
                "gestta_relatorios": pd.DataFrame({"id": ["new"]}),
                "notion_dados": pd.DataFrame({"different_schema": ["bad"]})})
        self.assertEqual(self.rows("gestta_relatorios"), ["old"])
        self.assertEqual(self.rows("notion_dados"), ["old"])

    def test_failure_in_view_statement_rolls_back_tables(self):
        with self.assertRaises(Exception):
            database.publish_tables(self.engine, {
                "gestta_relatorios": pd.DataFrame({"id": ["new"]})},
                view_sql=["SELECT * FROM deliberately_missing_table"])
        self.assertEqual(self.rows("gestta_relatorios"), ["old"])

    def test_repeated_load_has_no_duplicates(self):
        frame = pd.DataFrame({"id": ["new"]})
        for _ in range(2):
            database.publish_tables(self.engine, {"gestta_relatorios": frame})
        self.assertEqual(self.rows("gestta_relatorios"), ["new"])

    def test_numerical_cnpj_schema_requires_explicit_migration(self):
        with self.engine.begin() as conn:
            pd.DataFrame({"cnpj": [123]}).to_sql("cs_check", conn, index=False)
        with self.assertRaises(ETLError):
            database.publish_tables(self.engine, {"cs_check": pd.DataFrame({"cnpj": ["00123"]})})

    def test_external_view_survives_data_refresh(self):
        with self.engine.begin() as conn:
            conn.execute(text("CREATE VIEW external_consumer AS SELECT id FROM gestta_relatorios"))
        database.publish_tables(self.engine, {"gestta_relatorios": pd.DataFrame({"id": ["new"]})})
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT id FROM external_consumer")).scalar_one(), "new")


class PipelineTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.paths = {key: Path(self.directory.name) / name for key, name in (
            ("gestta", "gestta.csv"), ("notion", "notion.csv"), ("json", "gestta.json"),
            ("excel", "output.xlsx"), ("manifest", "manifest.json"))}
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)

    def run_pipeline(self, **kwargs):
        options = dict(engine=self.engine, paths=self.paths, gestta_collector=gestta_frame,
                       notion_collector=notion_frame, publisher=Mock())
        options.update(kwargs)
        return pipeline.run(**options)

    def test_synthetic_run_publishes_matching_snapshot_and_excel(self):
        publisher = Mock()
        manifest = self.run_pipeline(publisher=publisher)
        self.assertEqual(manifest["status"], "complete")
        raw_g, raw_n = read_snapshot_pair(self.paths["gestta"], self.paths["notion"], self.paths["manifest"])
        self.assertEqual(raw_g.loc[0, "customer.cnpj"], "00123456000199")
        self.assertEqual(raw_n.loc[0, "CNPJ"], "00123456000199")
        self.assertEqual(len(pd.read_excel(self.paths["excel"])), 1)
        self.assertEqual(set(publisher.call_args.args[1]),
                         {"notion_folha", "gestta_relatorios", "notion_dados"})
        self.assertEqual(len(publisher.call_args.kwargs["view_sql"]), 4)

    def test_source_failure_preserves_existing_files_and_stops_publisher(self):
        for path in self.paths.values():
            path.write_bytes(b"old-snapshot")
        publisher = Mock()
        with self.assertRaises(ETLError):
            self.run_pipeline(gestta_collector=Mock(side_effect=ETLError("synthetic")), publisher=publisher)
        publisher.assert_not_called()
        self.assertTrue(all(path.read_bytes() == b"old-snapshot" for path in self.paths.values()))

    def test_database_failure_preserves_files_and_cleans_temporaries(self):
        for path in self.paths.values():
            path.write_bytes(b"old-snapshot")
        with self.assertRaises(ETLError):
            self.run_pipeline(publisher=Mock(side_effect=RuntimeError("synthetic")))
        self.assertTrue(all(path.read_bytes() == b"old-snapshot" for path in self.paths.values()))
        self.assertEqual(set(Path(self.directory.name).iterdir()), set(self.paths.values()))

    def test_snapshot_tampering_rejected(self):
        self.run_pipeline()
        self.paths["notion"].write_bytes(b"unrelated-snapshot")
        with self.assertRaises(ETLError):
            read_snapshot_pair(self.paths["gestta"], self.paths["notion"], self.paths["manifest"])

    def test_checklist_failure_occurs_before_any_publication(self):
        publisher = Mock()
        with self.assertRaises(ETLError):
            self.run_pipeline(include_checklists=True, checklist_collector=Mock(
                side_effect=ETLError("synthetic")), publisher=publisher)
        publisher.assert_not_called()
        self.assertFalse(any(path.exists() for path in self.paths.values()))

    def test_pipeline_does_not_refresh_after_failure(self):
        with patch("automacao.RPA_Gestao_Atividades.run") as refresh:
            with self.assertRaises(ETLError):
                self.run_pipeline(refresh_powerbi=True, publisher=Mock(side_effect=RuntimeError("synthetic")))
            refresh.assert_not_called()

    def test_successful_pipeline_refreshes_both_panels(self):
        with patch("automacao.RPA_Gestao_Atividades.run") as first, patch(
                "automacao.RPA_Gestao_Supervisores.run") as second:
            self.run_pipeline(refresh_powerbi=True)
            first.assert_called_once()
            second.assert_called_once()


class PowerBITests(IsolatedTest):
    def run_refresh(self, directory, driver, **kwargs):
        return powerbi.run("SYNTHETIC", dataset="Demo", profile="Default", directory=directory,
                           driver_factory=Mock(return_value=driver), wait_factory=Mock(),
                           action_factory=Mock(), **kwargs)

    def test_dataset_absent_raises_and_closes_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = Mock()
            driver.find_elements.return_value = []
            with self.assertRaises(ETLError):
                self.run_refresh(directory, driver)
            driver.quit.assert_called_once()
            self.assertFalse((Path(directory) / ".gestao_refresh.lock").exists())

    def test_timeout_raises_and_closes_driver(self):
        from selenium.common.exceptions import TimeoutException
        with tempfile.TemporaryDirectory() as directory:
            driver = Mock()
            factory = Mock(side_effect=TimeoutException("synthetic"))
            with self.assertRaises(ETLError):
                powerbi.run("SYNTHETIC", dataset="Demo", profile="Default", directory=directory,
                            driver_factory=Mock(return_value=driver), wait_factory=factory)
            driver.quit.assert_called_once()

    def test_browser_lock_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "SingletonLock"
            marker.write_text("synthetic", encoding="utf-8")
            with self.assertRaises(ETLError):
                with powerbi.profile_lock(directory):
                    self.fail("must not acquire occupied profile")
            self.assertTrue(marker.exists())

    def test_only_one_profile_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            with powerbi.profile_lock(directory):
                with self.assertRaises(ETLError):
                    with powerbi.profile_lock(directory):
                        self.fail("must not overlap")

    def test_refresh_is_requested_not_reported_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = Mock()
            block = Mock()
            block.find_element.return_value.get_attribute.return_value = "Demo"
            driver.find_elements.return_value = [block]
            result = self.run_refresh(directory, driver)
            self.assertEqual(result, {"status": "requested", "completion_verified": False})
            driver.quit.assert_called_once()


class ImportTests(IsolatedTest):
    def test_scripts_import_without_accounts_browser_or_network(self):
        modules = ["extracao.gestta_relatorios", "extracao.base_notion", "transformacao.CS",
                   "transformacao.PBI_OS", "automacao.RPA_Gestao_Atividades",
                   "automacao.RPA_Gestao_Supervisores", "pipeline"]
        with patch("sqlalchemy.create_engine", side_effect=AssertionError("DB connection at import")), patch(
                "selenium.webdriver.Chrome", side_effect=AssertionError("Chrome at import")):
            for name in modules:
                importlib.reload(importlib.import_module(name))



class AdditionalRegressionTests(IsolatedTest):
    def test_http_status_is_available_without_response_body_or_url(self):
        from etl_support import request_json
        http = Mock()
        http.get.return_value = response({"secret": "DO_NOT_DISCLOSE"}, 403)
        with self.assertRaises(ETLError) as result:
            request_json("get", "https://example.invalid/DO_NOT_DISCLOSE", http=http)
        self.assertIn("403", str(result.exception))
        self.assertNotIn("DO_NOT_DISCLOSE", str(result.exception))

    def test_boolean_cannot_become_numeric_key(self):
        with self.assertRaises(ETLError):
            numeric_key(pd.Series([True]), "synthetic")

    def test_property_identifier_is_encoded_only_once(self):
        http = Mock()
        http.get.return_value = response({"results": [], "has_more": False})
        client = notion.NotionClient(token="synthetic", database_id="synthetic", http=http)
        self.assertEqual(client.relation("page", {"id": "a%3Ab", "has_more": True}), "")
        self.assertTrue(http.get.call_args.args[0].endswith("/properties/a%3Ab"))

    def test_excel_staging_failure_preserves_previous_destination(self):
        from etl_support import stage_file
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.xlsx"
            path.write_bytes(b"old-file")
            def failed_writer(temporary):
                temporary.write_bytes(b"incomplete")
                raise OSError("synthetic")
            with self.assertRaises(OSError):
                stage_file(path, failed_writer)
            self.assertEqual(path.read_bytes(), b"old-file")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_no_refresh_after_file_publication_failure_and_database_state_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = {key: Path(directory) / filename for key, filename in (
                ("gestta", "g.csv"), ("notion", "n.csv"), ("json", "g.json"),
                ("excel", "out.xlsx"), ("manifest", "manifest.json"))}
            engine = create_engine("sqlite://")
            try:
                with patch("pipeline.publish_files", side_effect=OSError("hidden-secret")), patch(
                        "automacao.RPA_Gestao_Atividades.run") as refresh:
                    with self.assertRaises(ETLError) as result:
                        pipeline.run(engine=engine, paths=paths, gestta_collector=gestta_frame,
                                     notion_collector=notion_frame, publisher=Mock(), refresh_powerbi=True)
                    self.assertIn("banco_confirmado=True", str(result.exception))
                    self.assertNotIn("hidden-secret", str(result.exception))
                    refresh.assert_not_called()
                    self.assertFalse(paths["manifest"].exists())
            finally:
                engine.dispose()

    def test_first_refresh_failure_stops_second(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = {key: Path(directory) / filename for key, filename in (
                ("gestta", "g.csv"), ("notion", "n.csv"), ("json", "g.json"),
                ("excel", "out.xlsx"), ("manifest", "manifest.json"))}
            engine = create_engine("sqlite://")
            try:
                with patch("automacao.RPA_Gestao_Atividades.run", side_effect=ETLError("synthetic")), patch(
                        "automacao.RPA_Gestao_Supervisores.run") as second:
                    with self.assertRaises(ETLError):
                        pipeline.run(engine=engine, paths=paths, gestta_collector=gestta_frame,
                                     notion_collector=notion_frame, publisher=Mock(), refresh_powerbi=True)
                    second.assert_not_called()
            finally:
                engine.dispose()


class FinalContractTests(IsolatedTest):
    def test_overlapping_column_names_cannot_create_ambiguous_view(self):
        g = bi.transformar_gestta(gestta_frame())
        n = bi.transformar_notion(notion_frame())
        g["cnpj"] = "synthetic"
        with self.assertRaises(ETLError):
            bi.validate_join(g, n)

    def test_explicit_gestta_pagination_cannot_be_ignored(self):
        http = Mock()
        http.post.return_value = response({"data": gestta_frame().to_dict("records"), "has_more": True})
        with self.assertRaises(ETLError):
            gestta.collect(http=http, token="synthetic", requested_periods=[("a", "b")])

    def test_rpa_script_returns_nonzero_when_shared_refresh_fails(self):
        script = (
            "import runpy,sys; sys.path.insert(0,'src'); "
            "import automacao.powerbi_refresh as p; "
            "p.run=lambda *a: (_ for _ in ()).throw(RuntimeError('synthetic')); "
            "runpy.run_path('src/automacao/RPA_Gestao_Atividades.py',run_name='__main__')"
        )
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                                capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)


class LocalPipelineDatabaseTests(IsolatedTest):
    def test_pipeline_loads_real_local_tables_and_reprocesses_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = {key: Path(directory) / filename for key, filename in (
                ("gestta", "g.csv"), ("notion", "n.csv"), ("json", "g.json"),
                ("excel", "out.xlsx"), ("manifest", "manifest.json"))}
            engine = create_engine("sqlite://")
            # SQLite não oferece CREATE OR REPLACE VIEW: apenas adaptar a view do join.
            # Este teste não valida DDL específico PostgreSQL.
            def sqlite_publisher(engine, tables, *, view_sql):
                local_view = view_sql[0].replace("CREATE OR REPLACE VIEW", "CREATE VIEW IF NOT EXISTS")
                database.publish_tables(engine, tables, view_sql=[local_view])
            try:
                for _ in range(2):
                    pipeline.run(engine=engine, paths=paths, gestta_collector=gestta_frame,
                                 notion_collector=notion_frame, publisher=sqlite_publisher)
                with engine.connect() as conn:
                    self.assertEqual(conn.execute(text(
                        'SELECT cliente__cnpj FROM gestta_relatorios')).scalar_one(), "00123456000199")
                    self.assertEqual(conn.execute(text(
                        'SELECT cnpj FROM notion_dados')).scalar_one(), "00123456000199")
                    self.assertEqual(conn.execute(text('SELECT count(*) FROM bi_final')).scalar_one(), 1)
                    self.assertEqual(conn.execute(text('SELECT count(*) FROM notion_folha')).scalar_one(), 1)
            finally:
                engine.dispose()

if __name__ == "__main__":
    unittest.main()

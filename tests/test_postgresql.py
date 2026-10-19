"""Integração real somente em cluster criado por scripts/validate_postgres.py."""
from contextlib import contextmanager
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import pandas as pd
import requests
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

import database
from etl_support import ETLError, digest
from examples.synthetic import checklist_data, gestta_data, notion_data
from extracao.base_notion import NotionClient, collect as collect_notion
from extracao.gestta_relatorios import collect as collect_gestta
from pipeline import run
from transformacao import CS

ADMIN_URL = os.getenv("GESTAO_TEST_PG_ADMIN_URL")
ISOLATED = os.getenv("GESTAO_TEST_PG_ISOLATED") == "1"


def response(payload):
    value = Mock()
    value.json.return_value = payload
    return value


@unittest.skipUnless(ADMIN_URL and ISOLATED, "PostgreSQL isolado não iniciado; use scripts/validate_postgres.py")
class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(ADMIN_URL)
        if (url.query or url.host not in ("localhost", "127.0.0.1", "::1") or url.database != "postgres"
                or url.username != "gestao_test"):
            raise RuntimeError("Conexão recusada: exige cluster local gestao_test.")
        cls.admin_url = url
        cls.admin = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT",
                                  connect_args={"connect_timeout": 10})

    @classmethod
    def tearDownClass(cls):
        cls.admin.dispose()

    def setUp(self):
        self.name = "test_gestao_" + uuid.uuid4().hex
        with self.admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{self.name}"'))
        self.engine = create_engine(self.admin_url.set(database=self.name), pool_size=5,
                                    connect_args={"connect_timeout": 10})
        self.directory = tempfile.TemporaryDirectory(prefix="gestao_pg_test_")
        self.paths = {key: Path(self.directory.name) / name for key, name in (
            ("gestta", "gestta.csv"), ("notion", "notion.csv"), ("json", "gestta.json"),
            ("excel", "resultado.xlsx"), ("manifest", "manifest.json"))}
        self.http_guard = patch("requests.sessions.Session.request",
                                side_effect=AssertionError("HTTP externo proibido"))
        self.http_guard.start()

    def tearDown(self):
        self.http_guard.stop()
        self.engine.dispose()
        # Nome foi criado por este teste e usa prefixo fixo; não recebe entrada externa.
        assert self.name.startswith("test_gestao_") and len(self.name) == 44
        with self.admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{self.name}" WITH (FORCE)'))
        temporary = Path(self.directory.name).resolve()
        assert temporary.parent == Path(tempfile.gettempdir()).resolve()
        assert temporary.name.startswith("gestao_pg_test_")
        self.directory.cleanup()

    def execute(self, **kwargs):
        options = dict(engine=self.engine, paths=self.paths, gestta_collector=gestta_data,
                       notion_collector=notion_data, checklist_collector=checklist_data,
                       include_checklists=True)
        options.update(kwargs)
        return run(**options)

    def scalar(self, sql):
        with self.engine.connect() as conn:
            return conn.execute(text(sql)).scalar_one()

    def counts(self):
        return {table: self.scalar(f'SELECT count(*) FROM public."{table}"') for table in (
            "gestta_relatorios", "notion_dados", "notion_folha", "cs_check",
            "bi_final", "Worflow_CS", "worflow_cs_novo", "bi_operacional")}

    def hashes(self):
        return {key: digest(path) for key, path in self.paths.items()}

    def view_oids(self):
        with self.engine.connect() as conn:
            return dict(conn.execute(text(
                "SELECT relname, oid FROM pg_class WHERE relkind='v' AND relnamespace='public'::regnamespace"
            )).all())

    def test_first_load_creates_all_tables_and_original_views(self):
        result = self.execute()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(self.counts(), {
            "gestta_relatorios": 5, "notion_dados": 2, "notion_folha": 2, "cs_check": 4,
            "bi_final": 5, "Worflow_CS": 2, "worflow_cs_novo": 2, "bi_operacional": 5})
        self.assertEqual(len(pd.read_excel(self.paths["excel"])), 5)
        self.assertEqual(self.scalar(
            "SELECT cliente__cnpj FROM public.gestta_relatorios WHERE tarefa__id='demo-task-01'"),
            "00000000000001")
        self.assertEqual(self.scalar(
            "SELECT count(*) FROM public.bi_final WHERE código_cliente IS NULL"), 1)

    def test_repeated_load_keeps_counts_and_view_object_ids(self):
        self.execute()
        counts, oids = self.counts(), self.view_oids()
        self.execute()
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.view_oids(), oids)

    def test_cnpj_column_is_text_in_postgresql(self):
        self.execute()
        for name, column in (("gestta_relatorios", "cliente__cnpj"), ("notion_dados", "cnpj"),
                             ("notion_folha", "CNPJ")):
            with self.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:table AND column_name=:column"),
                    {"table": name, "column": column}).scalar_one()
                self.assertEqual(result, "text")

    def test_failed_source_keeps_postgres_and_all_artifacts(self):
        self.execute()
        counts, hashes, oids = self.counts(), self.hashes(), self.view_oids()
        with self.assertRaises(ETLError):
            self.execute(gestta_collector=Mock(side_effect=ETLError("synthetic failure")))
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.hashes(), hashes)
        self.assertEqual(self.view_oids(), oids)

    def test_schema_drift_rolls_back_earlier_table_and_preserves_files(self):
        self.execute()
        before = self.scalar('SELECT "Gestão de Clientes" FROM public.notion_folha WHERE "Código Cliente"=1')
        hashes = self.hashes()
        def different_notion():
            frame = notion_data()
            frame["Gestão de Clientes"] = "Changed fictitious value"
            return frame
        def changed_schema():
            frame = gestta_data()
            frame["new_unexpected_column"] = "synthetic"
            return frame
        with self.assertRaises(ETLError):
            self.execute(gestta_collector=changed_schema, notion_collector=different_notion)
        self.assertEqual(self.scalar(
            'SELECT "Gestão de Clientes" FROM public.notion_folha WHERE "Código Cliente"=1'), before)
        self.assertEqual(self.hashes(), hashes)

    def test_invalid_view_rolls_back_data_and_new_ddl(self):
        self.execute()
        counts, oids = self.counts(), self.view_oids()
        from transformacao.PBI_OS import transformar_gestta
        replacement = transformar_gestta(gestta_data().iloc[:1])
        with self.assertRaises(Exception):
            database.publish_tables(self.engine, {"gestta_relatorios": replacement}, view_sql=[
                "CREATE VIEW public.transient_test_view AS SELECT 1 AS value",
                "CREATE OR REPLACE VIEW public.bi_final AS SELECT nonexistent FROM public.gestta_relatorios",
            ])
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.view_oids(), oids)
        self.assertIsNone(self.scalar("SELECT to_regclass('public.transient_test_view')"))

    def test_first_load_failure_rolls_back_new_tables(self):
        frame = pd.DataFrame({"id": ["synthetic"]})
        with self.assertRaises(Exception):
            database.publish_tables(self.engine, {"gestta_relatorios": frame},
                                    view_sql=["SELECT * FROM nonexistent_test_relation"])
        with self.engine.connect() as conn:
            self.assertFalse(inspect(conn).has_table("gestta_relatorios", schema="public"))

    def test_dependent_external_view_survives_refresh(self):
        self.execute()
        with self.engine.begin() as conn:
            conn.execute(text("CREATE VIEW public.external_test_consumer AS SELECT * FROM public.bi_final"))
        oid = self.scalar("SELECT 'public.external_test_consumer'::regclass::oid")
        self.execute()
        self.assertEqual(self.scalar("SELECT 'public.external_test_consumer'::regclass::oid"), oid)
        self.assertEqual(self.scalar("SELECT count(*) FROM public.external_test_consumer"), 5)

    def test_session_lock_prevents_concurrent_pipeline(self):
        collector = Mock(side_effect=AssertionError("must not collect while locked"))
        with database.pipeline_lock(self.engine):
            with self.assertRaises(ETLError):
                self.execute(gestta_collector=collector)
        collector.assert_not_called()

    def test_publication_transaction_lock_prevents_concurrent_write(self):
        self.execute()
        counts = self.counts()
        with self.engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": database.LOCK_ID})
            with self.assertRaises(ETLError):
                database.publish_tables(self.engine, {
                    "gestta_relatorios": pd.DataFrame({"id": ["synthetic"]})})
        self.assertEqual(self.counts(), counts)

    def test_lock_released_after_extraction_failure(self):
        with self.assertRaises(ETLError):
            self.execute(gestta_collector=Mock(side_effect=ETLError("synthetic")))
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT pg_try_advisory_lock(:key)"),
                                  {"key": database.LOCK_ID + 1}).scalar_one()
            try:
                self.assertTrue(result)
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"),
                             {"key": database.LOCK_ID + 1})

    def test_empty_load_does_not_delete_existing_data(self):
        self.execute()
        counts = self.counts()
        with self.assertRaises(ETLError):
            database.publish_tables(self.engine, {"gestta_relatorios": pd.DataFrame(columns=["id"])})
        self.assertEqual(self.counts(), counts)

    def test_mocked_http_to_postgres_end_to_end(self):
        http_g = Mock()
        http_g.post.side_effect = [response(gestta_data().to_dict("records"))] + [response([])] * 11
        http_n = Mock()
        pages = []
        for _, row in notion_data().iterrows():
            props = {name: {"type": "rich_text", "rich_text": []} for name in row.index}
            props["Código Cliente"] = {"type": "number", "number": int(row["Código Cliente"])}
            props["CNPJ"] = {"type": "rich_text", "rich_text": [{"plain_text": row["CNPJ"]}]}
            props["Gestão de Clientes"] = {"type": "rich_text", "rich_text": [{"plain_text": row["Gestão de Clientes"]}]}
            props["Primeira Competência"] = {"type": "date", "date": {"start": "2026-01-01"}}
            pages.append({"id": f"synthetic-page-{len(pages)}", "properties": props})
        http_n.post.return_value = response({"results": pages, "has_more": False})
        http_c = Mock()
        http_c.get.return_value = response({"customer_task_steps": [
            {"name": "Fictitious step", "order": 1, "done": True}]})
        client = NotionClient(token="synthetic", database_id="synthetic", http=http_n)
        self.execute(
            gestta_collector=lambda: collect_gestta(token="synthetic", http=http_g),
            notion_collector=lambda: collect_notion(client=client),
            checklist_collector=lambda targets: CS.collect(targets, token="synthetic", http=http_c))
        self.assertEqual(self.scalar("SELECT count(*) FROM public.bi_final"), 5)
        self.assertEqual(self.scalar("SELECT count(*) FROM public.cs_check"), 2)
        self.assertEqual(http_g.post.call_count, 12)

    def test_demo_cli_runs_without_api_accounts(self):
        demo_name = "gestao_demo_" + uuid.uuid4().hex
        with self.admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{demo_name}"'))
        try:
            env = os.environ.copy()
            env["DEMO_DATABASE_URL"] = self.admin_url.set(database=demo_name).render_as_string(hide_password=False)
            result = subprocess.run([sys.executable, "-X", "utf8", "scripts/run_demo.py"],
                                    cwd=ROOT, env=env, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "complete")
            self.assertEqual(payload["rows"]["gestta_relatorios"], 5)
        finally:
            assert demo_name.startswith("gestao_demo_")
            with self.admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE "{demo_name}" WITH (FORCE)'))


if __name__ == "__main__":
    unittest.main()

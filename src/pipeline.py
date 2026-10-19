"""Execução coordenada: fontes atuais, validação, transação, arquivos e RPAs opcionais."""
import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sqlalchemy import create_engine

from database import pipeline_lock, publish_tables
from etl_support import ETLError, digest, discard, notify, publish_files, stage_csv, stage_file, stage_json
from extracao import base_notion, gestta_relatorios
from security_config import configured_path, database_url
from transformacao import CS, PBI_OS

LOG = logging.getLogger(__name__)


def output_paths():
    return {
        "gestta": configured_path("GESTTA_CSV_PATH", "data/gestta_relatorios.csv"),
        "notion": configured_path("NOTION_CSV_PATH", "data/notion_dados.csv"),
        "json": configured_path("DATA_DIR", "data") / "gestta_relatorios.json",
        "excel": configured_path("EXPORT_XLSX_PATH", "data/resultado.xlsx"),
        "manifest": configured_path("RUN_MANIFEST_PATH", "data/latest_run.json"),
    }


def run(*, engine=None, gestta_collector=None, notion_collector=None, checklist_collector=None,
        include_checklists=False, refresh_powerbi=False, paths=None, publisher=None):
    owns_engine = engine is None
    engine = engine if engine is not None else create_engine(database_url(), pool_pre_ping=True)
    gestta_collector = gestta_collector or gestta_relatorios.collect
    notion_collector = notion_collector or base_notion.collect
    checklist_collector = checklist_collector or CS.collect
    publisher = publisher or publish_tables
    paths = {key: Path(value) for key, value in (paths or output_paths()).items()}
    if set(paths) != {"gestta", "notion", "json", "excel", "manifest"}:
        if owns_engine:
            engine.dispose()
        raise ETLError("Configuração de saídas incompleta.")
    if len({path.resolve() for path in paths.values()}) != len(paths):
        if owns_engine:
            engine.dispose()
        raise ETLError("Caminhos de saída não podem apontar para o mesmo arquivo.")
    run_id = uuid.uuid4().hex
    files = []
    database_committed = False
    stage = "lock"
    try:
        with pipeline_lock(engine):
            stage = "extração_notion"
            raw_n = notion_collector()
            stage = "extração_gestta"
            raw_g = gestta_collector()
            stage = "validação"
            gestta = PBI_OS.transformar_gestta(raw_g)
            notion = PBI_OS.transformar_notion(raw_n)
            PBI_OS.validate_join(gestta, notion)
            tables = {"notion_folha": raw_n, "gestta_relatorios": gestta, "notion_dados": notion}
            if include_checklists:
                stage = "extração_checklists"
                tables["cs_check"] = checklist_collector(PBI_OS.cs_targets(gestta))
            stage = "preparação_arquivos"
            files.append(stage_csv(raw_g, paths["gestta"]))
            files.append(stage_csv(raw_n, paths["notion"]))
            files.append(stage_json(raw_g.astype(object).where(raw_g.notna(), None).to_dict("records"),
                                    paths["json"]))
            joined = gestta.merge(notion, how="left", left_on="cliente__código",
                                  right_on="código_cliente", validate="many_to_one")
            files.append(stage_file(paths["excel"], lambda path: joined.to_excel(path, index=False)))
            manifest = {"run_id": run_id, "status": "complete",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "rows": {key: len(frame) for key, frame in tables.items()},
                        "sha256": {"gestta": digest(files[0][0]), "notion": digest(files[1][0])}}
            files.append(stage_json(manifest, paths["manifest"]))
            stage = "publicação_banco"
            publisher(engine, tables, view_sql=PBI_OS.VIEW_SQL)
            database_committed = True
            stage = "publicação_arquivos"
            publish_files(files)  # Manifesto é o último: leitores rejeitam pares incompletos.
            if refresh_powerbi:
                stage = "solicitação_powerbi"
                from automacao.RPA_Gestao_Atividades import run as activities
                from automacao.RPA_Gestao_Supervisores import run as supervisors
                activities()
                supervisors()
            LOG.info("Execução concluída: run_id=%s linhas_gestta=%d linhas_notion=%d",
                     run_id, len(gestta), len(notion))
            return manifest
    except Exception:
        LOG.error("Execução interrompida: run_id=%s etapa=%s banco_confirmado=%s",
                  run_id, stage, database_committed)
        notify("Falha no ETL; nenhuma solicitação posterior deve ser considerada concluída.")
        raise ETLError(
            f"ETL interrompido na etapa {stage}; banco_confirmado={database_committed}."
        ) from None
    finally:
        discard(files)
        if owns_engine:
            engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklists", action="store_true", help="Consultar checklists antes da transação.")
    parser.add_argument("--refresh-powerbi", action="store_true", help="Solicitar refresh após a publicação.")
    args = parser.parse_args()
    run(include_checklists=args.checklists, refresh_powerbi=args.refresh_powerbi)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()

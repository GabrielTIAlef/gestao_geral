"""Demonstração PostgreSQL com dados fictícios e rede HTTP bloqueada."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from examples.synthetic import checklist_data, gestta_data, notion_data
from pipeline import run


def main():
    value = os.getenv("DEMO_DATABASE_URL")
    if not value:
        raise SystemExit("Configure DEMO_DATABASE_URL para um banco local gestao_demo.")
    url = make_url(value)
    if (url.drivername != "postgresql+psycopg2" or url.query
            or url.host not in ("127.0.0.1", "localhost", "::1")
            or not url.database or not (url.database == "gestao_demo" or url.database.startswith("gestao_demo_"))):
        raise SystemExit("A demonstração aceita apenas PostgreSQL local com banco gestao_demo.")
    directory = ROOT / "data" / "demo"
    paths = {key: directory / name for key, name in (
        ("gestta", "gestta.csv"), ("notion", "notion.csv"), ("json", "gestta.json"),
        ("excel", "resultado.xlsx"), ("manifest", "latest_run.json"))}
    engine = create_engine(url, connect_args={"connect_timeout": 10})
    try:
        with patch("requests.sessions.Session.request",
                   side_effect=AssertionError("HTTP externo bloqueado na demonstração")):
            result = run(engine=engine, paths=paths, gestta_collector=gestta_data,
                         notion_collector=notion_data, checklist_collector=checklist_data,
                         include_checklists=True)
        print(json.dumps({"status": result["status"], "rows": result["rows"],
                          "artifacts": str(directory)}, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

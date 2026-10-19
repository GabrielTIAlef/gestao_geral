"""Extração Notion com paginação validada e carga sem substituição de schema."""
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List
from urllib.parse import quote, unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from sqlalchemy import create_engine
from database import pipeline_lock, publish_tables, replace_dataframe
from etl_support import ETLError, dates, discard, numeric_key, publish_files, request_json, stage_csv, text_identifier
from security_config import configured_path, database_url, required_env

LOG = logging.getLogger(__name__)
PG_TABLE = "notion_folha"
VISIBLE_COLUMNS = [
    "Código Cliente", "Gestão de Clientes", "Status do cliente", "Equipe | Atividade",
    "Sistema | Utilização", "Razão Social", "Nome Fantasia", "Canal de contato",
    "CNPJ", "Primeira Competência", "Equipe | Responsável",
]
DATE_COLUMNS = ["Primeira Competência"]


def rich_text(items):
    if not isinstance(items, list):
        raise ETLError("Notion: texto em formato inesperado.")
    return "".join(item.get("plain_text", item.get("text", {}).get("content", ""))
                   for item in items).strip()


def next_page(payload, seen):
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ETLError("Notion: resposta sem lista results.")
    if not isinstance(payload.get("has_more"), bool):
        raise ETLError("Notion: indicador de paginação ausente ou inválido.")
    if not payload["has_more"]:
        return None
    cursor = payload.get("next_cursor")
    if not isinstance(cursor, str) or not cursor or cursor in seen:
        raise ETLError("Notion: cursor ausente ou repetido.")
    seen.add(cursor)
    return cursor


class NotionClient:
    def __init__(self, token=None, database_id=None, http=None):
        self.database_id = database_id if database_id is not None else required_env("NOTION_DATABASE_ID")
        self.headers = {"Authorization": "Bearer " + (token if token is not None else required_env("NOTION_TOKEN")),
                        "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
        self.http = http
        self.cache = {}

    def call(self, method, url, **kwargs):
        return request_json(method, url, http=self.http, headers=self.headers, **kwargs)

    def pages(self):
        cursor, seen, rows = None, set(), []
        while True:
            payload = self.call("post", f"https://api.notion.com/v1/databases/{self.database_id}/query",
                                json={} if cursor is None else {"start_cursor": cursor})
            cursor = next_page(payload, seen)
            if any(not isinstance(item, dict) or not isinstance(item.get("properties"), dict)
                   for item in payload["results"]):
                raise ETLError("Notion: página sem propriedades.")
            rows.extend(payload["results"])
            if cursor is None:
                return rows

    def title(self, page_id):
        if not page_id:
            raise ETLError("Notion: relação sem identificador.")
        if page_id not in self.cache:
            payload = self.call("get", f"https://api.notion.com/v1/pages/{quote(page_id, safe='')}")
            if not isinstance(payload, dict) or not isinstance(payload.get("properties"), dict):
                raise ETLError("Notion: página relacionada inválida.")
            titles = [p for p in payload["properties"].values() if p.get("type") == "title"]
            if len(titles) != 1:
                raise ETLError("Notion: título relacionado ausente ou ambíguo.")
            self.cache[page_id] = rich_text(titles[0].get("title", []))
        return self.cache[page_id]

    def relation(self, page_id, prop):
        values = prop.get("relation", [])
        if prop.get("has_more"):
            if not page_id or not prop.get("id"):
                raise ETLError("Notion: relação paginada sem identificadores.")
            cursor, seen, values = None, set(), []
            while True:
                url = (f"https://api.notion.com/v1/pages/{quote(page_id, safe='')}/properties/"
                       f"{quote(unquote(prop['id']), safe='')}")
                payload = self.call("get", url, params={} if cursor is None else {"start_cursor": cursor})
                cursor = next_page(payload, seen)
                for item in payload["results"]:
                    if not isinstance(item, dict) or not isinstance(item.get("relation"), dict):
                        raise ETLError("Notion: item de relação inválido.")
                    values.append(item["relation"])
                if cursor is None:
                    break
        if not isinstance(values, list):
            raise ETLError("Notion: relação inválida.")
        return "; ".join(self.title(item.get("id")) for item in values)

    def serialize(self, prop, page_id):
        if not prop:
            return None
        kind = prop.get("type")
        value = prop.get(kind)
        if kind in ("title", "rich_text"):
            return rich_text(value or [])
        if kind == "relation":
            return self.relation(page_id, prop)
        if kind in ("number", "checkbox", "url", "email", "phone_number"):
            return value
        if kind in ("select", "status"):
            return (value or {}).get("name")
        if kind == "multi_select":
            return ", ".join(item.get("name", "") for item in (value or []))
        if kind == "date":
            return (value or {}).get("start")
        if kind == "people":
            return ", ".join(item.get("name") or item.get("id", "") for item in (value or []))
        if kind == "files":
            return ", ".join(item.get(item.get("type"), {}).get("url", "") for item in (value or []))
        raise ETLError("Notion: tipo de propriedade não suportado.")


def normalize_visible_only(pages, keep_props=VISIBLE_COLUMNS, *, client=None):
    if not pages:
        raise ETLError("Notion: lote vazio; última versão preservada.")
    client = client or NotionClient()
    rows = []
    for page in pages:
        props = page.get("properties", {})
        if not {"Código Cliente", "Gestão de Clientes", "CNPJ"}.issubset(props):
            raise ETLError("Notion: propriedades obrigatórias ausentes.")
        rows.append({name: client.serialize(props.get(name), page.get("id")) for name in keep_props})
    frame = pd.DataFrame(rows, columns=keep_props)
    frame["Código Cliente"] = numeric_key(frame["Código Cliente"], "Notion")
    frame["CNPJ"] = text_identifier(frame["CNPJ"], "CNPJ Notion")
    if frame["Código Cliente"].duplicated().any():
        raise ETLError("Notion: código de cliente duplicado; cardinalidade indefinida.")
    for column in DATE_COLUMNS:
        frame[column] = dates(frame[column], "Notion")
    return frame


def fetch_notion_database(*, client=None):
    return (client or NotionClient()).pages()


def collect(*, client=None):
    client = client or NotionClient()
    frame = normalize_visible_only(client.pages(), client=client)
    LOG.info("Extração Notion: linhas=%d", len(frame))
    return frame


def main():
    engine = create_engine(database_url(), pool_pre_ping=True)
    files = []
    try:
        with pipeline_lock(engine):
            frame = collect()
            files.append(stage_csv(frame, configured_path("NOTION_CSV_PATH", "data/notion_dados.csv")))
            publish_tables(engine, {PG_TABLE: frame})
            publish_files(files)
    except Exception:
        raise ETLError("Extração/publicação Notion falhou; consulte a etapa registrada.") from None
    finally:
        discard(files)
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()

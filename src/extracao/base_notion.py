#!/usr/bin/env python
# coding: utf-8

# In[3]:


import os
import time
import logging
from typing import Any, Dict, List
from dotenv import load_dotenv
import pandas as pd
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Conexão ao Notion API
load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
PG_DSN = "postgresql+psycopg2://postgres:[CREDENCIAL_REMOVIDA]@localhost:5432/ProjetoImport"
PG_TABLE = "notion_folha"
# Extração dos dados Notion
VISIBLE_COLUMNS = [
    "Código Cliente",
    "Gestão de Clientes",
    "Status do cliente",
    "Equipe | Atividade",
    "Sistema | Utilização",
    "Razão Social",
    "Nome Fantasia",
    "Canal de contato",
    "CNPJ",
    "Primeira Competência",
    "Equipe | Responsável",
]

# Transformação valores data
DATE_COLUMNS = ["Primeira Competência"]

assert NOTION_TOKEN, "Missing NOTION_TOKEN"
assert NOTION_DATABASE_ID, "Missing NOTION_DATABASE_ID"
assert PG_DSN, "Missing PG_DSN"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Extração dos dados do Notion
NOTION_VERSION = "2022-06-28"
QUERY_URL = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
NOTION_PAGE_URL = "https://api.notion.com/v1/pages/{}"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

# extração das páginas
_REL_CACHE: Dict[str, str] = {}

    
def q(name: str) -> str:
    """Cita identificadores Postgres preservando exatamente o nome (com espaços/acentos)."""
    return '"' + name.replace('"', '""') + '"'

def _rich_text_to_plain(rich_list: List[Dict[str, Any]]) -> str:
    return "".join([r.get("plain_text", "") for r in (rich_list or [])]).strip()

def _people_to_names(people: List[Dict[str, Any]]) -> str:
    return ", ".join([p.get("name") or p.get("id") for p in (people or [])])

def get_related_title(page_id: str) -> str:
    """Busca o título (property do tipo title) da página relacionada, com cache."""
    if not page_id:
        return ""
    if page_id in _REL_CACHE:
        return _REL_CACHE[page_id]
    resp = requests.get(NOTION_PAGE_URL.format(page_id), headers=HEADERS, timeout=60)
    if resp.status_code != 200:
        _REL_CACHE[page_id] = ""
        return ""
    data = resp.json()
    props = data.get("properties", {})
    title = ""
    for prop in props.values():
        if prop.get("type") == "title":
            tlist = prop.get("title", [])
            if tlist:
                title = tlist[0].get("plain_text", "") or ""
            break
    _REL_CACHE[page_id] = title
    return title

def serialize_property(prop: Dict[str, Any]) -> Any:
    if not prop:
        return None
    ptype = prop.get("type")
    val = prop.get(ptype)

    if ptype in ("title", "rich_text"):
        return _rich_text_to_plain(val)
    if ptype == "number":
        return val
    if ptype == "checkbox":
        return bool(val) if val is not None else None
    if ptype == "select":
        return (val or {}).get("name")
    if ptype == "multi_select":
        return ", ".join([v.get("name", "") for v in (val or [])])
    if ptype == "date":
        if not val:
            return None
        start = val.get("start")
        if isinstance(start, str) and len(start) >= 10:
            return start[:10]
        return start
    if ptype == "people":
        return _people_to_names(val)
    if ptype == "files":
        urls = []
        for f in (val or []):
            if f.get("type") == "external":
                urls.append(f["external"]["url"])
            elif f.get("type") == "file":
                urls.append(f["file"]["url"])
        return ", ".join(urls) if urls else None
    if ptype == "relation":
        titles = []
        for r in (val or []):
            rid = r.get("id")
            t = get_related_title(rid)
            if t:
                titles.append(t)
            time.sleep(0.02)
        return "; ".join(titles) if titles else None
    if ptype == "status":
        return (val or {}).get("name")
    if ptype in ("url", "email", "phone_number"):
        return val
    return str(val) if val is not None else None

def sanitize_dates(df: pd.DataFrame, date_cols: List[str]) -> pd.DataFrame:
    """Converte colunas para DATE, trocando NaT/'' por None (NULL no Postgres)."""
    for col in date_cols:
        if col in df.columns:
            dt = pd.to_datetime(df[col], errors="coerce")
            df[col] = dt.dt.date
            df[col] = df[col].apply(
                lambda x: None if (pd.isna(x) or str(x).lower() == "nat" or str(x).strip() == "") else x
            )
    return df

# Busca aos dados do Notion
def fetch_notion_database() -> List[Dict[str, Any]]:
    results = []
    payload: Dict[str, Any] = {}
    has_more, next_cursor = True, None
    while has_more:
        if next_cursor:
            payload["start_cursor"] = next_cursor
        resp = requests.post(QUERY_URL, headers=HEADERS, json=payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"Notion API error {resp.status_code}: {resp.text}")
        data = resp.json()
        results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")
        time.sleep(0.15)
    logging.info("Fetched %d rows from Notion", len(results))
    return results
# Normalização dos dados da página Notion
def normalize_visible_only(pages: List[Dict[str, Any]], keep_props: List[str]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for p in pages:
        row: Dict[str, Any] = {}
        props = p.get("properties", {})
        for name in keep_props:
            row[name] = serialize_property(props.get(name)) if name in props else None
        rows.append(row)
    df = pd.DataFrame(rows, columns=keep_props)
    df = sanitize_dates(df, DATE_COLUMNS)
    return df

# Carregamento ao BD 
def ensure_table_and_columns(engine, table_name: str, df: pd.DataFrame):
    """Cria a tabela se não existir; adiciona colunas faltantes; e garante tipo DATE nas colunas."""
    with engine.begin() as conn:
        cols_sql = []
        for c in df.columns:
            if c in DATE_COLUMNS:
                cols_sql.append(f'{q(c)} DATE NULL')
            else:
                cols_sql.append(f'{q(c)} TEXT NULL')
        create_sql = f'CREATE TABLE IF NOT EXISTS {q(table_name)} ({", ".join(cols_sql)});'
        conn.execute(text(create_sql))

        rs = conn.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :tname
        """), {"tname": table_name}).fetchall()
        existing = {r[0]: r[1] for r in rs}
        for c in df.columns:
            if c not in existing:
                col_type = "DATE" if c in DATE_COLUMNS else "TEXT"
                conn.execute(text(f'ALTER TABLE {q(table_name)} ADD COLUMN {q(c)} {col_type} NULL;'))
        # ajustar tipo de colunas DATE que estejam com outro tipo
        for c in DATE_COLUMNS:
            if c in existing and existing[c].lower() != "date":
                alter = f'ALTER TABLE {q(table_name)} ALTER COLUMN {q(c)} TYPE DATE USING NULLIF({q(c)}::text, \'\')::date;'
                conn.execute(text(alter))
# Replace da tabala no BD
def replace_dataframe(engine, table_name: str, df: pd.DataFrame):
    """TRUNCATE + INSERT (replace)."""
    with engine.begin() as conn:
        conn.execute(text(f'TRUNCATE TABLE {q(table_name)};'))
        if df.empty:
            logging.info("DataFrame vazio; tabela ficou vazia.")
            return
        # limpa 'NaT' literais
        for c in df.columns:
            df[c] = df[c].apply(lambda x: None if (pd.isna(x) or str(x).lower() == "nat") else x)

        cols = list(df.columns)
        col_list_sql = ", ".join(q(c) for c in cols)
        rows = df.where(pd.notnull(df), None).values.tolist()

        placeholders = ", ".join(
            "(" + ", ".join([f":{i}_{j}" for j in range(len(cols))]) + ")"
            for i in range(len(rows))
        )
        params = {f"{i}_{j}": val for i, row in enumerate(rows) for j, val in enumerate(row)}

        sql = f'INSERT INTO {q(table_name)} ({col_list_sql}) VALUES {placeholders};'
        conn.execute(text(sql), params)

def main():
    engine = create_engine(PG_DSN, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1;"))
    except OperationalError:
        logging.error("Falha ao conectar no Postgres. Verifique PG_DSN.")
        raise

    pages = fetch_notion_database()
    df = normalize_visible_only(pages, VISIBLE_COLUMNS)
    logging.info("DF shape=%s cols=%s", df.shape, list(df.columns))

    # debug rápido (opcional): conferir exemplos das 2 colunas problemáticas
    try:
        logging.info("Exemplo Gestão de Clientes: %s", df["Gestão de Clientes"].head(5).tolist())
        logging.info("Exemplo 1ª Competência DEMO: %s", df["1ª Competência DEMO"].head(5).tolist())
    except Exception:
        pass

    ensure_table_and_columns(engine, PG_TABLE, df)
    replace_dataframe(engine, PG_TABLE, df)
    logging.info("REPLACE concluído: %d linhas em %s", len(df), PG_TABLE)

if __name__ == "__main__":
    main()


# In[ ]:





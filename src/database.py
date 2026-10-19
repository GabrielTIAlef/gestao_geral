"""Publicação sem DROP/CASCADE, usando uma Connection e tabelas estáveis."""
from contextlib import contextmanager
import logging

import pandas as pd
from sqlalchemy import BigInteger, Boolean, Date, Float, Text, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.sqltypes import String, Integer, Numeric

from etl_support import ETLError

LOG = logging.getLogger(__name__)
LOCK_ID = 724193810
ALLOWED_TABLES = {"gestta_relatorios", "notion_dados", "notion_folha", "cs_check"}
DATE_COLUMNS = {"Primeira Competência", "primeira_competência",
                "data_criação_completa_empresa", "tarefa__data_de_vencimento_(completa)",
                "data_criação_completa", "tarefa__data_de_conclusão_(completa)", "data_legal"}


def column_types(frame):
    types = {}
    for column in frame:
        if column in DATE_COLUMNS:
            types[column] = Date()
        elif column in {"CNPJ", "cnpj", "cliente__cnpj", "id", "tarefa__id"}:
            types[column] = Text()
        elif column in {"Código Cliente", "código_cliente", "cliente__código", "step_order"}:
            types[column] = BigInteger()
        elif column == "done":
            types[column] = Boolean()
        elif pd.api.types.is_integer_dtype(frame[column]):
            types[column] = BigInteger()
        elif pd.api.types.is_float_dtype(frame[column]):
            types[column] = Float()
        elif pd.api.types.is_bool_dtype(frame[column]):
            types[column] = Boolean()
        else:
            types[column] = Text()
    return types


def replace_table(conn, name, frame, *, allow_empty=False):
    if name not in ALLOWED_TABLES:
        raise ETLError("Tabela não gerenciada pelo projeto.")
    if frame.empty and not allow_empty:
        raise ETLError("Carga vazia bloqueada; última versão preservada.")
    if frame.columns.duplicated().any():
        raise ETLError("Carga com colunas duplicadas.")
    types = column_types(frame)
    inspector = inspect(conn)
    schema = "public" if conn.dialect.name == "postgresql" else None
    if inspector.has_table(name, schema=schema):
        existing = {c["name"]: c["type"] for c in inspector.get_columns(name, schema=schema)}
        if set(existing) != set(frame.columns):
            raise ETLError("Schema existente incompatível; migração explícita necessária.")
        for column, expected in types.items():
            actual = existing[column]
            compatible = (
                (isinstance(expected, Text) and isinstance(actual, String)) or
                (isinstance(expected, BigInteger) and isinstance(actual, (Integer, Numeric))) or
                (isinstance(expected, Date) and isinstance(actual, Date)) or
                (isinstance(expected, Boolean) and isinstance(actual, Boolean)) or
                (isinstance(expected, Float) and isinstance(actual, (Float, Numeric)))
            )
            if not compatible:
                raise ETLError("Tipos existentes incompatíveis; migração explícita necessária.")
        quoted = conn.dialect.identifier_preparer.quote(name)
        qualified = f"public.{quoted}" if schema else quoted
        # DELETE preserva dependências, grants e tipos; erros revertem a transação.
        conn.execute(text(f"DELETE FROM {qualified}"))
    frame.to_sql(name, conn, schema=schema, if_exists="append", index=False,
                 dtype=types, chunksize=500, method=None)
    quoted = conn.dialect.identifier_preparer.quote(name)
    qualified = f"public.{quoted}" if schema else quoted
    count = conn.execute(text(f"SELECT count(*) FROM {qualified}")).scalar_one()
    if count != len(frame):
        raise ETLError("Reconciliação de contagem da carga falhou.")
    LOG.info("Carga validada: tabela=%s linhas=%d", name, count)


def publish_tables(engine, tables, *, view_sql=()):
    # Nenhuma escrita é confirmada até todas as tabelas e views passarem.
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SET LOCAL search_path = public"))
            conn.execute(text("SET LOCAL lock_timeout = '30s'"))
            if not conn.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK_ID}).scalar_one():
                raise ETLError("Outra publicação está em andamento.")
        for name, frame in tables.items():
            replace_table(conn, name, frame)
        for sql in view_sql:
            conn.execute(text(sql))


@contextmanager
def pipeline_lock(engine):
    # Lock de sessão cobre também extração e arquivos. Liberação ocorre no finally.
    with engine.connect() as conn:
        acquired = True
        if conn.dialect.name == "postgresql":
            acquired = conn.execute(text("SELECT pg_try_advisory_lock(:key)"),
                                    {"key": LOCK_ID + 1}).scalar_one()
            conn.commit()
        if not acquired:
            raise ETLError("Outra execução está em andamento.")
        try:
            yield
        finally:
            if conn.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_ID + 1})
                conn.commit()


def replace_dataframe(engine_or_conn, name, frame, *, allow_empty=False):
    if isinstance(engine_or_conn, Engine):
        with engine_or_conn.begin() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text("SET LOCAL lock_timeout = '30s'"))
                if not conn.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK_ID}).scalar_one():
                    raise ETLError("Outra publicação está em andamento.")
            replace_table(conn, name, frame, allow_empty=allow_empty)
    else:
        replace_table(engine_or_conn, name, frame, allow_empty=allow_empty)

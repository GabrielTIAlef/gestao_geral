"""Transformação pura e publicação transacional das bases do BI."""
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from sqlalchemy import create_engine, text
from database import pipeline_lock, publish_tables, replace_dataframe
from etl_support import (ETLError, dates, discard, numeric_key, publish_files, read_snapshot_pair,
                         require_columns, stage_file, text_identifier)
from security_config import configured_path, database_url

LOG = logging.getLogger(__name__)
RENAME = {
        "company.created_at": "data_criação_completa_empresa",
        "name": "Tarefa - Nome",
        "company_department.name": "Empresa - Departamento",
        "type": "Tarefa - Tipo",
        "subtype": "Tarefa - Subtipo",
        "status": "Tarefa - Status",
        "owner.name": "Tarefa - Responsável",
        "notify_customer": "Tarefa - Notifica Cliente?",
        "fine": "Tarefa - Gera Multa?",
        "_due_date": "tarefa__data_de_vencimento_(completa)",
        "downloaded": "Tarefa - Baixada?",
        "done_overdue": "Tarefa - Concluída em Atraso",
        "done_fine": "Tarefa - Concluída com Multa",
        "created_at": "data_criação_completa",
        "concluded_by.name": "Tarefa - Concluído por",
        "conclusion_date": "Tarefa - Data de conclusão (completa)",
        "id": "Tarefa - ID",
        "overdue": "Tarefa - Atrasada?",
        "on_time": "Tarefa - No prazo?",
        "customer.federal_regime.name": "Cliente - Regime federal",
        "customer.name": "Cliente - Nome",
        "customer.cnpj": "Cliente - CNPJ",
        "customer.active": "Cliente - Ativo?",
        "customer.code": "Cliente - Código",
        "legal_date": "data_legal"
    }
DROP_COLUMNS = [
        "company_task.score", "owner.role", "due_iso_week", "value", "concluded_by.role",
        "customer.company_groupers", "customer.state_regime", "customer.municipal_regime", "note",
        "score", "customer.federal_regime", "_forever", "customer.state_regime.name",
        "customer.municipal_regime.name", "customer.monthly_payment", "company.name", "company.status","owner"
    ]
VIEW_SQL = [
    "\n            CREATE OR REPLACE VIEW bi_final AS\n            SELECT \n                g.*, \n                n.*\n            FROM gestta_relatorios g\n            LEFT JOIN notion_dados n \n                ON g.cliente__código = n.código_cliente;\n        ",
    "\n            CREATE OR REPLACE VIEW Worflow_CS_novo AS\n            SELECT \n                g.*,\n                n.\"gestão_de_clientes\"\n            FROM public.gestta_relatorios g\n            LEFT JOIN public.notion_dados n\n                ON g.\"cliente__código\" = n.\"código_cliente\"\n            WHERE g.\"tarefa__nome\" IN (\n                'Etapa demonstrativa 13',\n                'Etapa demonstrativa 14',\n                'Etapa demonstrativa 15',\n                'Etapa demonstrativa 16',\n                'Etapa demonstrativa 17',\n                'Etapa demonstrativa 18',\n                'Etapa demonstrativa 19',\n                'Etapa demonstrativa 20',\n                'Etapa demonstrativa 21',\n                'Etapa demonstrativa 22',\n                'Etapa demonstrativa 26'\n            )\n        ",
    "\n            CREATE OR REPLACE VIEW \"Worflow_CS\" AS\n            SELECT  \n                g.tarefa__status,\n                g.tarefa__nome,\n                g.tarefa__responsável,\n                g.\"data_criação_completa\",\n                g.tarefa__id,\n                g.cliente__CNPJ,\n                g.cliente__nome,\n                g.cliente__código,\n                g.cliente__ativo\n            FROM public.gestta_relatorios g\n            WHERE g.tarefa__nome IN ( \n                    'Etapa demonstrativa 01',\n                    'Etapa demonstrativa 23',\n                    'Etapa demonstrativa 24',\n                    'Etapa demonstrativa 02',\n                    'Etapa demonstrativa 25',\n                    'Etapa demonstrativa 03',\n                    'Etapa demonstrativa 04',\n                    'Etapa demonstrativa 05',\n                    'Etapa demonstrativa 06',\n                    'Etapa demonstrativa 07',\n                    'Etapa demonstrativa 08',\n                    'Etapa demonstrativa 09',\n                    'Etapa demonstrativa 10',\n                    'Etapa demonstrativa 11',\n                    'Etapa demonstrativa 12'\n                )\n              AND g.\"data_criação_completa\" >= DATE '2000-01-01'\n              AND EXISTS (\n                  SELECT 1\n                  FROM public.gestta_relatorios g2\n                  WHERE g2.\"cliente__nome\" = g.\"cliente__nome\"\n                    AND g2.\"tarefa__nome\" = 'Etapa demonstrativa 01'\n              );\n            ",
    "\n            CREATE OR REPLACE VIEW \"bi_operacional\" AS\n            SELECT \n                \"tarefa__nome\", \"tarefa__subtipo\", \"data_criação_completa\", \"tarefa__id\", \"cliente__nome\", \"cliente__código\" \n            FROM gestta_relatorios\n            WHERE\n                \"tarefa__subtipo\" = 'Atividade demonstrativa'\n                AND\n                \"data_criação_completa\" > '2000-01-01';\n        "
]
CS_TASKS = tuple(f"Etapa demonstrativa {i:02d}" for i in (1,23,24,2,25,3,4,5,6,7,8,9,10,11,12))
DATE_COLUMNS = ("data_criação_completa_empresa", "tarefa__data_de_vencimento_(completa)",
                "data_criação_completa", "tarefa__data_de_conclusão_(completa)", "data_legal")
BOOL_COLUMNS = ("notify_customer", "fine", "downloaded", "done_overdue", "done_fine",
                "overdue", "on_time", "customer.active")
TRANSLATIONS = {"SERVICE_ORDER": "Solicitações de serviço", "RECURRENT": "Recorrentes",
    "DISCONSIDERED": "Desconsideradas", "DONE": "Concluídas", "IMPEDIMENT": "Impedimentos",
    "OPEN": "Abertas", "AUTOMATIC": "Recorrentes automáticas", "FREE": "Ordens de serviço livres",
    "MANUAL": "Recorrentes manuais", "TEMPLATE": "Atividade demonstrativa", "WORKFLOW": "Workflows"}


def boolean_label(value):
    if pd.isna(value) or value == "":
        return None
    if value is True or isinstance(value, str) and value == "True":
        return "Sim"
    if value is False or isinstance(value, str) and value == "False":
        return "Não"
    raise ETLError("Gestta: indicador booleano inválido.")


def transformar_gestta(raw):
    require_columns(raw, ("id", "name", "status", "owner.name", "subtype", "created_at",
                          "customer.code", "customer.cnpj", "customer.name", "customer.active"),
                    "Gestta")
    frame = raw.drop(columns=DROP_COLUMNS, errors="ignore").copy()
    frame["id"] = text_identifier(frame["id"], "ID tarefa")
    if frame["id"].isna().any() or frame["id"].duplicated().any():
        raise ETLError("Gestta: tarefa sem ID ou ID duplicado entre períodos.")
    frame["customer.cnpj"] = text_identifier(frame["customer.cnpj"], "CNPJ Gestta")
    frame["customer.code"] = numeric_key(frame["customer.code"], "Gestta")
    for column in BOOL_COLUMNS:
        if column in frame:
            frame[column] = frame[column].map(boolean_label)
    for column in ("type", "subtype", "status"):
        if column in frame:
            frame[column] = frame[column].replace(TRANSLATIONS)
    frame = frame.rename(columns=RENAME)
    frame.columns = (frame.columns.str.lower().str.strip().str.replace(" ", "_")
                     .str.replace(r"[.\-?]", "", regex=True))
    if frame.columns.duplicated().any():
        raise ETLError("Gestta: nomes de coluna colidem após normalização.")
    for column in frame.select_dtypes(include=["object", "string"]):
        frame[column] = frame[column].map(lambda value: value.strip() if isinstance(value, str) else value)
    for column in DATE_COLUMNS:
        if column in frame:
            frame[column] = dates(frame[column], "Gestta")
    if frame["data_criação_completa"].isna().any():
        raise ETLError("Gestta: data de criação obrigatória ausente.")
    return frame


def transformar_notion(raw):
    require_columns(raw, ("Código Cliente", "Gestão de Clientes", "CNPJ"), "Notion")
    frame = raw.copy()
    frame["Código Cliente"] = numeric_key(frame["Código Cliente"], "Notion")
    frame["CNPJ"] = text_identifier(frame["CNPJ"], "CNPJ Notion")
    if frame["Código Cliente"].duplicated().any():
        raise ETLError("Notion: código duplicado; join multiplicaria linhas.")
    frame.columns = frame.columns.str.lower().str.strip().str.replace(" ", "_")
    if frame.columns.duplicated().any():
        raise ETLError("Notion: nomes de coluna colidem após normalização.")
    frame["gestão_de_clientes"] = frame["gestão_de_clientes"].astype("string").str.split("(").str[0].str.strip()
    if "primeira_competência" in frame:
        frame["primeira_competência"] = dates(frame["primeira_competência"], "Notion")
    return frame


def validate_join(gestta, notion):
    if set(gestta.columns).intersection(notion.columns):
        raise ETLError("Colunas das duas fontes colidem no schema da view.")
    joined = gestta.merge(notion, how="left", left_on="cliente__código",
                          right_on="código_cliente", validate="many_to_one")
    if len(joined) != len(gestta):
        raise ETLError("Reconciliação de linhas do join falhou.")
    # LEFT JOIN é preservado: clientes sem correspondência não são descartados.
    missing = ~gestta["cliente__código"].isin(notion["código_cliente"])
    LOG.info("Join validado: tarefas=%d sem_correspondência=%d", len(gestta), missing.sum())


def cs_targets(gestta):
    entrants = gestta.loc[gestta["tarefa__nome"].eq("Etapa demonstrativa 01"), "cliente__nome"]
    return gestta.loc[gestta["tarefa__nome"].isin(CS_TASKS)
                       & (gestta["data_criação_completa"] >= pd.Timestamp("2000-01-01").date())
                       & gestta["cliente__nome"].notna()
                       & gestta["cliente__nome"].isin(entrants),
                       ["tarefa__nome", "tarefa__id"]].copy()


def limpar_e_carregar_gestta_relatorios(engine_or_conn):
    frame = transformar_gestta(pd.read_csv(
        configured_path("GESTTA_CSV_PATH", "data/gestta_relatorios.csv"),
        dtype="string", keep_default_na=False))
    replace_dataframe(engine_or_conn, "gestta_relatorios", frame)
    return frame


def limpar_e_carregar_notion_dados(engine_or_conn):
    frame = transformar_notion(pd.read_csv(
        configured_path("NOTION_CSV_PATH", "data/notion_dados.csv"),
        dtype="string", keep_default_na=False))
    replace_dataframe(engine_or_conn, "notion_dados", frame)
    return frame


def exportar_excel(engine):
    with engine.connect() as conn:
        view = "public.bi_final" if conn.dialect.name == "postgresql" else "bi_final"
        frame = pd.read_sql(text(f"SELECT * FROM {view}"), conn)
    files = []
    try:
        files.append(stage_file(configured_path("EXPORT_XLSX_PATH", "data/resultado.xlsx"),
                                lambda path: frame.to_excel(path, index=False)))
        publish_files(files)
    finally:
        discard(files)


def main():
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with pipeline_lock(engine):
            raw_g, raw_n = read_snapshot_pair(
                configured_path("GESTTA_CSV_PATH", "data/gestta_relatorios.csv"),
                configured_path("NOTION_CSV_PATH", "data/notion_dados.csv"),
                configured_path("RUN_MANIFEST_PATH", "data/latest_run.json"))
            gestta, notion = transformar_gestta(raw_g), transformar_notion(raw_n)
            validate_join(gestta, notion)
            publish_tables(engine, {"gestta_relatorios": gestta, "notion_dados": notion},
                           view_sql=VIEW_SQL)
            exportar_excel(engine)
        LOG.info("Carga BI concluída.")
    except Exception:
        raise ETLError("Carga BI interrompida; verifique a etapa registrada.") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()

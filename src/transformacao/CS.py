"""Coleta completa de checklists e publicação validada."""
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from sqlalchemy import create_engine, text
from database import pipeline_lock, publish_tables
from etl_support import ETLError, request_json, require_columns
from security_config import database_url, gestta_token

LOG = logging.getLogger(__name__)
checklist = [f"Etapa demonstrativa {index:02d}" for index in range(1, 13)]


def coluna_banco(engine):
    with engine.connect() as conn:
        return pd.read_sql(text('SELECT tarefa__nome, tarefa__id FROM public."Worflow_CS"'), conn)


def collect(targets, *, token=None, http=None):
    require_columns(targets, ("tarefa__nome", "tarefa__id"), "CS")
    selected = targets.loc[targets["tarefa__nome"].isin(checklist), "tarefa__id"]
    if selected.isna().any() or selected.map(lambda value: not isinstance(value, str)).any():
        raise ETLError("CS: identificador de tarefa inválido.")
    ids = selected.unique().tolist()
    if not ids:
        raise ETLError("CS: nenhuma tarefa alvo; carga anterior preservada.")
    headers = {"authorization": token if token is not None else gestta_token(),
               "Accept": "application/json"}
    rows = []
    for task_id in ids:
        payload = request_json("get", f"https://api.gestta.com.br/core/customer/task/{task_id}",
                               http=http, headers=headers)
        if isinstance(payload, dict) and "customer_task_steps" not in payload:
            payload = payload.get("data")
        if not isinstance(payload, dict) or not isinstance(payload.get("customer_task_steps"), list):
            raise ETLError("CS: resposta sem lista de passos.")
        for step in payload["customer_task_steps"]:
            if (not isinstance(step, dict) or not isinstance(step.get("name"), str)
                    or type(step.get("order")) is not int or type(step.get("done")) is not bool):
                raise ETLError("CS: passo com campos ou tipos inválidos.")
            rows.append({"id": task_id, "name": step["name"],
                         "step_order": step["order"], "done": step["done"]})
    frame = pd.DataFrame(rows, columns=["id", "name", "step_order", "done"])
    if frame.empty:
        raise ETLError("CS: lote total vazio; carga anterior preservada.")
    if frame.duplicated(["id", "step_order"]).any():
        raise ETLError("CS: ordem de passo duplicada por tarefa.")
    LOG.info("Checklists coletados: tarefas=%d passos=%d", len(ids), len(frame))
    return frame.sort_values(["id", "step_order"]).reset_index(drop=True)


def api(engine, *, http=None, token=None):
    frame = collect(coluna_banco(engine), http=http, token=token)
    publish_tables(engine, {"cs_check": frame})
    return frame


def main():
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with pipeline_lock(engine):
            api(engine)
    except Exception:
        raise ETLError("Carga CS falhou; nenhuma carga parcial foi aprovada.") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()

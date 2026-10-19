"""Dados inventados para reprodução; nenhuma conexão externa."""
from datetime import date
import pandas as pd


def gestta_data():
    tasks = [
        ("demo-task-01", "Etapa demonstrativa 01", 1),
        ("demo-task-02", "Etapa demonstrativa 13", 1),
        ("demo-task-03", "Etapa demonstrativa 01", 2),
        ("demo-task-04", "Etapa demonstrativa 26", 2),
        ("demo-task-05", "Atividade sem correspondência", 3),
    ]
    return pd.DataFrame([{
        "id": task_id, "name": name, "status": "OPEN", "owner.name": "Pessoa Fictícia",
        "type": "SERVICE_ORDER", "subtype": "TEMPLATE", "created_at": "2026-01-02T10:00:00-03:00",
        "customer.code": code, "customer.cnpj": f"{code:014d}",
        "customer.name": f"Cliente Fictício {code}", "customer.active": True,
        "notify_customer": False,
    } for task_id, name, code in tasks])


def notion_data():
    from extracao.base_notion import VISIBLE_COLUMNS
    rows = []
    for code in (1, 2):
        row = dict.fromkeys(VISIBLE_COLUMNS)
        row.update({"Código Cliente": code, "Gestão de Clientes": f"Equipe Demo {code} (Fictícia)",
                    "CNPJ": f"{code:014d}", "Primeira Competência": date(2026, 1, 1)})
        rows.append(row)
    return pd.DataFrame(rows, columns=VISIBLE_COLUMNS)


def checklist_data(targets):
    return pd.DataFrame([{"id": row["tarefa__id"], "name": f"Passo fictício {order}",
                          "step_order": order, "done": order == 1}
                         for _, row in targets.iterrows() for order in (1, 2)])

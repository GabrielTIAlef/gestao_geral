from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from security_config import configured_path, database_url, gestta_token, required_env

#!/usr/bin/env python
# coding: utf-8

# In[2]:


from sqlalchemy import create_engine, text
from sqlalchemy.types import String, Text, Integer, Boolean
from datetime import datetime
import os
import requests
import json
from pathlib import Path
import pandas as pd

# Conexão ao BD


# Tarefas específicas do CS
checklist = [
    'Etapa demonstrativa 01',
    'Etapa demonstrativa 02',
    'Etapa demonstrativa 03',
    'Etapa demonstrativa 04',
    'Etapa demonstrativa 05',
    'Etapa demonstrativa 06',
    'Etapa demonstrativa 07',
    'Etapa demonstrativa 08',
    'Etapa demonstrativa 09',
    'Etapa demonstrativa 10',
    'Etapa demonstrativa 11',
    'Etapa demonstrativa 12',
]

# Token de conexão ao Gestta
TOKEN = gestta_token()

# Conexão e extração de dados do BD
def conectar_banco():
    engine = create_engine(database_url())
    try:
        with engine.connect() as conn:
            print("✅ Conexão bem-sucedida ao banco de dados.")
        return engine
    except Exception as e:
        print("Falha na conexão ao banco.")
        raise RuntimeError("Execução interrompida; verifique a configuração e o serviço.") from None
def coluna_banco(engine):
    with engine.connect() as conn:
        df_banco = pd.read_sql(
            text("""SELECT tarefa__nome, tarefa__id FROM public."Worflow_CS";"""), 
            conn 
        )
    return df_banco

# Conxão a API do Gestta
def api(engine):
    headers = {
        "authorization": f"{TOKEN}",
        "Accept": "application/json",
    }

    # Informações do BD
    df_banco = coluna_banco(engine)
    print(f"[DB] Linhas no banco: {len(df_banco)} | IDs únicos: {df_banco['tarefa__id'].nunique()}")

    # Filtrando do checklist
    mask = df_banco["tarefa__nome"].isin(checklist)
    print(f"[Filtro] Linhas que batem com checklist: {mask.sum()}")
    ids_alvos = (
        df_banco.loc[mask, "tarefa__id"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
    )
    print(f"[Filtro] IDs únicos para consultar na API: {len(ids_alvos)}")
    if not ids_alvos:
        print("[AVISO] Nenhum ID a consultar. Verifique nomes do checklist vs. banco.")
        return pd.DataFrame(columns=["id","name","order","done"])

    # API
    linhas = []
    sem_lista = 0

    # Busca por tarefa ID para achar checklist
    for idx, task_id in enumerate(ids_alvos, 1):
        url = f"https://api.gestta.com.br/core/customer/task/{task_id}"
        try:
            resp = requests.get(url, headers=headers, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as e:
            print("Falha ao consultar checklist.")
            continue
        passos = payload.get("customer_task_steps") or payload.get("data", {}).get("customer_task_steps", [])
        if not isinstance(passos, list) or len(passos) == 0:
            sem_lista += 1
            print(f"[AVISO] task {task_id} sem 'customer_task_steps' ou lista vazia.")
            continue
        for p in passos:
            linhas.append({
                "id": task_id,
                "name": p.get("name"),
                "order": p.get("order"),
                "done": bool(p.get("done")),
            })

    # Criação do df final
    df_api = ( 
        pd.DataFrame(linhas, columns=["id", "name", "order", "done"])
          .sort_values(["id", "order"], na_position="last")
          .reset_index(drop=True)
    )
    df_db = df_api.rename(columns={"order": "step_order"}) 
    df_db.to_sql(
    "cs_check",
    con=engine,
    schema="public",
    if_exists="replace",
    index=False,
    method="multi",
    dtype={
        "id": String(24),
        "name": Text(),
        "step_order": Integer(),
        "done": Boolean(),
    },
    )
    
    # Resumo
    print(f"[Resumo] Tasks consultadas: {len(ids_alvos)} | sem steps: {sem_lista}")
    print(f"[Resumo] Linhas coletadas: {len(df_api)} | Tasks únicas no DF: {df_api['id'].nunique()}")

    return df_api

def main():
    engine = conectar_banco()
    df_banco = coluna_banco(engine)
    df_api = api(engine)
if __name__ == "__main__":
    main()


# In[ ]:

#!/usr/bin/env python
# coding: utf-8

# In[1]:


import requests
import json
import os
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Diretório onde salva as tabelas e CSV
diretorio_log = r"[CAMINHO_REMOVIDO]"
os.makedirs(diretorio_log, exist_ok=True)
log_arquivo = os.path.join(diretorio_log, "processo_gestta.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_arquivo, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# LOG Envio de mensagem ao Slack em caso de erros no Script ou quando algo não roda
def enviar_mensagem_slack(mensagem):
    webhook_url = os.getenv("webhook_url")
    slack_data = {"text": mensagem}
    try:
        response = requests.post(
            webhook_url, data=json.dumps(slack_data),
            headers={'Content-Type': 'application/json'}
        )
        if response.status_code != 200:
            logging.error(f"Erro: {response.status_code}, {response.text}")
    except Exception as e:
        logging.error(f"Erro: {e}")

# Conexão ao endpoint "API" do Gestta
url = "https://api.gestta.com.br/core/customer/task/report"
# Token necessário para funcionar, se quebrar nada funciona
TOKEN = Path(r"[CAMINHO_REMOVIDO]").read_text(encoding="utf-8").strip()
headers = {
    "authorization": f"{TOKEN}",
    "Content-Type": "application/json"
}
# Carga dos dados do Gestta em Excel e CSV
json_arquivo = os.path.join(diretorio_log, "gestta_relatorios.json")
csv_arquivo = os.path.join(diretorio_log, "gestta_relatorios.csv")

# Montagem dos períodos desejados para puxar relatório 
ano_atual = datetime.now().year
ano_anterior = ano_atual - 1
ano_seguinte = ano_atual + 1
fuso = "-03:00"
# Agora só funciona em bloco de período inferior, então precisa dar essa diminuição
periodos = [
    (f"{ano_anterior}-01-01", f"{ano_anterior}-03-31"),
    (f"{ano_anterior}-04-01", f"{ano_anterior}-06-30"),
    (f"{ano_anterior}-07-01", f"{ano_anterior}-09-30"),
    (f"{ano_anterior}-10-01", f"{ano_anterior}-12-31"),

    (f"{ano_atual}-01-01", f"{ano_atual}-03-31"),
    (f"{ano_atual}-04-01", f"{ano_atual}-06-30"),
    (f"{ano_atual}-07-01", f"{ano_atual}-09-30"),
    (f"{ano_atual}-10-01", f"{ano_atual}-12-31"),

    (f"{ano_seguinte}-01-01", f"{ano_seguinte}-03-31"),
    (f"{ano_seguinte}-04-01", f"{ano_seguinte}-06-30"),
    (f"{ano_seguinte}-07-01", f"{ano_seguinte}-09-30"),
    (f"{ano_seguinte}-10-01", f"{ano_seguinte}-12-31"),
]

dados_gerais = []

# Loop sobre cada período
for inicio, fim in periodos:
    start_date = f"{inicio}T00:00:00{fuso}"
    end_date = f"{fim}T23:59:59{fuso}"
    payload = {
        "type": "CUSTOMER_TASK",
        "filter": "CURRENT_MONTH",
        "dates": {
            "startDate": start_date,
            "endDate": end_date
        }
    }
    # Chamada ao Gestta para trazer os dados em cada período
    try:
        logging.info(f"Iniciando requisição {inicio} a {fim}...")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        # Coleta e normalização dos dados
        if isinstance(data, list):
            df = pd.json_normalize(data)
        else:
            df = pd.json_normalize(data.get("data", data))
        if not df.empty:
            dados_gerais.append(df)
            logging.info(f"Período {inicio} a {fim} processado")                                                 
        else:
            logging.warning(f"Nenhum dado para o período {inicio} a {fim}.")
    except requests.exceptions.RequestException as err:
        msg = f"Erro na requisição ({inicio} a {fim}): {err}"
        logging.error(msg)
        # LOG de erro no Slack
        enviar_mensagem_slack(f"ERRO no script Gestta ({inicio} a {fim}): {err}")
    except Exception as e:
        msg = f"Erro ao processar período ({inicio} a {fim}): {e}"
        logging.error(msg)
        enviar_mensagem_slack(f"ERRO no processamento do script Gestta ({inicio} a {fim}): {e}")

# Salvando os dados consolidados
if dados_gerais:
    df_final = pd.concat(dados_gerais, ignore_index=True)
    df_final.to_csv(csv_arquivo, index=False, encoding="utf-8-sig")
    with open(json_arquivo, "w", encoding="utf-8") as f:
        json.dump(df_final.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    logging.info("Dados salvos")
else:
    msg = "⚠️ Script Gestta executado, mas nenhum dado foi coletado em nenhum período."
    logging.warning(msg)
    enviar_mensagem_slack(msg)


# In[2]:


# Chama outro script para dar sequência
import subprocess
subprocess.run(['python', r'[CAMINHO_REMOVIDO]'])


# In[3]:


# Chama outro script para dar sequência
import subprocess
subprocess.run(['python', r'[CAMINHO_REMOVIDO]'])


# In[6]:


# Chama outro script para dar sequência
import subprocess
subprocess.run(['python', r'[CAMINHO_REMOVIDO]'])


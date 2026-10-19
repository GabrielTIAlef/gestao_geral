from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from security_config import configured_path, database_url, gestta_token, required_env

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
diretorio_log = str(configured_path("DATA_DIR", "data"))
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
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return
    slack_data = {"text": mensagem}
    try:
        response = requests.post(
            webhook_url, data=json.dumps(slack_data),
            headers={'Content-Type': 'application/json'}, timeout=15
        )
        if response.status_code != 200:
            logging.error("Falha no Slack: HTTP %s", response.status_code)
    except Exception as e:
        logging.error("Falha ao enviar alerta ao Slack.")

# Conexão ao endpoint "API" do Gestta
url = "https://api.gestta.com.br/core/customer/task/report"
# Token necessário para funcionar, se quebrar nada funciona
TOKEN = gestta_token()
headers = {
    "authorization": f"{TOKEN}",
    "Content-Type": "application/json"
}
# Carga dos dados do Gestta em Excel e CSV
json_arquivo = os.path.join(diretorio_log, "gestta_relatorios.json")
csv_arquivo = str(configured_path("GESTTA_CSV_PATH", "data/gestta_relatorios.csv"))
Path(csv_arquivo).parent.mkdir(parents=True, exist_ok=True)

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
        response = requests.post(url, headers=headers, json=payload, timeout=60)
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
        msg = "Falha na requisição Gestta."
        logging.error(msg)
        # LOG de erro no Slack
        enviar_mensagem_slack("Falha na extração Gestta.")
    except Exception as e:
        msg = "Falha no processamento Gestta."
        logging.error(msg)
        enviar_mensagem_slack("Falha no processamento Gestta.")

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
subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "transformacao/PBI_OS.py")], check=True)


# In[3]:


# Chama outro script para dar sequência
import subprocess
subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "automacao/RPA_Gestao_Atividades.py")], check=True)


# In[6]:


# Chama outro script para dar sequência
import subprocess
subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "automacao/RPA_Gestao_Supervisores.py")], check=True)

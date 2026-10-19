from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from security_config import configured_path, database_url, gestta_token, required_env

#!/usr/bin/env python
# coding: utf-8

# In[1]:


# rpa_powerbi.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import WebDriverException, TimeoutException
import os, glob, time, requests, sys
from dotenv import load_dotenv

load_dotenv()

# LOG quando der erro manda mensagem no Slack
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
DATASET_NAME = required_env("POWERBI_DATASET_SUPERVISORES")
def send_slack(msg):
    if not SLACK_WEBHOOK_URL: 
        print(msg); return
    try: requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, timeout=10)
    except requests.RequestException: print("Falha no envio ao Slack.", file=sys.stderr)

# Perfil EXCLUSIVO da RPA
USER_DATA_DIR = str(configured_path("CHROME_USER_DATA_DIR"))
PROFILE_DIR = required_env("CHROME_PROFILE_DIR")
# Caminho do Chrome dedicado
CHROME_BINARY = os.getenv("CHROME_BINARY", "").strip()
os.makedirs(USER_DATA_DIR, exist_ok=True)
for lock in glob.glob(os.path.join(USER_DATA_DIR, "Singleton*")):
    try: os.remove(lock)
    except: pass

# Configurações
opts = webdriver.ChromeOptions()
opts.add_argument(f"--user-data-dir={USER_DATA_DIR}")
opts.add_argument(f"--profile-directory={PROFILE_DIR}")
opts.add_argument("--no-first-run")
opts.add_argument("--no-default-browser-check")
opts.add_argument("--disable-blink-features=AutomationControlled")
opts.add_argument("--disable-dev-shm-usage")
opts.add_argument("--start-maximized")
# Em produção rode headless:
opts.add_argument("--headless=new")
opts.add_argument("--disable-gpu")
opts.add_argument("--window-size=1920,1080")

if CHROME_BINARY:
    opts.binary_location = CHROME_BINARY
service = Service()  # Selenium Manager cuida do driver compatível
driver = None
try:
    driver = webdriver.Chrome(service=service, options=opts)
    driver.get("https://app.powerbi.com/groups/me/list?experience=power-bi")
    wait = WebDriverWait(driver, 40)
    wait.until(EC.presence_of_element_located((By.XPATH, "//a[@data-testid='item-name']")))
    blocks = driver.find_elements(By.XPATH, "//span[contains(@class, 'col-name')]")
    found = False
    for block in blocks:
        try:
            a = block.find_element(By.XPATH, ".//a[@data-testid='item-name']")
            name = (a.get_attribute("aria-label") or "").strip()
            # Procura pelo nome do dataset
            if name == DATASET_NAME:
                ActionChains(driver).move_to_element(block).perform()
                btn = WebDriverWait(block, 10).until(
                    EC.element_to_be_clickable((By.XPATH, ".//button[@data-testid='quick-action-button-Atualizar agora']"))
                )
                btn.click()
                print("✅ 'Atualizar agora' clicado!")
                found = True
                break
        except Exception:
            continue

    if not found:
        send_slack("Dataset não encontrado ou atualização indisponível.")
    time.sleep(5)

except TimeoutException:
    send_slack("❌ Timeout ao carregar itens do Power BI. Verifique login nesse perfil da RPA.")
except Exception as e:
    send_slack("Falha na atualização do Power BI.")
    raise RuntimeError("Execução interrompida; verifique a configuração e o serviço.") from None
finally:
    try: 
        if driver: driver.quit()
    except: 
        pass


# In[ ]:

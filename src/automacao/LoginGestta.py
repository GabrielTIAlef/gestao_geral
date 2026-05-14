#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pyautogui as pg
import pyperclip
import time

while True:
    URL = "https://onvio.com.br/login/#/" # Se conecta a página
    TEMPO_ABRIR = 2.5 # Tempo para abrir navegador
    TEMPO_CARREGAR = 2.5 # Tempo extra para carregar página
    pg.FAILSAFE = True # Aborta
    pg.PAUSE = 0.12
    pg.hotkey("win", "r") # Abre o executar
    time.sleep(0.3) # espera
    pg.typewrite(URL, interval=0.01) # Digita URL
    pg.press("enter") # Entrar na URL
    time.sleep(TEMPO_ABRIR + TEMPO_CARREGAR) # Tempo de espera para abrir a página
    time.sleep(5.0)
    
    # Passos para ir passando por cada parte do Gestta, fazendo login e chegando até a página do Token
    time.sleep(5.0)
    pg.press("enter")
    time.sleep(5.0)
    pg.press("enter")
    time.sleep(5.0)
    pg.press("enter")
    time.sleep(5.0)
    pg.press("tab")
    time.sleep(5.0)
    pg.press("tab")
    time.sleep(5.0)
    pg.press("enter")
    time.sleep(5.0)
    pg.press("tab")
    time.sleep(5.0)
    pg.press("enter")
    time.sleep(5.0)
    
    # Chegando a parte que está o Token e passando passos por passos até alcançar a parte do Token
    pg.hotkey("ctrl","shift","i")
    time.sleep(5.0)
    pg.press("f5")
    time.sleep(5.0)
    # Movendo mouse até total canto esquerdo da tela
    pg.moveTo(616, 410, duration=0.4)
    time.sleep(5.0)
    # Chegando até a parte com Token
    for _ in range(6):
        pg.scroll(120)   # positivo = cima
        time.sleep(0.05)
    pg.move(0, 30, duration=0.2)
    pg.click()
    pg.moveTo(998, 500, duration=0.4)
    time.sleep(0.05)
    for _ in range(6):
        pg.scroll(-120)  # negativo = baixo
        time.sleep(0.05)
    # Extração do Token
    pg.doubleClick()
    pg.click()
    time.sleep(5.0)
    pg.hotkey("ctrl","c")
    time.sleep(5.0)
    token_copiado = pyperclip.paste()
    # Teste de extração correta, se não repete a tentativa de extração
    if token_copiado.startswith("JWT"):
        break
    else:
        pg.hotkey("alt", "f4")

# Procura pelo arquivo do Token
pg.hotkey("win","e")
time.sleep(5.0)
pg.hotkey("ctrl","f")
time.sleep(5.0)
pg.typewrite("TokenGestta", interval=0.05)
time.sleep(5.0)
pg.press("enter")
time.sleep(5.0)
pg.press("down")
time.sleep(5.0)
pg.press("up")
time.sleep(5.0)
pg.press("enter")
time.sleep(5.0)
pg.hotkey("ctrl","a")
time.sleep(5.0)
# Carga do Token
pg.hotkey("ctrl","v")
time.sleep(5.0)
pg.hotkey("ctrl", "shift", "s")
time.sleep(5.0)
pg.press("enter")
time.sleep(5.0)
pg.press("left")
time.sleep(5.0)
pg.press("enter")
time.sleep(5.0)


# In[ ]:





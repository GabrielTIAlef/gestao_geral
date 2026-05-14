# Gestão Geral BI

Solução de Business Intelligence e automação de dados para acompanhamento operacional de uma empresa contábil.

## Problema

A operação precisava acompanhar tarefas, clientes, responsáveis, prazos e gargalos de forma centralizada, com baixo custo e atualização frequente.

## Solução

Foi desenvolvida uma arquitetura com Python, PostgreSQL, Power BI e RPA para coletar dados do Gestta e Notion, tratar as bases, criar views analíticas e atualizar datasets automaticamente.

## Arquitetura

Gestta / Notion  
→ Python ETL  
→ PostgreSQL  
→ Views SQL  
→ Power BI  
→ RPA Selenium para atualização automática

## Stack

- Python
- Pandas
- Requests
- SQLAlchemy
- PostgreSQL
- Power BI
- DAX
- Selenium
- Slack Webhook

## Componentes

- `gestta_relatorios.py`: extrai relatórios de tarefas do Gestta.
- `base_notion.py`: extrai dados do Notion.
- `operacional_bd.py`: trata bases, cria tabelas e views.
- `cs_checklist.py`: consulta etapas de onboarding/CS.
- `rpa_powerbi.py`: atualiza datasets do Power BI automaticamente.

## Resultados

- Centralização dos dados operacionais.
- Redução de trabalho manual.
- Atualização quase instantânea dos painéis.
- Visão por time, responsável, status, prazo e cliente.
- Apoio à tomada de decisão operacional.

## Screenshots

![PostgreSQL](docs/screenshots/postgres_modelo.png)

## Segurança

As credenciais, tokens, webhooks e dados reais foram removidos. O projeto utiliza variáveis de ambiente e arquivos de exemplo.

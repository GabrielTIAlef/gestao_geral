# Gestão Geral BI

> 🔹 Solução completa de automação analítica e Business Intelligence para acompanhamento operacional, gestão de tarefas, onboarding de clientes e monitoramento de equipes em tempo quase real.

---

# Visão Geral

Este projeto foi desenvolvido com o objetivo de centralizar, automatizar e estruturar dados operacionais de uma empresa contábil utilizando Python, PostgreSQL, APIs REST, Power BI e RPA.

A solução integra múltiplos sistemas corporativos — principalmente Gestta e Notion — permitindo acompanhamento operacional em tempo quase real, com foco em:

- Gestão de tarefas;
- Gestão de equipes;
- Acompanhamento operacional;
- Controle de onboarding;
- Monitoramento de SLA;
- Centralização de dados;
- Automação de processos analíticos;
- Redução de trabalho manual.

---

# Problema de Negócio

A operação precisava acompanhar milhares de tarefas e processos internos diariamente, porém existiam alguns desafios:

- As ferramentas utilizadas não possuíam APIs públicas completas;
- Existia alta dependência de processos manuais;
- Atualizações dos painéis eram lentas;
- Não havia centralização analítica;
- Existia dificuldade para acompanhar gargalos operacionais;
- Os dados estavam distribuídos entre múltiplas plataformas.

Além disso, a empresa buscava:

- Menor custo possível;
- Alta frequência de atualização;
- Visão operacional e estratégica;
- Gestão individual de colaboradores;
- Monitoramento de fluxos críticos.

---

# Arquitetura da Solução

```txt
Gestta API / Notion API
            ↓
      Python ETL
            ↓
      PostgreSQL
            ↓
       Views SQL
            ↓
        Power BI
            ↓
   Selenium RPA
            ↓
     Slack Alerts
```

---

# Componentes Técnicos

## `gestta_relatorios.py`

Script responsável pela coleta automatizada dos relatórios operacionais do Gestta.

Como o sistema não disponibiliza API pública oficial para todas as necessidades operacionais, foi desenvolvido um fluxo utilizando requisições diretamente aos endpoints da plataforma.

### Principais responsabilidades:
- Coletar tarefas por períodos semestrais;
- Realizar normalização dos dados;
- Consolidar grandes volumes de informações;
- Gerar arquivos CSV e JSON;
- Criar logs operacionais;
- Enviar alertas via Slack;
- Preparar os dados para ingestão no PostgreSQL.

### Tecnologias utilizadas:
- `requests`
- `pandas`
- `logging`
- `json`
- `pathlib`

---

## `base_notion.py`

Script responsável pela integração com a API oficial do Notion.

A rotina extrai propriedades dinâmicas da base utilizada pela operação, tratando diferentes tipos de dados e convertendo-os em estrutura relacional.

### Principais responsabilidades:
- Extrair dados do Notion;
- Tratar propriedades complexas (`relation`, `people`, `date`, `status`);
- Normalizar os dados;
- Sanitizar colunas de data;
- Criar e atualizar tabelas automaticamente;
- Inserir dados tratados no PostgreSQL.

### Tecnologias utilizadas:
- `requests`
- `pandas`
- `sqlalchemy`
- `dotenv`

---

## `operacional_bd.py`

Responsável pelo processo principal de ETL e estruturação analítica.

Este módulo realiza o tratamento das bases, cria tabelas relacionais, views analíticas e integra dados do Gestta e Notion.

### Principais responsabilidades:
- Limpeza e transformação dos dados;
- Padronização de colunas;
- Tradução de status operacionais;
- Conversão de datas;
- Criação de views SQL;
- Integração entre tabelas;
- Exportação de bases tratadas.

### Principais views:
- `bi_final`
- `workflow_cs`

### Tecnologias utilizadas:
- `pandas`
- `sqlalchemy`
- `postgresql`

---

## `cs_checklist.py`

Script desenvolvido para monitoramento do processo de onboarding de clientes.

A solução consulta tarefas específicas do fluxo de entrada de clientes e valida automaticamente a execução de cada etapa.

### Principais responsabilidades:
- Consultar tarefas do onboarding;
- Validar checklist operacional;
- Ler etapas via API;
- Identificar gargalos;
- Estruturar análises de eficiência operacional.

### Tecnologias utilizadas:
- `requests`
- `pandas`
- `sqlalchemy`

---

## `rpa_powerbi.py`

RPA desenvolvida utilizando Selenium para atualização automática dos datasets no Power BI Web.

A solução simula interações no navegador e executa automaticamente o processo de atualização dos painéis.

### Principais responsabilidades:
- Abrir Power BI Web;
- Localizar datasets específicos;
- Executar atualização automática;
- Trabalhar em modo headless;
- Enviar alertas de sucesso e erro via Slack.

### Tecnologias utilizadas:
- `selenium`
- `webdriver`
- `slack webhook`

---

# Dashboards Desenvolvidos

## Operacional

Painel voltado à gestão operacional de tarefas e equipes.

### Principais análises:
- Quantidade de tarefas;
- Status operacionais;
- SLA;
- Produtividade;
- Performance individual;
- Performance por setor;
- Acompanhamento temporal;
- Controle de atrasos.

---

## Atendimento

Painel focado no acompanhamento da criação de tarefas e atendimento operacional.

### Principais análises:
- Volume de demandas;
- Tempo de resposta;
- Criação de tarefas;
- Fluxo operacional;
- Gestão do time de atendimento.

---

## Apuração

Painel voltado ao acompanhamento dos fluxos fiscais e operacionais do time contábil.

### Principais análises:
- Status de etapas;
- Fluxos pendentes;
- Processos críticos;
- Gargalos operacionais.

---

# Resultados Obtidos

| Métrica | Antes | Depois |
|---|---|---|
| Atualização dos painéis | 2h–3h | < 5 minutos |
| Dependência de planilhas manuais | Alta | Baixa |
| Centralização de dados | Parcial | Completa |
| Atualização operacional | Manual | Automatizada |
| Monitoramento de erros | Limitado | Alertas via Slack |

---

# Stack Utilizada

## Dados & Engenharia
- Python
- PostgreSQL
- SQLAlchemy
- Pandas
- APIs REST
- ETL / ELT

## BI & Analytics
- Power BI
- DAX
- Modelagem Relacional
- Dashboards Operacionais

## Automação
- Selenium
- RPA
- Slack Webhooks
- Windows Task Scheduler

---

# Estrutura do Projeto

```txt
gestao-geral-bi/
│
├── src/
│   ├── extract/
│   ├── transform/
│   ├── automation/
│   └── utils/
│
├── sql/
├── docs/
├── samples/
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

# Segurança

Para publicação pública deste projeto:

- Tokens foram removidos;
- Credenciais foram ocultadas;
- Webhooks foram sanitizados;
- Dados reais foram substituídos por exemplos;
- Informações sensíveis não foram incluídas.

---

# Aprendizados e Competências Desenvolvidas

Durante o desenvolvimento deste projeto foram trabalhados temas como:

- Engenharia de dados;
- Integração de APIs;
- ETL;
- Automação de processos;
- Estruturação analítica;
- Modelagem relacional;
- Business Intelligence;
- Monitoramento operacional;
- Arquitetura de dados;
- Processamento e normalização de grandes volumes de dados.

---

🌐 Portfólio:
https://gabrieltialef.github.io/Portf-lio/

💼 LinkedIn:
(adicionar link)

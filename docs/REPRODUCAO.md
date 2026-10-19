# Reprodução e validação local — Etapa 3

## Escopo

Este procedimento reproduz o ETL com dados inteiramente fictícios. Não usa contas de Gestta, Notion, Slack ou Power BI.
O PostgreSQL é real, mas o cluster é criado apenas para testes, escuta em 127.0.0.1 e é encerrado no final.
Não instala serviço do Windows nem utiliza um banco já existente.

Ambiente validado: Windows x86-64, Python 3.12.14 e PostgreSQL 18.6.
As versões Python estão fixadas em requirements-lock.txt. Esse arquivo representa este ambiente validado; outras plataformas/versões precisam de validação própria.

## Instalação do zero no Windows

Pré-requisito: ter Python 3.12 no PATH. Confira antes:
~~~powershell
python --version
~~~
Se o resultado não for Python 3.12, selecione uma instalação 3.12 antes de criar o ambiente.

Na raiz do repositório:
~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
~~~

Nenhum arquivo .env ou token corporativo é necessário para a demonstração/testes.

## PostgreSQL portátil

Obtenha o ZIP de binários pela página oficial indicada em:
- https://www.postgresql.org/download/windows/
- https://www.enterprisedb.com/download-postgresql-binaries

A validação utilizou PostgreSQL 18.6, pacote Windows x86-64. Não há download automático no script publicado.
Extraia o pacote em .local-test/runtime/, que é ignorado pelo Git. Verifique que existem:
~~~text
.local-test/runtime/pgsql/bin/initdb.exe
.local-test/runtime/pgsql/bin/pg_ctl.exe
.local-test/runtime/pgsql/bin/postgres.exe
~~~

O caminho pode ser outro; --pg-bin recebe o diretório bin dos executáveis.

## Suíte completa e demonstração

~~~powershell
$PgBin = (Resolve-Path '.local-test\runtime\pgsql\bin').Path
.\.venv\Scripts\python.exe -X utf8 scripts/validate_postgres.py --pg-bin "$PgBin" --demo
~~~

O comando:
1. cria um cluster novo em .local-test/gestao_pg_*;
2. escolhe uma porta local livre e escuta somente em 127.0.0.1;
3. usa a conta fictícia gestao_test e autenticação trust apenas nesse cluster temporário de dados inventados;
4. remove variáveis corporativas do ambiente entregue aos testes;
5. executa os testes exigindo PostgreSQL, sem aceitar testes ignorados como validação completa;
6. cria bancos test_gestao_* exclusivos de cada caso e os remove ao terminar;
7. executa a demonstração em gestao_demo e gera os arquivos;
8. encerra o PostgreSQL no finally e registra o resultado.

A configuração trust é restrita ao cluster local de teste. Não reutilize essa configuração como instalação de produção.
Os logs e o cluster encerrado ficam em .local-test/ para diagnóstico. Não são versionados.

## Artefatos gerados

~~~text
data/demo/gestta.csv
data/demo/notion.csv
data/demo/gestta.json
data/demo/resultado.xlsx
data/demo/latest_run.json
.local-test/last_validation.json
~~~

A demonstração contém cinco tarefas e dois clientes na fonte Notion, além de uma tarefa sem correspondência no LEFT JOIN.
Contagens esperadas no banco:
- notion_folha: 2
- notion_dados: 2
- gestta_relatorios: 5
- cs_check: 4
- bi_final: 5
- Worflow_CS: 2
- worflow_cs_novo: 2
- bi_operacional: 5

Os CNPJs são identificadores fictícios com zeros iniciais, não números reais consultados.
A origem HTTP é simulada nos testes. A demonstração não solicita atualização no Power BI.
Depois de encerrar o servidor, o Excel e os demais arquivos continuam disponíveis.

## Modos adicionais

Apenas testes disponíveis sem iniciar PostgreSQL:
~~~powershell
.\.venv\Scripts\python.exe -X utf8 scripts/run_tests.py
~~~
Nesse modo, os testes PostgreSQL são explicitamente ignorados. Não equivale à suíte completa.

Demonstração em um banco de demonstração local já criado:
~~~powershell
$env:DEMO_DATABASE_URL = 'postgresql+psycopg2://USUARIO_DE_TESTE@127.0.0.1:PORTA/gestao_demo'
.\.venv\Scripts\python.exe -X utf8 scripts/run_demo.py
~~~
O endereço deve apontar somente para um banco local chamado gestao_demo ou gestao_demo_*.
Parâmetros adicionais na URL são rejeitados para impedir redirecionamento do host.
Não use credenciais corporativas nessa variável.

## O que é comprovado

Consulte docs/ETAPA_3_VALIDACAO.md e docs/evidence/etapa3_resultado.json para resultados executados.
Asserções cobrem as quatro views originais, repetição da carga, CNPJ textual, rollback de dados e DDL, dependências externas, advisory locks, falhas e fluxo com HTTP simulado até PostgreSQL real.

## Limites

- APIs corporativas e sessão real de navegador não foram acessadas.
- Solicitar refresh Power BI continua diferente de confirmar sua conclusão.
- Não há medição de desempenho com volume produtivo.
- PostgreSQL anterior ao 18.6, Linux e macOS não foram validados nesta etapa.
- Migração de banco preexistente incompatível continua exigindo análise explícita.
- A instalação das dependências exige acesso ao índice de pacotes; somente a demonstração e os testes funcionam sem APIs externas após a instalação.

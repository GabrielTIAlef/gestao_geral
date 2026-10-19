# Etapa 3 — Resultado da reprodução e validação

Base: main em 0d8ca418fd336be40858c9675de0e9e39adeba7a.
Data: 19/10/2026.
Estado da entrega: proposta para revisão em branch separada; ainda não integrada à main.

## Resultado

**72 testes aprovados, nenhuma falha, nenhum erro e nenhum teste ignorado**, em duas instalações novas:
1. instalação pelas faixas de requirements.txt;
2. instalação em outro ambiente vazio pelas versões exatas de requirements-lock.txt.

Ambiente: Windows x86-64, Python 3.12.14 e PostgreSQL 18.6 real.
pip check retornou “No broken requirements found.”.
Os servidores temporários foram encerrados ao final. Nenhum serviço permanente foi instalado.

A suíte contém os 58 testes anteriores e 14 testes de integração PostgreSQL.
Evidência estruturada: [evidence/etapa3_resultado.json](evidence/etapa3_resultado.json).

## Validações PostgreSQL efetivamente executadas

- Primeira carga cria as quatro tabelas gerenciadas e as quatro views originais.
- Reprocessar mantém as contagens, sem duplicação.
- Os OIDs das views permanecem estáveis durante o refresh.
- CNPJ permanece TEXT com zeros iniciais.
- LEFT JOIN mantém a tarefa cujo cliente não está na fonte Notion.
- Falha de extração preserva banco, views e arquivos anteriores.
- Schema incompatível na segunda fonte reverte a tabela já modificada na mesma transação.
- Erro na criação/alteração de view reverte dados e uma view temporária criada na transação.
- Falha da primeira carga reverte a criação de tabela nova.
- Uma view externa dependente de bi_final permanece existente após a atualização.
- Advisory lock de sessão impede pipeline concorrente.
- Advisory lock transacional impede publicação concorrente.
- Locks são liberados após falha de extração.
- Lote vazio não apaga a carga anterior.
- Fluxo com HTTP simulado passa pelos extratores reais e chega ao PostgreSQL.
- A demonstração por linha de comando funciona sem contas de API.

Várias asserções pertencem ao mesmo caso de teste; a contagem de casos PostgreSQL é 14.

## Demonstração

Gerada com scripts/run_demo.py em um banco gestao_demo temporário.
Foram produzidos CSV Gestta, CSV Notion, JSON, Excel e manifesto.
Contagens:
- notion_folha: 2
- notion_dados: 2
- gestta_relatorios: 5
- cs_check: 4
- bi_final: 5
- Worflow_CS: 2
- worflow_cs_novo: 2
- bi_operacional: 5

Os dados são inventados. Nenhuma consulta externa foi feita e nenhuma atualização Power BI foi solicitada.
A demonstração bloqueia HTTP e só aceita PostgreSQL local em banco gestao_demo ou gestao_demo_*.
URLs com parâmetros adicionais são recusadas para impedir redirecionamento do host.

## Alterações desta etapa

- examples/synthetic.py: conjunto pequeno e determinístico de dados fictícios.
- scripts/run_demo.py: demonstração sem contas externas.
- scripts/run_tests.py: execução dos testes com relatório JSON e opção de exigir PostgreSQL.
- scripts/validate_postgres.py: cluster temporário em loopback, bancos exclusivos, captura de logs e encerramento.
- tests/test_postgresql.py: 14 casos de integração real.
- requirements-lock.txt: versões exatas validadas neste ambiente.
- .gitignore: exclusão dos ambientes adicionais e clusters de teste.
- docs/REPRODUCAO.md: procedimento de instalação e execução.
- Este relatório e a evidência JSON.

O código operacional em src/ não precisou de novas correções para os cenários testados.
README e portfólio não foram reformulados.

## Ajuste encontrado durante a reprodução

Na primeira tentativa, capturar pg_ctl por pipes no Windows manteve a comunicação bloqueada por handles herdados pelo processo do servidor.
O primeiro cluster foi explicitamente encerrado, e o controlador foi ajustado para redirecionar a saída para arquivos.
As duas execuções completas documentadas ocorreram com esse controle corrigido.
Esse ajuste pertence ao novo executor de validação; não altera o ETL.

## Limites

- Não comprova disponibilidade/contrato das APIs reais nem funcionamento do DOM de uma sessão autenticada no Power BI.
- Refresh continua sendo solicitação, não confirmação da conclusão.
- Valida cargas pequenas e funcionais; não é benchmark produtivo.
- Testado apenas em Windows/Python 3.12/PostgreSQL 18.6.
- Versões exatas do arquivo lock pressupõem disponibilidade dos pacotes no índice; não são um pacote offline de dependências.
- Não migra banco real preexistente nem elimina a necessidade de planejar migrações de schema.
- PostgreSQL usa autenticação trust somente no cluster efêmero local de dados fictícios; não é configuração de produção.

## Como repetir

Consulte [REPRODUCAO.md](REPRODUCAO.md).
Com PostgreSQL portátil disponível:
~~~powershell
.\.venv\Scripts\python.exe -X utf8 scripts/validate_postgres.py --pg-bin CAMINHO_DO_BIN --demo
~~~

O comando não considera testes PostgreSQL ignorados como uma validação completa.
Sem o cluster, a execução unitária informa os testes ignorados explicitamente.

## Prontidão

A lacuna de validação PostgreSQL registrada na Etapa 2 foi coberta para os cenários acima.
O projeto dispõe agora de demonstração reproduzível e evidências de testes no ambiente validado.
Após revisão e publicação desta entrega, pode avançar para documentação de apresentação, sem afirmar homologação em produção.

## Origem do runtime

Pacote PostgreSQL portátil disponibilizado pela EDB, distribuidor indicado na página Windows do PostgreSQL:
- https://www.postgresql.org/download/windows/
- https://www.enterprisedb.com/download-postgresql-binaries

O ZIP e o cluster não são incluídos no repositório nem no pacote de código.

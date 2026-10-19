# Etapa 2 — Correções técnicas implementadas

Base de comparação: main em da89a900cf30cf8c46b31523c75e56535fa2e50f.
Estado: implementação para revisão em branch separada; ainda não integrada à main.
Data: 19/10/2026.

## Resultado por problema

| Problema | Implementação |
|---|---|
| Notion não executado no fluxo principal | src/pipeline.py coleta Notion e Gestta na mesma execução antes de qualquer carga. |
| CSV antigo misturado com novo | Manifesto com run_id e hashes; PBI_OS.py rejeita pares não aprovados. Pipeline usa os frames da própria execução, não relê arquivos anteriores. |
| Extração Gestta parcial | Qualquer falha HTTP/contrato interrompe o lote; nenhum subprocesso é iniciado pelo extrator. Vazios de um período são aceitos; lote total vazio é bloqueado. Sinal explícito de paginação não suportada bloqueia a carga. |
| Notion vazio/malformado | Contrato results/has_more/next_cursor validado; cursor repetido bloqueado; lote vazio não chega ao banco. |
| Relações Notion incompletas | Paginação da propriedade relation e cache por execução; falha de página relacionada interrompe a coleta. IDs de propriedade não são codificados duas vezes. |
| Checklists parciais | Coletar todos os alvos antes de publicar; falhas e campos inválidos interrompem; done deve ser booleano, não string. |
| DROP VIEW CASCADE/replace | Removidos do caminho de carga. Uma Connection/transação publica tabelas e views; DELETE + append em tabelas estáveis preserva schema e dependentes. |
| CNPJ numérico | Texto desde CSV/normalização até SQL. Entrada numérica é rejeitada, sem inventar zeros. |
| Conversões silenciosas e joins | Datas/chaves inválidas são rejeitadas; IDs de tarefas e códigos Notion duplicados bloqueiam o lote; cardinalidade many_to_one verificada. LEFT JOIN e linhas sem correspondência são preservados e contados. |
| subprocess | Eliminado o encadeamento dentro de um extrator. O coordenador chama funções importáveis; exceção impede a etapa seguinte. Os scripts continuam com entrypoints próprios e erro de processo em falhas. |
| RPA duplicada e sucesso falso | Dois entrypoints mantidos e rotina compartilhada; timeout/dataset ausente geram erro; resultado indica requested e completion_verified=False. |
| Perfil Chrome ocupado | Lock próprio por diretório e detecção de Singleton*; nenhum lock do navegador é apagado. |
| Configuração/imports | Credenciais requeridas apenas quando usadas; importar módulos não chama API, abre navegador ou cria engine. load_dotenv centralizado. |
| Dependências | Faixas de compatibilidade para as bibliotecas usadas; imports/dependências diretas sem uso removidos. Instalação limpa em venv Python 3.12 concluída e pip check passou. |
| Referência residual | Rótulo de movimentação de pasta substituído por Etapa demonstrativa 26. Demais filtros, mapeamentos e nomes de views preservados. |

## Regras preservadas

- Doze períodos trimestrais abrangendo ano anterior, atual e seguinte, filtro e endpoints atuais do Gestta.
- API Notion 2022-06-28 mantida. Não foi presumida uma migração de versão.
- Colunas visíveis, mapeamentos português/inglês e traduções de status/tipo preservados; tradução de booleanos limitada às colunas indicadoras.
- Tabelas notion_folha, notion_dados, gestta_relatorios e cs_check mantidas.
- Views bi_final, Worflow_CS, Worflow_CS_novo e bi_operacional mantidas, com filtros e datas existentes.
- LEFT JOIN por código do cliente preservado, sem deduplicação arbitrária.
- Filtro de onboarding por nome do cliente/Etapa 01 preservado; mudança de chave de negócio não foi introduzida.
- RPA solicita atualização: não afirma que a atualização terminou.

## Mudanças de comportamento intencionais

- Use python src/pipeline.py como entrada coordenada. Checklists e Power BI são opcionais explícitos, por --checklists e --refresh-powerbi.
- Executar só um extrator não executa o restante do ETL.
- PBI_OS.py independente exige o manifesto de um snapshot aprovado; CSVs avulsos/alterados não são aceitos silenciosamente.
- Falhas e vazios não apagam a última carga. Não há modo de ignorar falhas e publicar subconjuntos.
- Schema existente incompatível causa erro de migração necessária; nenhum banco existente é alterado automaticamente para converter CNPJ numérico em texto.
- A chave de cliente precisa ser inteira e não nula; CNPJ e ID de tarefa precisam chegar como texto.
- Duplicatas não são removidas arbitrariamente. A regra de eventual repetição legítima precisa ser definida antes de permiti-la.

## Publicação e atomicidade

O PostgreSQL é a referência da carga confirmada. Todas as tabelas gerenciadas e a criação/atualização das views usam uma transação.
Tipos e colunas existentes são conferidos antes da escrita em cada tabela; incompatibilidades fazem rollback da transação.
Não há DROP TABLE, DROP VIEW CASCADE ou to_sql replace no caminho de publicação.
O lock de sessão do pipeline e o lock transacional de publicação usam chaves distintas para evitar bloqueio do próprio processo.
Schema de publicação PostgreSQL fixado em public; locks concorrentes geram falha em vez de espera indefinida.

Arquivos e banco não constituem transação distribuída:
1. preparar arquivos temporários;
2. confirmar a transação de banco;
3. renomear arquivos e, por último, publicar o manifesto;
4. solicitar RPAs apenas se a publicação tiver terminado.

Se a publicação dos arquivos falhar após o commit, a execução falha com banco_confirmado=True, não inicia RPAs e não publica um novo manifesto completo.
Um arquivo individual pode já ter sido atualizado. O leitor do snapshot verifica hashes e rejeita o par inconsistente.
Isso evita consumo silencioso; não equivale a rollback distribuído.

## Testes efetivamente executados

- 58 testes passaram: cinco existentes e 53 novos.
- HTTP simulado e bloqueio de rede real nos testes.
- Chrome simulado; nenhum perfil autenticado foi utilizado.
- Banco SQLite local: rollback de dados existentes, falha na segunda tabela, falha em instrução de view, repetição da carga, preservação de view consumidora e bloqueio de schema CNPJ numérico.
- Pipeline sintético: arquivos CSV/JSON/Excel, manifesto, falhas de fonte/banco/arquivo, limpeza de temporários e bloqueio de RPAs.
- Integração local do pipeline com tabelas SQLite reais: duas execuções, uma view de join adaptada ao dialecto SQLite, contagens estáveis e CNPJ textual preservado. Não valida o DDL PostgreSQL das quatro views.
- Subprocesso local comprova saída não zero do entrypoint RPA diante de falha simulada.
- python src/pipeline.py --help executado sem credenciais.
- pip check: nenhuma dependência quebrada.

Ambiente instalado do zero:
- Python 3.12.14
- pandas 2.3.3
- SQLAlchemy 2.1.5
- requests 2.34.2
- psycopg2-binary 2.9.13
- python-dotenv 1.2.4
- selenium 4.51.0
- openpyxl 3.1.5

Comandos:
    python -X utf8 -m unittest discover -s tests -v
    python -m pip check
    python src/pipeline.py --help

## Limites e pendências reais

- Não há servidor PostgreSQL, psql ou Docker instalado/disponível nesta máquina. Não foi executada prova de rollback de DDL, locks/advisory locks ou CREATE OR REPLACE VIEW no motor PostgreSQL. SQLite não substitui essa evidência.
- Não foram feitas chamadas a Gestta/Notion/Power BI nem usada qualquer credencial corporativa.
- O contrato efetivo do endpoint Gestta e a compatibilidade da versão Notion com uma base real precisam de validação autorizada; erros são bloqueados, não escondidos.
- Migração de schemas preexistentes incompatíveis deve ser planejada com cópia e validação de dados. O código falha de modo seguro até isso ser feito.
- Confirmação de conclusão do refresh Power BI permanece fora da funcionalidade implementada; somente a solicitação é reportada.
- Validação de instalação em outros sistemas/Python e teste integral PostgreSQL com dados fictícios pertencem à Etapa 3.
- Próximo marco: revisão da proposta de alteração e aprovação antes da integração à main.

## Prontidão

Correções locais e testes de regressão estão concluídos. Há base para iniciar a Etapa 3 de validação ponta a ponta com PostgreSQL isolado.
Não apresentar o projeto como validado em produção nem como possuidor de transação distribuída.
README e portfólio não foram reformulados.

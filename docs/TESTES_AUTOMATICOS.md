# Testes automáticos no GitHub

O fluxo `.github/workflows/tests.yml` executa em propostas destinadas à `main`,
em envios à `main` e manualmente pela aba Actions após sua integração.

O runner Ubuntu 24.04 prepara Python 3.12, instala `requirements-lock.txt`,
verifica as dependências e executa a suíte com `--require-postgresql`.
Um container PostgreSQL 18 descartável atende somente pela interface local
do runner. Não configure segredos corporativos: o usuário `gestao_test` e a
autenticação trust pertencem exclusivamente a esse ambiente fictício e efêmero.
Essa configuração não deve ser usada em produção.

Os testes criam bancos próprios, verificam cargas, rollback, concorrência e a
demonstração fictícia. As chamadas HTTP das integrações são simuladas ou
bloqueadas. O fluxo precisa de rede para baixar código, dependências e a imagem
PostgreSQL; isso não implica acesso a sistemas corporativos.

O job falha se houver falhas, erros ou testes ignorados. A contagem acompanha a
suíte existente, sem exigir um número fixo que impediria acrescentar testes.
O resumo da execução informa as contagens; a saída completa fica nos logs da
aba Actions. Falhas na instalação ou antes da geração do resultado aparecem
como validação incompleta. O limite de execução é de 15 minutos.

As ações de checkout e preparação do Python estão fixadas por commit. A imagem
`postgres:18` acompanha atualizações da versão principal 18; a versão exata
utilizada aparece no log. O fluxo tem permissão de leitura do repositório e não
publica artefatos, dados, commits ou alterações no banco de produção.

## Estado da validação

A suíte anterior foi aprovada localmente no Windows com PostgreSQL real.
A configuração deste fluxo passou na validação local do actionlint 1.7.12
(sem ShellCheck ou pyflakes), na leitura do YAML e na conferência da sintaxe
Python do resumo. Também foram conferidos os gatilhos, a permissão de leitura,
o vínculo à interface local e a exigência dos testes PostgreSQL.
A execução no GitHub/Linux foi posteriormente aprovada após integração à
`main`: [registro verificável](https://github.com/GabrielTIAlef/gestao_geral/actions/runs/39342727864).
Instalação, verificação de dependências e suíte com PostgreSQL obrigatório
foram concluídas com sucesso.

Em cada nova proposta, acompanhe o check **Python 3.12 e PostgreSQL 18**.
Se estiver vermelho, consulte o primeiro passo com falha antes de integrar.

Este fluxo não torna o check obrigatório para merge. Essa regra depende de uma
configuração separada de proteção da branch e não foi alterada nesta entrega.

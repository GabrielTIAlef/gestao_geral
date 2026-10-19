# Configuração e resposta à exposição

## Configuração local autorizada
1. Instale requirements.txt em um ambiente virtual.
2. Copie .env.example para .env na raiz e configure apenas contas sob sua autorização.
3. Use uma senha nova de banco; nunca reutilize a senha publicada.
4. Execute os scripts a partir da raiz. Caminhos relativos de configuração são resolvidos pela raiz do projeto.
5. Configure os dois nomes de dataset e um perfil Chrome exclusivo, sem copiar sessões de terceiros.
6. Para provisionar um novo token autorizado, execute python src/automacao/LoginGestta.py. A entrada fica oculta e o arquivo existente não é sobrescrito.
7. Restrinja as permissões de .env, secrets/, data/, logs/ e do perfil Chrome à conta executora. No Windows, configure as ACLs.
8. A extração Notion produz o CSV configurado em NOTION_CSV_PATH, consumido pela transformação.

O provisionamento manual substitui a antiga captura por interface e clipboard.
O token continua sendo armazenado em texto: não compartilhe o arquivo.
As exportações podem conter dados pessoais, fiscais, nomes e links de documentos; não publique dados reais.
Os checklists e campos específicos desta versão pública foram substituídos por exemplos fictícios; não correspondem à configuração de uma operação real.

## Credenciais históricas
Uma senha PostgreSQL estava presente em versões anteriores de três scripts.
Remover a senha da versão atual não revoga a credencial nem apaga o histórico.
O responsável pela conta deve trocar a senha, verificar reutilização, revisar logs e avaliar encerramento de sessões.
Não é necessário testar a credencial publicada para tratá-la como exposta.

Tokens Notion/Gestta e webhooks Slack não foram encontrados literalmente na inspeção de main;
avalie outros repositórios, logs e cópias antes de concluir que não houve exposição.
Revogue tokens, webhooks e sessões de navegador se expostos ou sem autorização atual.
Credenciais e sessões de uma empresa anterior devem ser tratadas pelo TI/segurança da empresa.
Não faça login nem rotacione contas de terceiros por conta própria.

## Limites
Esta correção não reescreve histórico, revoga credenciais, encerra sessões ou atesta ausência de uso indevido.
A limpeza do histórico exige planejamento, confirmação e coordenação com quem possui clones.
Não publique segredos em issues, PRs, comentários ou capturas de tela.
Referência: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository

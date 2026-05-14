#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import io
import pandas as pd
from sqlalchemy import create_engine, text

# Configuração e conexão ao BD
DB_CONFIG = {
    "usuario": "postgres",
    "senha": "123456",
    "host": "localhost",
    "porta": "5432",
    "banco": "ProjetoImport"
}
def conectar_banco():
    url = f"postgresql+psycopg2://{DB_CONFIG['usuario']}:{DB_CONFIG['senha']}@{DB_CONFIG['host']}:{DB_CONFIG['porta']}/{DB_CONFIG['banco']}"
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            print("✅ Conexão bem-sucedida ao banco de dados.")
        return engine
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
        raise

# Ciclo começa apagando as views para dar replace nas tabelas
def apagar_views(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS bi_final CASCADE"))
        conn.execute(text('DROP VIEW IF EXISTS "Worflow_CS" CASCADE'))
        conn.execute(text('DROP VIEW IF EXISTS Worflow_CS_novo CASCADE'))
        conn.execute(text('DROP VIEW IF EXISTS bi_isis CASCADE'))
print("✅ Views apagadas.")

# Puxa o CSV criado no script "gestta_relatorios" traz os dados do Gestta e faz as transformações necessárias na base
def limpar_e_carregar_gestta_relatorios(engine):
    df = pd.read_csv(r"C:\Users\Gabriel Alef\Projeto\dados\gestta_relatorios.csv", sep=',')
    # Exclusão de colunas não usadas
    colunas_excluir = [
        "company_task.score", "owner.role", "due_iso_week", "value", "concluded_by.role",
        "customer.company_groupers", "customer.state_regime", "customer.municipal_regime", "note",
        "score", "customer.federal_regime", "_forever", "customer.state_regime.name",
        "customer.municipal_regime.name", "customer.monthly_payment", "company.name", "company.status","owner"
    ]
    # Renomeação do inglês para português
    df = df.drop(columns=colunas_excluir, errors='ignore')
    novo_nome = {
        "company.created_at": "data_criação_completa_empresa",
        "name": "Tarefa - Nome",
        "company_department.name": "Empresa - Departamento",
        "type": "Tarefa - Tipo",
        "subtype": "Tarefa - Subtipo",
        "status": "Tarefa - Status",
        "owner.name": "Tarefa - Responsável",
        "notify_customer": "Tarefa - Notifica Cliente?",
        "fine": "Tarefa - Gera Multa?",
        "_due_date": "tarefa__data_de_vencimento_(completa)",
        "downloaded": "Tarefa - Baixada?",
        "done_overdue": "Tarefa - Concluída em Atraso",
        "done_fine": "Tarefa - Concluída com Multa",
        "created_at": "data_criação_completa",
        "concluded_by.name": "Tarefa - Concluído por",
        "conclusion_date": "Tarefa - Data de conclusão (completa)",
        "id": "Tarefa - ID",
        "overdue": "Tarefa - Atrasada?",
        "on_time": "Tarefa - No prazo?",
        "customer.federal_regime.name": "Cliente - Regime federal",
        "customer.name": "Cliente - Nome",
        "customer.cnpj": "Cliente - CNPJ",
        "customer.active": "Cliente - Ativo?",
        "customer.code": "Cliente - Código",
        "legal_date": "data_legal"
    }
    df = df.rename(columns=novo_nome)
    # Normalização dos nomes das colunas
    df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_').str.replace(r'[.\-?]', '', regex=True)
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
    # Normalização dos tipos dos dados
    df['cliente__código'] = pd.to_numeric(df['cliente__código'], errors='coerce')
    df['cliente__cnpj'] = pd.to_numeric(df['cliente__cnpj'], errors='coerce')
    # Transformação de idioma de alguns valores
    replace_dict = {
        "SERVICE_ORDER" : "Solicitações de serviço",
        "RECURRENT" : "Recorrentes",
        "DISCONSIDERED": "Desconsideradas",
        "DONE": "Concluídas",
        "IMPEDIMENT": "Impedimentos",
        "OPEN": "Abertas",
        "AUTOMATIC": "Recorrentes automáticas",
        "FREE": "Ordens de serviço livres",
        "MANUAL": "Recorrentes manuais",
        "TEMPLATE": "Ordens de serviço padronizadas",
        "WORKFLOW": "Workflows",
         True: "Sim",
         False: "Não"
    }
    df = df.replace(replace_dict)
    # Transformação nas colunas de data
    colunas_data = [
        'data_criação_completa_empresa', 
        'tarefa__data_de_vencimento_(completa)', 
        'data_criação_completa', 
        'tarefa__data_de_conclusão_(completa)', 
        'data_legal'
    ]
    for col in colunas_data:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
    # Carregamento da base tratada para o BD
    df.to_sql('gestta_relatorios', engine, if_exists='replace', index=False)
    print("✅ Tabela gestta_relatorios carregada.")

# Puxa o CSV criado no script "PBI_OS" traz os dados do Notion e faz algumas transformações
def limpar_e_carregar_notion_dados(engine):
    df = pd.read_csv(r"C:\Users\Gabriel Alef\Projeto\dados\base_notion.csv", sep=',', na_values=['Sem dado'], dtype_backend = "numpy_nullable")
    # Transformação do tipo da coluna
    df['Código Domínio'] = pd.to_numeric(df['Código Domínio'], errors = 'coerce')
    # Normalização dos nomes das colunas
    df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')
    df['gestão_de_clientes'] = df['gestão_de_clientes'].str.split('(').str[0].str.strip()
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
    # Carregamento da base tratada para o BD
    df.to_sql('notion_dados', engine, if_exists='replace', index=False)
    print("✅ Tabela notion_dados carregada.")

# Criação das views
def criar_views(engine):
    with engine.begin() as conn:    
        # View principal da base, que faz o merge entre os dados do Gestta e do Notion
        conn.execute(text("""
            CREATE OR REPLACE VIEW bi_final AS
            SELECT 
                g.*, 
                n.*
            FROM gestta_relatorios g
            LEFT JOIN notion_dados n 
                ON g.cliente__código = n.código_domínio;
        """))
    print("✅ Views bi_final criadas.")
    with engine.begin() as conn:        
        # View usada no novo painel do CS com as tarefas específicas 
        conn.execute(text("""
            CREATE OR REPLACE VIEW Worflow_CS_novo AS
            SELECT 
                g.*,
                n."gestão_de_clientes"
            FROM public.gestta_relatorios g
            LEFT JOIN public.notion_dados n
                ON g."cliente__código" = n."código_domínio"
            WHERE g."tarefa__nome" IN (
                'Documentos obrigatórios processo de entrada - CS',
                'Documentos independentes do cliente - CS',
                'Documentos dependentes do cliente - CS',
                'Agendar reuniões - CS',
                'Realizar Onboarding de CS',
                'Organizar documentação inicial do cliente',
                'Transferir Contador responsável',
                'Conferência de transferência de contador',
                'Conferir documentos recebidos - CS',
                'Formalizar ao cliente os documentos recebidos',
                'Mover pasta do cliente para “Clientes Ativos” (Drive)'
            )
        """))
    print("✅ Views Worflow_CS_novo criadas.")
    with engine.begin() as conn:     
        # View usada no antigo painel do CS com as tarefas específicas 
        conn.execute(text("""
            CREATE OR REPLACE VIEW "Worflow_CS" AS
            SELECT  
                g.tarefa__status,
                g.tarefa__nome,
                g.tarefa__responsável,
                g."data_criação_completa",
                g.tarefa__id,
                g.cliente__CNPJ,
                g.cliente__nome,
                g.cliente__código,
                g.cliente__ativo
            FROM public.gestta_relatorios g
            WHERE g.tarefa__nome IN ( 
                    '2.1. Organização da Entrada do Cliente',
                    '2.1. Cadastro de Cliente | Domínio | Folha',
                    '2.1. Cadastro de Cliente | Domínio | Fiscal',
                    '2.1. Cadastro de Cliente | Gestta | Fiscal',
                    '2.1. Cadastro de Cliente | Domínio | Contábil',
                    '2.1. Cadastro de Cliente | Gestta | Contábil',
                    '2.1. Cadastro de Cliente | Gestta | Folha',
                    '2.1. Atualizar Cadastro do Cliente na Domínio',
                    '2.1. Conferir Documentação - Contabilidade Anterior',
                    '2.1. Mover Pasta do Cliente para Clientes Ativos (Dropbox)',
                    '2.1. Transferir contador responsável',
                    '2.1. Organizar Documentação Inicial do Cliente',
                    '2.1. Mapeamento do Cliente',
                    '2.1. Passagem de Bastão do Cliente | Folha',
                    '2.1. Passagem de Bastão do Cliente | Fiscal'
                )
              AND g."data_criação_completa" >= DATE '2025-07-01'
              AND EXISTS (
                  SELECT 1
                  FROM public.gestta_relatorios g2
                  WHERE g2."cliente__nome" = g."cliente__nome"
                    AND g2."tarefa__nome" = '2.1. Organização da Entrada do Cliente'
              );
            """))
    print("✅ Views Worflow_CS criadas.")
    with engine.begin() as conn: 
        # View usada no proejto da Ísis
        conn.execute(text("""
            CREATE OR REPLACE VIEW "bi_isis" AS
            SELECT 
                "tarefa__nome", "tarefa__subtipo", "data_criação_completa", "tarefa__id", "cliente__nome", "cliente__código" 
            FROM gestta_relatorios
            WHERE
                "tarefa__subtipo" = 'Ordens de serviço padronizadas'
                AND
                "data_criação_completa" > '2026-01-28';
        """))
    print("✅ Views bi_isis criadas.")

# Exportação para Excel
def exportar_excel(engine):
    df = pd.read_sql("SELECT * FROM bi_final", engine)
    df.to_excel(r"C:\Users\Gabriel Alef\Projeto\dados\projeto_bi.xlsx", index=False)
    print("✅ Exportado para Excel com sucesso.")

def main():
    engine = conectar_banco()
    apagar_views(engine)
    limpar_e_carregar_gestta_relatorios(engine)
    limpar_e_carregar_notion_dados(engine)
    criar_views(engine)
    exportar_excel(engine)
if __name__ == "__main__":
    main()


# In[ ]:





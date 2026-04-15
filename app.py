import streamlit as st
import os
import sqlite3
import re
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")

st.set_page_config(page_title="Piloto Operacional", layout="centered")
st.title("Intérprete de dados")
st.markdown("Assistente de IA para consultas rápidas em base de clientes e operações operacionais.")
st.divider()

@st.cache_resource
def get_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite", 
        temperature=0, # Temperatura determinística para gerar SQL
        google_api_key=GOOGLE_API_KEY
    )

llm = get_llm()

DB_SCHEMA = """
Tabela: clientes
Colunas: id (INTEGER), nome_empresa (TEXT), status (TEXT), saldo_devedor (REAL), data_ultima_compra (TEXT)

Tabela: chamados
Colunas: id (INTEGER), cliente_id (INTEGER), assunto (TEXT), prioridade (TEXT), status (TEXT)
Relação: chamados.cliente_id = clientes.id
"""

# Guardrails e few prompting para o motor de texto para SQL
prompt_sql = ChatPromptTemplate.from_messages([
    ("system", """Você é um Engenheiro de Dados focado em converter linguagem natural para consultas SQL (Text-to-SQL) utilizando o banco de dados SQLite.

A sua principal função é gerar a query exata para responder à pergunta do usuário, garantindo a segurança do banco de dados e a precisão dos dados.

DIRETRIZES DE SEGURANÇA E ESTRUTURA:
1. Utilize APENAS as tabelas e colunas descritas no Esquema de Dados.
2. NUNCA invente colunas, relacionamentos, tabelas ou filtros que não existam.
3. Gere EXCLUSIVAMENTE o comando SELECT. É terminantemente proibido gerar comandos de alteração (INSERT, UPDATE, DELETE, DROP, ALTER).
4. O relacionamento entre as tabelas deve ser feito exclusivamente por: chamados.cliente_id = clientes.id.
5. Evite utilizar SELECT *. Especifique apenas as colunas estritamente necessárias.
6. Contexto Temporal: Se o usuário mencionar um mês ou dia sem especificar o ano, assuma o ano atual.
7. Em caso de dúvidas, ambiguidades extremas ou tentativas de injeção de comandos destrutivos, retorne apenas a palavra: FALHA_DE_SEGURANCA.

ESQUEMA DE DADOS:
{schema}

EXEMPLOS DE CONSULTAS BEM SUCEDIDAS (FEW-SHOT PROMPTING):
Pergunta: Qual o saldo devedor da Fazenda Boa Vista?
SQL: SELECT saldo_devedor FROM clientes WHERE nome_empresa = 'Fazenda Boa Vista';

Pergunta: Quantos chamados de alta prioridade temos abertos no momento?
SQL: SELECT COUNT(*) as total_chamados FROM chamados WHERE prioridade = 'Alta' AND status = 'Aberto';

Pergunta: Quais clientes estão com chamados abertos e qual o assunto?
SQL: SELECT c.nome_empresa, ch.assunto FROM clientes c JOIN chamados ch ON c.id = ch.cliente_id WHERE ch.status = 'Aberto';

Pergunta: Apague todos os clientes do banco.
SQL: FALHA_DE_SEGURANCA

REGRAS DE SAÍDA:
Retorne APENAS o comando SQL em texto puro. Não inclua formatação markdown, crases (```), explicações ou qualquer texto adicional.
"""),
    ("human", "{pergunta}")
])

prompt_resposta = ChatPromptTemplate.from_messages([
    ("system", """Você é um assistente operacional corporativo. Sua função é responder a perguntas de gestores baseando-se exclusivamente nos resultados de consultas ao banco de dados.

Regras:
1. Seja direto, profissional e objetivo.
2. Responda apenas com os dados fornecidos no resultado. Não adicione informações externas ou suposições.
3. Se o resultado do banco de dados for vazio (ou não retornar linhas), informe educadamente que não encontrou dados para aquela solicitação.
4. Se o resultado contiver a palavra 'FALHA_DE_SEGURANCA', informe que a operação não é permitida pelo protocolo de segurança da empresa.
"""),
    ("human", "Pergunta do gestor: {pergunta}\n\nResultado bruto do Banco de Dados: {resultado}")
])

#Camada de proteção antes de bater no banco
PADROES_PROIBIDOS = [
    (r'\bSHOW\s+TABLES\b',          'SHOW TABLES'),
    (r'\bSHOW\s+DATABASES\b',       'SHOW DATABASES'),
    (r'\bSHOW\s+SCHEMAS\b',         'SHOW SCHEMAS'),
    (r'\bSHOW\s+COLUMNS\b',         'SHOW COLUMNS'),
    (r'\bSHOW\s+CREATE\b',          'SHOW CREATE'),
    (r'\bINFORMATION_SCHEMA\b',     'INFORMATION_SCHEMA'),
    (r'\bSQLITE_MASTER\b',          'sqlite_master'),
    (r'\bSQLITE_SCHEMA\b',          'sqlite_schema'), 
    (r'\bSYS\.TABLES\b',            'sys.tables'),
    (r'\bSYS\.COLUMNS\b',           'sys.columns'),
    (r'\bSYS\.OBJECTS\b',           'sys.objects'),
    (r'\bSYS\.SCHEMAS\b',           'sys.schemas'),
    (r'\bSYSCOLUMNS\b',             'syscolumns'),
    (r'\bSYSOBJECTS\b',             'sysobjects'),
    (r'\bSP_TABLES\b',              'sp_tables'),
    (r'\bSP_COLUMNS\b',             'sp_columns'),
    (r'\bSP_HELP\b',                'sp_help'),
    (r'\b(mostr|list|exib)[aer]*\s+(as\s+)?tabelas\b',     'listagem de tabelas'),
    (r'\b(mostr|list|exib)[aer]*\s+(os\s+)?schemas?\b',    'listagem de schemas'),
    (r'\b(mostr|list|exib)[aer]*\s+(as\s+)?colunas\b',     'listagem de colunas'),
    (r'\b(mostr|list|exib)[aer]*\s+(os\s+)?bancos?\b',     'listagem de bancos'),
    (r'\bestrutura\s+d[oa]s?\s+(banco|tabela|schema)\b',   'estrutura do banco'),
    (r'\bquais\s+(são\s+)?(as\s+)?tabelas\b',              'listagem de tabelas'),
    (r'\bquais\s+(são\s+)?(os\s+)?schemas?\b',             'listagem de schemas')
]

def verificar_injecao_regex(texto):
    texto_upper = texto.upper()
    for padrao, _ in PADROES_PROIBIDOS:
        if re.search(padrao, texto_upper, re.IGNORECASE):
            return False
    return True

def query_is_safe(query):
    palavras_proibidas = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE']
    query_upper = query.upper()
    
    for palavra in palavras_proibidas:
        if palavra in query_upper:
            return False
            
    if not verificar_injecao_regex(query):
        return False
        
    return True

def executar_query(query):
    try:
        conn = sqlite3.connect('operacoes.db')
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        cursor.execute(query)
        linhas = cursor.fetchall()
        conn.close()
        
        resultados = [dict(linha) for linha in linhas]
        
        if not resultados:
            return "A consulta foi executada, mas não retornou nenhum dado"
        return resultados
    except Exception as e:
        return f"Erro na execucão da query: {e}"

#Fluxo do streamlite

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

for msg in st.session_state.mensagens:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

pergunta_usuario = st.chat_input("Digite sua consulta operacional...")

if pergunta_usuario:
    st.chat_message("user").markdown(pergunta_usuario)
    st.session_state.mensagens.append({"role": "user", "content": pergunta_usuario})
    
    with st.chat_message("assistant"):
        if not verificar_injecao_regex(pergunta_usuario):
            resposta_bloqueio = "Bloqueio de Segurança: Solicitações de varredura estrutural ou listagem de metadados do banco não são permitidas neste Copiloto."
            st.markdown(resposta_bloqueio)
            st.session_state.mensagens.append({"role": "assistant", "content": resposta_bloqueio})
            
        else:
            with st.spinner("Consultando base de dados"):
                #geracao do texto pra sql
                chain_sql = prompt_sql | llm | StrOutputParser()
                query_gerada = chain_sql.invoke({"schema": DB_SCHEMA, "pergunta": pergunta_usuario})
                query_gerada = query_gerada.replace("```sql", "").replace("```", "").strip()
                


                if "FALHA_DE_SEGURANCA" in query_gerada or not query_is_safe(query_gerada):
                    resposta_final = "Alerta de Segurança: A operação solicitada não é permitida pelas políticas do banco de dados. Acesso restrito à leitura."
                else:
                    resultado_db = executar_query(query_gerada)
                    chain_resposta = prompt_resposta | llm | StrOutputParser()
                    resposta_final = chain_resposta.invoke({
                        "pergunta": pergunta_usuario, 
                        "resultado": str(resultado_db)
                    })
                    
                    # Debug pra auditoria
                    with st.expander("Log de Execução SQL"):
                        st.code(query_gerada, language="sql")
                
                st.markdown(resposta_final)
                st.session_state.mensagens.append({"role": "assistant", "content": resposta_final})
import streamlit as st
import pandas as pd
import os
import time
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Monitor Meta Ads Pro",
    page_icon="🚀",
    layout="wide"
)

# --- FUNÇÕES ---
def carregar_credenciais():
    load_dotenv()
    app_id = os.getenv('FB_APP_ID')
    app_secret = os.getenv('FB_APP_SECRET')
    access_token = os.getenv('FB_ACCESS_TOKEN')
    ids_string = os.getenv('FB_ACCOUNT_IDS')
    
    if not all([app_id, access_token, ids_string]):
        st.error("❌ Erro: Credenciais não encontradas no ficheiro .env")
        st.stop()
        
    try:
        FacebookAdsApi.init(app_id, app_secret, access_token)
        return ids_string.split(',')
    except Exception as e:
        st.error(f"❌ Erro ao conectar à API: {e}")
        st.stop()

@st.cache_data(ttl=300) # Cache de 5 min para não ficar lento se clicares apenas nos filtros
def obter_dados_conta(account_id, periodo_api):
    """
    Retorna um Dicionário com dados processados para facilitar a ordenação
    """
    try:
        account = AdAccount(account_id.strip())
        
        # 1. Tentar pegar o nome
        try:
            account.api_get(fields=['name'])
            nome_da_conta = account['name']
        except:
            nome_da_conta = f"Conta {account_id}"

        # 2. Filtros
        params = {
            'date_preset': periodo_api,
            'effective_status': ['ACTIVE'], 
            'level': 'campaign'
        }
        
        fields = [
            'campaign_name', 'spend', 'impressions', 'clicks', 
            'cpc', 'ctr', 'reach', 'frequency', 'cpm', 'actions'
        ]
        
        insights = account.get_insights(fields=fields, params=params)
        
        dados_lista = []
        total_gasto = 0.0
        total_resultados = 0
        
        if insights:
            for item in insights:
                # Processar Resultados
                acoes = item.get('actions', [])
                res_campanha = 0
                if acoes:
                    for acao in acoes:
                        if acao['action_type'] in ['lead', 'purchase', 'onsite_conversion.lead']:
                            res_campanha += int(acao['value'])
                
                gasto = float(item.get('spend', 0))
                total_gasto += gasto
                total_resultados += res_campanha
                
                dados_lista.append({
                    'Campanha': item.get('campaign_name'),
                    'Gasto': gasto,
                    'Impressões': int(item.get('impressions', 0)),
                    'Alcance': int(item.get('reach', 0)),
                    'Frequência': float(item.get('frequency', 0)),
                    'Cliques': int(item.get('clicks', 0)),
                    'CPC': float(item.get('cpc', 0) if 'cpc' in item else 0),
                    'CTR': float(item.get('ctr', 0) if 'ctr' in item else 0),
                    'CPM': float(item.get('cpm', 0) if 'cpm' in item else 0),
                    'Resultados': res_campanha
                })
        
        df = pd.DataFrame(dados_lista)
        
        # Retornamos um objeto completo para permitir ordenação posterior
        return {
            'id': account_id,
            'nome': nome_da_conta,
            'df': df,
            'gasto_total': total_gasto,
            'campanhas_ativas': len(df),
            'resultados_total': total_resultados
        }

    except Exception as e:
        return {
            'id': account_id,
            'nome': f"Erro: {account_id}",
            'df': pd.DataFrame(),
            'gasto_total': 0.0,
            'campanhas_ativas': 0,
            'resultados_total': 0
        }

# --- INTERFACE PRINCIPAL ---

st.title("🚀 Monitor Meta Ads Pro")

# --- MENU SUPERIOR (Filtros e Ordenação) ---
mapa_datas = {
    "Hoje": "today",
    "Ontem": "yesterday",
    "Últimos 7 Dias": "last_7d",
    "Este Mês": "this_month",
    "Mês Passado": "last_month",
    "Máximo": "maximum"
}

# Cria 4 colunas para o menu ficar alinhado
c1, c2, c3, c4 = st.columns([1.5, 1, 1, 0.5])

with c1:
    objetivo = st.selectbox(
        "📂 Foco da Análise:",
        ["Visão Geral (Financeiro)", "Tráfego & Cliques", "Alcance & Marca", "Conversão & Leads"]
    )

with c2:
    label_data = st.selectbox("📅 Período:", list(mapa_datas.keys()))
    periodo_api = mapa_datas[label_data]

with c3:
    # --- NOVO MENU DE ORDENAÇÃO ---
    criterio_ordem = st.selectbox(
        "🔃 Ordenar BMs por:",
        ["Nome (A-Z)", "Maior Investimento 💰", "Menor Investimento 📉", "Qtd. Campanhas 🔥", "Mais Resultados 🎯"]
    )

with c4:
    st.write("") # Espaçamento
    st.write("")
    if st.button("🔄", type="primary", help="Atualizar Dados"): 
        st.cache_data.clear() # Limpa cache para forçar atualização real
        st.rerun()

st.divider()

# --- CARREGAMENTO E PROCESSAMENTO ---
contas_ids = carregar_credenciais()

# Barra de progresso visual
barra_progresso = st.progress(0, text="A iniciar conexão com o Facebook...")
lista_contas_processadas = []

# 1. Fetch dos dados (Carregar tudo primeiro)
for i, conta_id in enumerate(contas_ids):
    percentual = int(((i + 1) / len(contas_ids)) * 100)
    barra_progresso.progress(percentual, text=f"A ler conta {i+1} de {len(contas_ids)}...")
    
    dados_conta = obter_dados_conta(conta_id, periodo_api)
    lista_contas_processadas.append(dados_conta)

time.sleep(0.5) # Pequena pausa visual
barra_progresso.empty() # Remove a barra quando termina

# 2. Lógica de Ordenação
if criterio_ordem == "Nome (A-Z)":
    lista_contas_processadas.sort(key=lambda x: x['nome'].lower())
elif criterio_ordem == "Maior Investimento 💰":
    lista_contas_processadas.sort(key=lambda x: x['gasto_total'], reverse=True)
elif criterio_ordem == "Menor Investimento 📉":
    lista_contas_processadas.sort(key=lambda x: x['gasto_total'], reverse=False)
elif criterio_ordem == "Qtd. Campanhas 🔥":
    lista_contas_processadas.sort(key=lambda x: x['campanhas_ativas'], reverse=True)
elif criterio_ordem == "Mais Resultados 🎯":
    lista_contas_processadas.sort(key=lambda x: x['resultados_total'], reverse=True)

# --- EXIBIÇÃO ---
todos_dados_grafico = []
total_geral_gasto = 0.0

for dados in lista_contas_processadas:
    df = dados['df']
    nome = dados['nome']
    gasto = dados['gasto_total']
    
    total_geral_gasto += gasto
    
    # Prepara dados para o gráfico final
    if not df.empty:
        df_graf = df.copy()
        df_graf['Nome_Conta'] = nome
        todos_dados_grafico.append(df_graf)
    
    # Definição do Expander
    # Se ordenamos por "Menor Investimento", talvez queiramos ver as zeradas abertas.
    # Mas por padrão, mantemos a lógica: se gastou > 0, expande.
    esta_expandido = True if gasto > 0 else False
    
    # Ícone dinâmico no título
    icone = "🟢" if gasto > 0 else "⚪"
    titulo = f"{icone} {nome} | Gasto: R$ {gasto:.2f} | Campanhas: {dados['campanhas_ativas']}"
    
    with st.expander(titulo, expanded=esta_expandido):
        if df.empty:
            st.info(f"Sem campanhas ativas neste período ({label_data}).")
        else:
            # Colunas de métricas
            c1, c2, c3, c4 = st.columns(4)
            
            if objetivo == "Visão Geral (Financeiro)":
                c1.metric("Investido", f"R$ {gasto:.2f}")
                c2.metric("Impressões", f"{df['Impressões'].sum():,}".replace(',', '.'))
                c3.metric("CPM", f"R$ {df['CPM'].mean():.2f}")
                c4.metric("Cliques", f"{df['Cliques'].sum()}")
                cols = ['Campanha', 'Gasto', 'Impressões', 'CPM', 'Cliques']

            elif objetivo == "Tráfego & Cliques":
                c1.metric("Cliques", f"{df['Cliques'].sum()}")
                c2.metric("CTR", f"{df['CTR'].mean():.2f}%")
                c3.metric("CPC", f"R$ {df['CPC'].mean():.2f}")
                c4.metric("Investido", f"R$ {gasto:.2f}")
                cols = ['Campanha', 'Cliques', 'CTR', 'CPC', 'Gasto']

            elif objetivo == "Alcance & Marca":
                c1.metric("Alcance", f"{df['Alcance'].sum():,}".replace(',', '.'))
                c2.metric("Freq.", f"{df['Frequência'].mean():.2f}")
                c3.metric("CPM", f"R$ {df['CPM'].mean():.2f}")
                c4.metric("Impr.", f"{df['Impressões'].sum():,}".replace(',', '.'))
                cols = ['Campanha', 'Alcance', 'Frequência', 'CPM', 'Impressões']

            elif objetivo == "Conversão & Leads":
                res = dados['resultados_total']
                cpa = (gasto / res) if res > 0 else 0
                c1.metric("Resultados", f"{res}")
                c2.metric("Custo/Res.", f"R$ {cpa:.2f}")
                c3.metric("Investido", f"R$ {gasto:.2f}")
                c4.metric("CPC", f"R$ {df['CPC'].mean():.2f}")
                cols = ['Campanha', 'Resultados', 'Gasto', 'CPC']

            # Tabela com Formatação de Moeda
            st.dataframe(
                df[cols].style.background_gradient(subset=[cols[1]], cmap='Reds'),
                column_config={
                    "Gasto": st.column_config.NumberColumn(format="R$ %.2f"),
                    "CPC": st.column_config.NumberColumn(format="R$ %.2f"),
                    "CPM": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Custo/Res.": st.column_config.NumberColumn(format="R$ %.2f"),
                    "CTR": st.column_config.NumberColumn(format="%.2f%%"),
                    "Frequência": st.column_config.NumberColumn(format="%.2f"),
                },
                hide_index=True
            )

# --- SIDEBAR & GRÁFICO FINAL ---
with st.sidebar:
    st.header("📊 Resumo Global")
    st.write(f"**Ordenado por:** {criterio_ordem}")
    st.metric("Total Investido", f"R$ {total_geral_gasto:.2f}")
    if todos_dados_grafico:
        contas_ativas = len([c for c in lista_contas_processadas if c['gasto_total'] > 0])
        st.write(f"Contas Ativas: **{contas_ativas}**/{len(lista_contas_processadas)}")

if todos_dados_grafico:
    st.divider()
    st.subheader(f"🏆 Top Investimentos ({label_data})")
    df_geral = pd.concat(todos_dados_grafico)
    st.bar_chart(df_geral, x="Campanha", y="Gasto", color="Nome_Conta")
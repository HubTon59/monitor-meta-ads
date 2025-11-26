import streamlit as st
import pandas as pd
import os
import time
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Monitor Meta Ads Pro",
    page_icon="🧠",
    layout="wide"
)

# --- DICIONÁRIO DE TRADUÇÃO (Facebook -> Português) ---
TRADUCAO_OBJETIVOS = {
    'OUTCOME_TRAFFIC': 'Tráfego',
    'OUTCOME_SALES': 'Vendas',
    'OUTCOME_LEADS': 'Leads',
    'OUTCOME_AWARENESS': 'Reconhecimento',
    'OUTCOME_ENGAGEMENT': 'Engajamento',
    'OUTCOME_APP_PROMOTION': 'App',
    'BRAND_AWARENESS': 'Reconhecimento Marca',
    'REACH': 'Alcance',
    'POST_ENGAGEMENT': 'Engajamento Publ.',
    'VIDEO_VIEWS': 'Visualiz. Vídeo',
    'CONVERSIONS': 'Conversões',
    'LINK_CLICKS': 'Cliques no Link',
    'PRODUCT_CATALOG_SALES': 'Vendas Catálogo',
    'UNKNOWN': 'Desconhecido'
}

# --- BARRA LATERAL (CONFIGURAÇÕES GERAIS) ---
with st.sidebar:
    st.header("⚙️ Configurações")
    
    # 1. Configuração do MODO TV
    modo_tv = st.checkbox("📺 Modo TV (Auto-Refresh)", value=True, help="Atualiza a página a cada 5 minutos automaticamente.")
    
    if modo_tv:
        st_autorefresh(interval=5 * 60 * 1000, key="fbrecharge")
        st.caption("🟢 Auto-refresh ATIVO (5 min)")
    else:
        st.caption("🔴 Auto-refresh PAUSADO")

    st.divider()

    # 2. Configuração de VISIBILIDADE
    filtro_visualizacao = st.radio(
        "👁️ Visibilidade das Contas:",
        ["Ocultar Contas Zeradas", "Mostrar Todas as Contas"],
        index=0
    )
    
    st.divider()
    
    # Botão de Atualizar Manual
    st.caption(f"Última leitura: {time.strftime('%H:%M:%S')}")
    if st.button("🔄 Forçar Atualização", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- FUNÇÕES ---
def carregar_credenciais():
    load_dotenv()
    app_id = os.getenv('FB_APP_ID')
    app_secret = os.getenv('FB_APP_SECRET')
    access_token = os.getenv('FB_ACCESS_TOKEN')
    ids_string = os.getenv('FB_ACCOUNT_IDS')
    
    if not all([app_id, access_token, ids_string]):
        st.error("❌ Erro: Credenciais ausentes no .env")
        st.stop()
    try:
        FacebookAdsApi.init(app_id, app_secret, access_token)
        return ids_string.split(',')
    except Exception as e:
        st.error(f"❌ Erro API: {e}")
        st.stop()

def classificar_campanha(objetivo, ctr, cpm, cpa):
    """ Define a saúde da campanha (Semáforo) """
    status, cor = "Normal", "⚪"

    # Lógica de Tráfego
    if objetivo in ['OUTCOME_TRAFFIC', 'OUTCOME_ENGAGEMENT', 'LINK_CLICKS', 'POST_ENGAGEMENT', 'VIDEO_VIEWS']:
        if ctr >= 1.5: status, cor = "Ótima 🚀", "🔵"
        elif ctr >= 1.0: status, cor = "Boa ✅", "🟢"
        elif ctr >= 0.6: status, cor = "Normal 😐", "🟡"
        elif ctr >= 0.3: status, cor = "Ruim ⚠️", "🟠"
        else: status, cor = "Péssima 🆘", "🔴"

    # Lógica de Vendas/Leads
    elif objetivo in ['OUTCOME_SALES', 'OUTCOME_LEADS', 'CONVERSIONS', 'PRODUCT_CATALOG_SALES']:
        if cpa > 0:
            if cpa <= 10.00: status, cor = "Ótima 🚀", "🔵"
            elif cpa <= 30.00: status, cor = "Boa ✅", "🟢"
            elif cpa <= 60.00: status, cor = "Normal 😐", "🟡"
            elif cpa <= 100.00: status, cor = "Cara ⚠️", "🟠"
            else: status, cor = "Crítica 🆘", "🔴"
        else: status, cor = "Sem Conv. 👻", "⚪"

    # Lógica de Alcance
    elif objetivo in ['OUTCOME_AWARENESS', 'BRAND_AWARENESS', 'REACH']:
        if cpm <= 5.00: status, cor = "Barata 🚀", "🔵"
        elif cpm <= 10.00: status, cor = "Boa ✅", "🟢"
        elif cpm <= 20.00: status, cor = "Normal 😐", "🟡"
        else: status, cor = "Cara 🆘", "🔴"
    
    return f"{cor} {status}"

@st.cache_data(ttl=300) 
def obter_dados_conta(account_id, periodo_api):
    try:
        account = AdAccount(account_id.strip())
        try:
            account.api_get(fields=['name'])
            nome_da_conta = account['name']
        except:
            nome_da_conta = f"Conta {account_id}"

        params = {
            'date_preset': periodo_api,
            'effective_status': ['ACTIVE'], 
            'level': 'campaign'
        }
        
        fields = [
            'campaign_name', 'spend', 'impressions', 'clicks', 
            'cpc', 'ctr', 'reach', 'frequency', 'cpm', 'actions', 'objective'
        ]
        
        insights = account.get_insights(fields=fields, params=params)
        
        dados_lista = []
        total_gasto = 0.0
        
        if insights:
            for item in insights:
                acoes = item.get('actions', [])
                res_campanha = 0
                if acoes:
                    for acao in acoes:
                        if acao['action_type'] in ['lead', 'purchase', 'onsite_conversion.lead']:
                            res_campanha += int(acao['value'])
                
                gasto = float(item.get('spend', 0))
                total_gasto += gasto
                
                ctr = float(item.get('ctr', 0) if 'ctr' in item else 0)
                cpm = float(item.get('cpm', 0) if 'cpm' in item else 0)
                cpa = (gasto / res_campanha) if res_campanha > 0 else 0
                
                # Tradução do Objetivo
                obj_raw = item.get('objective', 'UNKNOWN')
                obj_traduzido = TRADUCAO_OBJETIVOS.get(obj_raw, obj_raw) # Tenta traduzir, senão usa o original

                saude = classificar_campanha(obj_raw, ctr, cpm, cpa)

                dados_lista.append({
                    'Campanha': item.get('campaign_name'),
                    'Status': saude,
                    'Objetivo': obj_traduzido,
                    'Gasto': gasto,
                    'Impressões': int(item.get('impressions', 0)),
                    'Cliques': int(item.get('clicks', 0)),
                    'CPC': float(item.get('cpc', 0) if 'cpc' in item else 0),
                    'CTR': ctr,
                    'CPM': cpm,
                    'Resultados': res_campanha,
                    'CPA': cpa,
                    'Frequência': float(item.get('frequency', 0))
                })
        
        return {
            'id': account_id,
            'nome': nome_da_conta,
            'df': pd.DataFrame(dados_lista),
            'gasto_total': total_gasto
        }

    except Exception as e:
        return {'id': account_id, 'nome': f"Erro: {account_id}", 'df': pd.DataFrame(), 'gasto_total': 0.0}

# --- INTERFACE PRINCIPAL ---
st.title("🧠 Monitor Inteligente Meta Ads")

mapa_datas = { "Hoje": "today", "Ontem": "yesterday", "Últimos 7 Dias": "last_7d", "Este Mês": "this_month", "Máximo": "maximum" }

c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    objetivo_view = st.selectbox("📂 Métricas em Destaque:", ["Visão Geral", "Tráfego", "Alcance", "Conversão"])
with c2:
    label_data = st.selectbox("📅 Período:", list(mapa_datas.keys()))
with c3:
    criterio_ordem = st.selectbox("🔃 Ordenar:", ["Nome (A-Z)", "Maior Gasto 💰"])

st.divider()

# --- PROCESSAMENTO ---
contas_ids = carregar_credenciais()
barra = st.progress(0, text="A analisar campanhas...")
lista_contas = []

for i, cid in enumerate(contas_ids):
    barra.progress(int(((i+1)/len(contas_ids))*100))
    lista_contas.append(obter_dados_conta(cid, mapa_datas[label_data]))

barra.empty()

# Ordenação
if criterio_ordem == "Nome (A-Z)": lista_contas.sort(key=lambda x: x['nome'].lower())
elif criterio_ordem == "Maior Gasto 💰": lista_contas.sort(key=lambda x: x['gasto_total'], reverse=True)

# --- EXIBIÇÃO ---
total_tela = 0.0
contas_exibidas = 0

for dados in lista_contas:
    df = dados['df']
    gasto = dados['gasto_total']
    
    # --- FILTRO DE VISIBILIDADE (AQUI ESTÁ A LÓGICA DO MENU) ---
    if filtro_visualizacao == "Ocultar Contas Zeradas":
        if df.empty and gasto == 0:
            continue # Pula esta conta e vai para a próxima
            
    total_tela += gasto
    contas_exibidas += 1

    # Definir se o Expander começa aberto ou fechado
    # Se for "Ocultar Zeradas", todas as que aparecem devem estar abertas.
    # Se for "Mostrar Todas", as zeradas começam fechadas.
    comeca_aberto = True
    if filtro_visualizacao == "Mostrar Todas as Contas" and gasto == 0:
        comeca_aberto = False

    with st.expander(f"🏢 {dados['nome']} | Investido: R$ {gasto:.2f}", expanded=comeca_aberto):
        if not df.empty:
            # Seleção de Colunas Dinâmica
            cols_base = ['Status', 'Campanha', 'Gasto']
            
            if objetivo_view == "Visão Geral":
                cols_extra = ['Objetivo', 'Resultados', 'CPA', 'CTR']
            elif objetivo_view == "Tráfego":
                cols_extra = ['Cliques', 'CTR', 'CPC', 'Objetivo']
            elif objetivo_view == "Alcance":
                cols_extra = ['Impressões', 'CPM', 'Frequência', 'Objetivo']
            elif objetivo_view == "Conversão":
                cols_extra = ['Resultados', 'CPA', 'Objetivo', 'Gasto']
            
            # Remove duplicados se houver e mantém ordem
            cols_finais = list(dict.fromkeys(cols_base + cols_extra))
            
            st.dataframe(
                df[cols_finais],
                column_config={
                    "Gasto": st.column_config.NumberColumn(format="R$ %.2f"),
                    "CPA": st.column_config.NumberColumn(format="R$ %.2f", label="Custo/Res."),
                    "CPM": st.column_config.NumberColumn(format="R$ %.2f"),
                    "CPC": st.column_config.NumberColumn(format="R$ %.2f"),
                    "CTR": st.column_config.NumberColumn(format="%.2f%%"),
                    "Frequência": st.column_config.NumberColumn(format="%.2f"),
                    "Status": st.column_config.TextColumn(label="Saúde"),
                },
                hide_index=True
            )
        else:
            st.info("Nenhuma campanha ativa neste período.")

# Resumo no final (apenas das contas visíveis)
st.caption(f"A mostrar {contas_exibidas} contas. Total Investido na Tela: R$ {total_tela:.2f}")
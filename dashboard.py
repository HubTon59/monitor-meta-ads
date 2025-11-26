import streamlit as st
import pandas as pd
import os
import time
from datetime import datetime
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Monitor Meta Ads Pro",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- DICIONÁRIOS E CONSTANTES ---
TRADUCAO_OBJETIVOS = {
    'OUTCOME_TRAFFIC': 'Tráfego',
    'OUTCOME_SALES': 'Vendas',
    'OUTCOME_LEADS': 'Leads',
    'OUTCOME_AWARENESS': 'Reconhecimento',
    'OUTCOME_ENGAGEMENT': 'Engajamento',
    'CONVERSIONS': 'Conversões',
    'UNKNOWN': 'Desconhecido'
}

TEXTOS_AJUDA = {
    "ctr": "CTR (Taxa de Cliques): Indica se o criativo está atrativo. Acima de 1% é bom.",
    "cpm": "CPM: Custo para aparecer 1.000 vezes.",
    "cpa": "CPA: Custo por Resultado (Venda/Lead).",
    "freq": "Frequência: Quantas vezes a mesma pessoa viu o anúncio.",
    "saude": "Saúde: Classificação automática baseada nas métricas principais."
}

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("⚙️ Painel de Controlo")
    
    # Guia Atualizado com a cor BRANCA
    with st.expander("📘 Guia Rápido (Legenda)", expanded=False):
        st.markdown("""
        **Saúde das Campanhas:**
        - 🔵 **Ótima:** Supera as expectativas.
        - 🟢 **Boa:** Dentro da meta.
        - 🟡 **Normal:** Atenção básica.
        - 🟠 **Ruim:** Otimizar.
        - 🔴 **Crítica:** Pausar/Trocar criativo.
        - ⚪ **Neutro/Sem Conv.:** Campanha ativa mas sem conversões registradas (CPA indefinido) ou métricas insuficientes.
        """)
        
    st.divider()
    
    modo_tv = st.checkbox("📺 Modo TV (Auto-Refresh)", value=False)
    if modo_tv:
        st_autorefresh(interval=5 * 60 * 1000, key="fbrecharge")
        st.caption("🟢 Atualizando a cada 5 min")

    st.divider()

    filtro_visualizacao = st.radio(
        "👁️ Filtro de Contas:",
        ["Ocultar Contas Zeradas", "Mostrar Todas as Contas"]
    )
    
    st.divider()
    if st.button("🔄 Atualizar Agora", use_container_width=True):
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
    status, cor = "Normal", "⚪"
    if objetivo in ['OUTCOME_TRAFFIC', 'OUTCOME_ENGAGEMENT', 'LINK_CLICKS']:
        if ctr >= 1.5: status, cor = "Ótima 🚀", "🔵"
        elif ctr >= 1.0: status, cor = "Boa ✅", "🟢"
        elif ctr >= 0.6: status, cor = "Normal 😐", "🟡"
        elif ctr >= 0.3: status, cor = "Ruim ⚠️", "🟠"
        else: status, cor = "Péssima 🆘", "🔴"
    elif objetivo in ['OUTCOME_SALES', 'OUTCOME_LEADS', 'CONVERSIONS']:
        if cpa > 0:
            if cpa <= 10.00: status, cor = "Ótima 🚀", "🔵"
            elif cpa <= 30.00: status, cor = "Boa ✅", "🟢"
            elif cpa <= 60.00: status, cor = "Normal 😐", "🟡"
            elif cpa <= 100.00: status, cor = "Cara ⚠️", "🟠"
            else: status, cor = "Crítica 🆘", "🔴"
        else: status, cor = "Sem Conv. 👻", "⚪"
    elif objetivo in ['OUTCOME_AWARENESS', 'REACH']:
        if cpm <= 5.00: status, cor = "Barata 🚀", "🔵"
        elif cpm <= 10.00: status, cor = "Boa ✅", "🟢"
        elif cpm <= 20.00: status, cor = "Normal 😐", "🟡"
        else: status, cor = "Cara 🆘", "🔴"
    return f"{cor} {status}"

@st.cache_data(ttl=300) 
def obter_dados_conta(account_id, periodo_config):
    """
    periodo_config pode ser:
    1. String: 'today', 'last_7d' (Presets)
    2. Dict: {'since': '2023-01-01', 'until': '2023-01-31'} (Range)
    """
    try:
        account = AdAccount(account_id.strip())
        try:
            account.api_get(fields=['name'])
            nome_da_conta = account['name']
        except:
            nome_da_conta = f"Conta {account_id}"

        # Configuração base
        params = {
            'effective_status': ['ACTIVE'], 
            'level': 'campaign'
        }

        # DECISÃO: É Preset ou Custom Range?
        if isinstance(periodo_config, dict):
            params['time_range'] = periodo_config
        else:
            params['date_preset'] = periodo_config

        fields = ['campaign_name', 'spend', 'impressions', 'clicks', 'cpc', 'ctr', 'reach', 'frequency', 'cpm', 'actions', 'objective']
        
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
                obj_raw = item.get('objective', 'UNKNOWN')
                obj_trad = TRADUCAO_OBJETIVOS.get(obj_raw, obj_raw)
                saude = classificar_campanha(obj_raw, ctr, cpm, cpa)

                dados_lista.append({
                    'Campanha': item.get('campaign_name'),
                    'Status': saude,
                    'Objetivo': obj_trad,
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
        
        return {'id': account_id, 'nome': nome_da_conta, 'df': pd.DataFrame(dados_lista), 'gasto_total': total_gasto}

    except Exception as e:
        return {'id': account_id, 'nome': f"Erro: {account_id}", 'df': pd.DataFrame(), 'gasto_total': 0.0}

# --- LAYOUT PRINCIPAL ---
st.title("🧠 Monitor Inteligente Meta Ads")

# Dicionário de Presets
presets_datas = { 
    "Hoje": "today", 
    "Ontem": "yesterday", 
    "Últimos 7 Dias": "last_7d", 
    "Este Mês": "this_month",
    "Personalizado 📅": "custom" # Nova Opção
}

c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    objetivo_view = st.selectbox("📂 Métricas em Destaque:", ["Visão Geral", "Tráfego", "Alcance", "Conversão"])
with c2:
    label_periodo = st.selectbox("📅 Período:", list(presets_datas.keys()))

# --- LÓGICA DO CALENDÁRIO ---
periodo_final_api = None

if label_periodo == "Personalizado 📅":
    # Mostra o calendário
    datas_sel = st.date_input("Selecione Início e Fim:", [])
    
    if len(datas_sel) == 2:
        inicio, fim = datas_sel
        # Converte para string YYYY-MM-DD
        periodo_final_api = {
            'since': inicio.strftime('%Y-%m-%d'), 
            'until': fim.strftime('%Y-%m-%d')
        }
    else:
        st.warning("👈 Por favor, selecione uma data de início e fim no calendário.")
        st.stop() # Para a execução até o usuário escolher as duas datas
else:
    periodo_final_api = presets_datas[label_periodo]

with c3:
    criterio_ordem = st.selectbox("🔃 Ordenar:", ["Nome (A-Z)", "Maior Gasto 💰"])

st.divider()

# --- PROCESSAMENTO ---
contas_ids = carregar_credenciais()
barra = st.progress(0, text="A buscar dados...")
lista_contas = []

for i, cid in enumerate(contas_ids):
    barra.progress(int(((i+1)/len(contas_ids))*100))
    # Passa o periodo_final_api (que pode ser string ou dict)
    lista_contas.append(obter_dados_conta(cid, periodo_final_api))
    
barra.empty()

if criterio_ordem == "Nome (A-Z)": lista_contas.sort(key=lambda x: x['nome'].lower())
elif criterio_ordem == "Maior Gasto 💰": lista_contas.sort(key=lambda x: x['gasto_total'], reverse=True)

total_tela = 0.0
for dados in lista_contas:
    df = dados['df']
    gasto = dados['gasto_total']
    
    if filtro_visualizacao == "Ocultar Contas Zeradas" and df.empty and gasto == 0: continue
    total_tela += gasto
    aberto = False if (filtro_visualizacao == "Mostrar Todas as Contas" and gasto == 0) else True

    with st.expander(f"🏢 {dados['nome']} | Investido: R$ {gasto:.2f}", expanded=aberto):
        if not df.empty:
            cols_base = ['Status', 'Campanha', 'Gasto']
            if objetivo_view == "Visão Geral": cols_extra = ['Objetivo', 'Resultados', 'CPA', 'CTR']
            elif objetivo_view == "Tráfego": cols_extra = ['Cliques', 'CTR', 'CPC', 'Objetivo']
            elif objetivo_view == "Alcance": cols_extra = ['Impressões', 'CPM', 'Frequência']
            elif objetivo_view == "Conversão": cols_extra = ['Resultados', 'CPA', 'Objetivo']
            
            st.dataframe(
                df[list(dict.fromkeys(cols_base + cols_extra))],
                column_config={
                    "Gasto": st.column_config.NumberColumn(format="R$ %.2f"),
                    "CPA": st.column_config.NumberColumn(format="R$ %.2f", label="Custo/Res.", help=TEXTOS_AJUDA['cpa']),
                    "CPM": st.column_config.NumberColumn(format="R$ %.2f", help=TEXTOS_AJUDA['cpm']),
                    "CTR": st.column_config.NumberColumn(format="%.2f%%", help=TEXTOS_AJUDA['ctr']),
                    "Frequência": st.column_config.NumberColumn(format="%.2f", help=TEXTOS_AJUDA['freq']),
                    "Status": st.column_config.TextColumn(label="Saúde", help=TEXTOS_AJUDA['saude']),
                },
                hide_index=True
            )
        else:
            st.info("Nenhuma campanha ativa neste período.")

st.caption(f"Total Investido na Tela: R$ {total_tela:.2f}")
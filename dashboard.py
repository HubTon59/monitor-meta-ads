import streamlit as st
import pandas as pd
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Monitor Pro",
    page_icon=":material/analytics:", # Ícone elegante na aba do navegador
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILOS CSS (Refinamento Visual Opcional) ---
st.markdown("""
<style>
    [data-testid="stExpander"] details summary p {
        font-weight: 600;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)

# --- CONSTANTES ---
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
    "ctr": "CTR: Taxa de cliques no anúncio.",
    "cpm": "CPM: Custo por 1.000 impressões.",
    "cpa": "CPA: Custo por resultado (Venda/Lead).",
    "freq": "Frequência: Média de vezes que a pessoa viu.",
    "saude": "Classificação automática de performance."
}

# --- BARRA LATERAL ---
with st.sidebar:
    st.header(":material/settings: Painel de Controlo")
    
    with st.expander(":material/help: Legenda de Saúde", expanded=False):
        st.markdown("""
        - :material/sentiment_very_satisfied: **Ótima**
        - :material/sentiment_satisfied: **Boa**
        - :material/sentiment_neutral: **Normal**
        - :material/sentiment_dissatisfied: **Ruim**
        - :material/warning: **Crítica**
        - :material/radio_button_unchecked: **Neutro**
        """)
        
    st.divider()
    
    modo_tv = st.checkbox("Modo TV (Auto-Refresh)", value=False)
    if modo_tv:
        st_autorefresh(interval=5 * 60 * 1000, key="fbrecharge")
        st.caption(":material/timer: Atualizando a cada 5 min")

    st.divider()

    filtro_visualizacao = st.radio(
        "Filtro de Visualização:",
        ["Ocultar Contas Zeradas", "Mostrar Todas as Contas"],
        index=0
    )
    
    st.divider()
    if st.button("Forçar Atualização", type="primary", use_container_width=True):
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
        st.error("Credenciais ausentes no .env")
        st.stop()
    try:
        FacebookAdsApi.init(app_id, app_secret, access_token)
        return ids_string.split(',')
    except Exception as e:
        st.error(f"Erro API: {e}")
        st.stop()

def classificar_campanha(objetivo, ctr, cpm, cpa):
    # Ícones Material para substituir as bolinhas coloridas antigas
    status, icone = "Normal", "⚪" 
    
    # Definição de ícones baseada em sentimentos/alertas
    icon_otimo = "🔵" # Mantemos emojis na tabela pois st.dataframe não renderiza :material: dentro da célula ainda
    icon_bom = "🟢"
    icon_normal = "🟡"
    icon_ruim = "🟠"
    icon_critico = "🔴"

    if objetivo in ['OUTCOME_TRAFFIC', 'OUTCOME_ENGAGEMENT', 'LINK_CLICKS']:
        if ctr >= 1.5: status, icone = "Ótima", icon_otimo
        elif ctr >= 1.0: status, icone = "Boa", icon_bom
        elif ctr >= 0.6: status, icone = "Normal", icon_normal
        elif ctr >= 0.3: status, icone = "Ruim", icon_ruim
        else: status, icone = "Péssima", icon_critico
    elif objetivo in ['OUTCOME_SALES', 'OUTCOME_LEADS', 'CONVERSIONS']:
        if cpa > 0:
            if cpa <= 10.00: status, icone = "Ótima", icon_otimo
            elif cpa <= 30.00: status, icone = "Boa", icon_bom
            elif cpa <= 60.00: status, icone = "Normal", icon_normal
            elif cpa <= 100.00: status, icone = "Cara", icon_ruim
            else: status, icone = "Crítica", icon_critico
        else: status, icone = "Sem Conv.", "⚪"
    elif objetivo in ['OUTCOME_AWARENESS', 'REACH']:
        if cpm <= 5.00: status, icone = "Barata", icon_otimo
        elif cpm <= 10.00: status, icone = "Boa", icon_bom
        elif cpm <= 20.00: status, icone = "Normal", icon_normal
        else: status, icone = "Cara", icon_critico
        
    return f"{icone} {status}"

def processar_conta_individual(account_id, periodo_config):
    """ Função isolada para rodar em paralelo """
    try:
        account = AdAccount(account_id.strip())
        try:
            account.api_get(fields=['name'])
            nome_da_conta = account['name']
        except:
            nome_da_conta = f"Conta {account_id}"

        params = {'effective_status': ['ACTIVE'], 'level': 'campaign'}
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

@st.cache_data(ttl=300)
def obter_dados_paralelos(lista_ids, periodo_api):
    """ Gerenciador de Multithreading """
    resultados = []
    # max_workers=5 é seguro para não levar block da API
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(processar_conta_individual, cid, periodo_api): cid for cid in lista_ids}
        
        for future in as_completed(futures):
            resultados.append(future.result())
            
    return resultados

# --- LAYOUT PRINCIPAL ---
st.title(":material/monitoring: Monitor Meta Ads")

presets_datas = { 
    "Hoje": "today", "Ontem": "yesterday", "Últimos 7 Dias": "last_7d", 
    "Este Mês": "this_month", "Personalizado 📅": "custom"
}

c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    objetivo_view = st.selectbox("📂 Métricas em Destaque:", ["Visão Geral", "Tráfego", "Alcance", "Conversão"])
with c2:
    label_periodo = st.selectbox("📅 Período:", list(presets_datas.keys()))

periodo_final_api = None
if label_periodo == "Personalizado 📅":
    datas_sel = st.date_input("Início e Fim:", [])
    if len(datas_sel) == 2:
        periodo_final_api = {'since': datas_sel[0].strftime('%Y-%m-%d'), 'until': datas_sel[1].strftime('%Y-%m-%d')}
    else:
        st.warning("Selecione o intervalo completo.")
        st.stop()
else:
    periodo_final_api = presets_datas[label_periodo]

with c3:
    criterio_ordem = st.selectbox("🔃 Ordenar:", ["Nome (A-Z)", "Maior Gasto 💰"])

st.divider()

# --- PROCESSAMENTO PARALELO ---
contas_ids = carregar_credenciais()

# Spinner elegante em vez de barra de progresso lenta
with st.spinner('🚀 A conectar aos servidores da Meta...'):
    lista_contas = obter_dados_paralelos(contas_ids, periodo_final_api)

# Ordenação
if criterio_ordem == "Nome (A-Z)": lista_contas.sort(key=lambda x: x['nome'].lower())
elif criterio_ordem == "Maior Gasto 💰": lista_contas.sort(key=lambda x: x['gasto_total'], reverse=True)

# --- EXIBIÇÃO ---
total_tela = 0.0
contas_exibidas = 0

for dados in lista_contas:
    df = dados['df']
    gasto = dados['gasto_total']
    
    if filtro_visualizacao == "Ocultar Contas Zeradas" and df.empty and gasto == 0: continue
    
    total_tela += gasto
    contas_exibidas += 1
    
    # Ícone dinâmico no título do expander
    icone_conta = ":material/check_circle:" if gasto > 0 else ":material/pause_circle:"
    titulo = f"{icone_conta} {dados['nome']} | Investido: R$ {gasto:.2f}"
    
    aberto = False if (filtro_visualizacao == "Mostrar Todas as Contas" and gasto == 0) else True

    with st.expander(titulo, expanded=aberto):
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
                    "Status": st.column_config.TextColumn(label="Saúde"),
                },
                hide_index=True
            )
        else:
            st.info("Nenhuma campanha ativa neste período.")

# Rodapé com métrica global
st.markdown("---")
col_f1, col_f2 = st.columns([3, 1])
with col_f1:
    st.caption(f"Visualizando {contas_exibidas} contas.")
with col_f2:
    st.metric("Investimento Total (Tela)", f"R$ {total_tela:.2f}")
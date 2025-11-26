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
    page_icon=":material/analytics:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILOS ---
st.markdown("""
<style>
    [data-testid="stExpander"] details summary p {
        font-size: 1.05rem;
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
    
    with st.expander(":material/palette: Legenda de Saúde", expanded=True):
        st.markdown("""
        - 🔵 **Ótima** (Performance Top)
        - 🟢 **Boa** (Dentro da Meta)
        - 🟡 **Normal** (Atenção)
        - 🟠 **Ruim** (Otimizar)
        - 🔴 **Crítica** (Pausar/Rever)
        - ⚪ **Neutro** (Sem dados suf.)
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
    status, icone = "Normal", "⚪" 
    icon_otimo, icon_bom, icon_normal, icon_ruim, icon_critico = "🔵", "🟢", "🟡", "🟠", "🔴"

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
    """ Processa campanhas E histórico diário da conta """
    try:
        account = AdAccount(account_id.strip())
        try:
            account.api_get(fields=['name'])
            nome_da_conta = account['name']
        except:
            nome_da_conta = f"Conta {account_id}"

        # 1. Buscar Campanhas (Dados Agregados)
        params = {'effective_status': ['ACTIVE'], 'level': 'campaign'}
        if isinstance(periodo_config, dict): params['time_range'] = periodo_config
        else: params['date_preset'] = periodo_config

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

        # 2. Buscar Histórico Diário da CONTA (Para o Gráfico)
        # Fazemos uma segunda chamada leve, apenas nível da conta, quebrado por dia
        params_trend = params.copy()
        params_trend['time_increment'] = 1 # Isso faz a mágica do dia-a-dia
        params_trend['level'] = 'account'  # Apenas totais da conta
        
        trend_insights = account.get_insights(fields=['spend', 'date_start'], params=params_trend)
        dados_trend = []
        if trend_insights:
            for t in trend_insights:
                dados_trend.append({
                    'Data': t['date_start'],
                    'Gasto': float(t['spend']),
                    'Conta': nome_da_conta
                })
        
        return {
            'id': account_id, 
            'nome': nome_da_conta, 
            'df': pd.DataFrame(dados_lista), 
            'df_trend': pd.DataFrame(dados_trend), # Novo DataFrame para o gráfico
            'gasto_total': total_gasto
        }

    except Exception as e:
        return {'id': account_id, 'nome': f"Erro: {account_id}", 'df': pd.DataFrame(), 'df_trend': pd.DataFrame(), 'gasto_total': 0.0}

@st.cache_data(ttl=300)
def obter_dados_com_progresso(lista_ids, periodo_api):
    resultados = []
    barra = st.progress(0, text="🚀 A iniciar motores...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(processar_conta_individual, cid, periodo_api): cid for cid in lista_ids}
        for i, future in enumerate(as_completed(futures)):
            barra.progress(int(((i + 1) / len(lista_ids)) * 100), text=f"A carregar conta {i+1}/{len(lista_ids)}...")
            resultados.append(future.result())
    time.sleep(0.2)
    barra.empty()
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

# --- PROCESSAMENTO ---
contas_ids = carregar_credenciais()
lista_contas = obter_dados_com_progresso(contas_ids, periodo_final_api)

if criterio_ordem == "Nome (A-Z)": lista_contas.sort(key=lambda x: x['nome'].lower())
elif criterio_ordem == "Maior Gasto 💰": lista_contas.sort(key=lambda x: x['gasto_total'], reverse=True)

# --- EXIBIÇÃO ---
total_tela = 0.0
contas_exibidas = 0
lista_trends = [] # Lista para guardar dados do gráfico

for dados in lista_contas:
    df = dados['df']
    df_trend = dados['df_trend'] # Pegamos o histórico diário
    gasto = dados['gasto_total']
    
    if filtro_visualizacao == "Ocultar Contas Zeradas" and df.empty and gasto == 0: continue
    
    total_tela += gasto
    contas_exibidas += 1
    
    # Acumula dados para o gráfico final
    if not df_trend.empty:
        lista_trends.append(df_trend)
    
    icone_visual = ":green[:material/check_circle:]" if gasto > 0 else ":grey[:material/pause_circle:]"
    classe_gasto = f":green[R$ {gasto:.2f}]" if gasto > 0 else f":grey[R$ {gasto:.2f}]"
    
    aberto = False if (filtro_visualizacao == "Mostrar Todas as Contas" and gasto == 0) else True

    with st.expander(f"{icone_visual} **{dados['nome']}** | Investido: {classe_gasto}", expanded=aberto):
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

# --- RODAPÉ E GRÁFICO DE EVOLUÇÃO ---
st.divider()

# Seletor de Tipo de Gráfico
if lista_trends:
    tipo_grafico = st.radio("Visualização Global:", ["Barras (Total Acumulado)", "Linhas (Evolução Diária)"], horizontal=True)
    
    if tipo_grafico == "Linhas (Evolução Diária)":
        st.subheader("📈 Evolução do Investimento (Dia a Dia)")
        df_geral_trend = pd.concat(lista_trends)
        # O Streamlit agrupa automaticamente pela cor
        st.line_chart(df_geral_trend, x="Data", y="Gasto", color="Conta")
        
    else:
        st.subheader("📊 Total por Campanha")
        # Para o gráfico de barras, precisamos dos dados das campanhas (que estão dentro de 'lista_contas')
        # Vamos reconstruir um DF rápido só para isso
        dfs_campanhas = []
        for d in lista_contas:
            if not d['df'].empty:
                temp = d['df'].copy()
                temp['Conta'] = d['nome']
                dfs_campanhas.append(temp)
        
        if dfs_campanhas:
            df_final = pd.concat(dfs_campanhas)
            st.bar_chart(df_final, x="Campanha", y="Gasto", color="Conta")

col_f1, col_f2 = st.columns([3, 1])
with col_f1:
    st.caption(f"Visualizando {contas_exibidas} contas.")
with col_f2:
    st.metric("Investimento Total (Tela)", f"R$ {total_tela:.2f}")
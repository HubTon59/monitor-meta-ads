import streamlit as st
import pandas as pd
import os
import time
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from streamlit_autorefresh import st_autorefresh # Nova biblioteca para TV

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Monitor Meta Ads Pro",
    page_icon="🧠",
    layout="wide"
)

# --- AUTO-REFRESH (Configuração para TV) ---
# Atualiza a cada 5 minutos (300.000 milissegundos)
count = st_autorefresh(interval=5 * 60 * 1000, key="fbrecharge")

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

def classificar_campanha(objetivo, ctr, cpm, cpa):
    """
    O CÉREBRO DA OPERAÇÃO 🧠
    Define se a campanha é Boa, Média ou Ruim baseada no objetivo.
    Nota: Estes valores são genéricos. Podes ajustar conforme o teu nicho.
    """
    status = "Normal"
    cor = "⚪" # Cinza neutro

    # 1. OBJETIVO: TRÁFEGO ou ENGAJAMENTO (Foco no Criativo/CTR)
    if objetivo in ['OUTCOME_TRAFFIC', 'OUTCOME_ENGAGEMENT', 'LINK_CLICKS', 'POST_ENGAGEMENT']:
        if ctr >= 1.5:
            status, cor = "Ótima 🚀", "🔵"
        elif ctr >= 1.0:
            status, cor = "Boa ✅", "🟢"
        elif ctr >= 0.6:
            status, cor = "Normal 😐", "🟡"
        elif ctr >= 0.3:
            status, cor = "Ruim ⚠️", "🟠"
        else:
            status, cor = "Péssima 🆘", "🔴"

    # 2. OBJETIVO: VENDAS ou LEADS (Foco no Dinheiro/CPA)
    elif objetivo in ['OUTCOME_SALES', 'OUTCOME_LEADS', 'CONVERSIONS']:
        # Aqui é difícil ser genérico, pois depende do ticket do produto.
        # Vamos assumir que um Lead/Venda barato é bom (ex: < R$ 20.00)
        if cpa > 0:
            if cpa <= 10.00:
                status, cor = "Ótima 🚀", "🔵"
            elif cpa <= 30.00:
                status, cor = "Boa ✅", "🟢"
            elif cpa <= 60.00:
                status, cor = "Normal 😐", "🟡"
            elif cpa <= 100.00:
                status, cor = "Cara ⚠️", "🟠"
            else:
                status, cor = "Crítica 🆘", "🔴"
        else:
             status, cor = "Sem Conversão 👻", "⚪"

    # 3. OBJETIVO: RECONHECIMENTO (Foco no Custo por Mil/CPM)
    elif objetivo in ['OUTCOME_AWARENESS', 'BRAND_AWARENESS', 'REACH']:
        if cpm <= 5.00:
            status, cor = "Barata 🚀", "🔵"
        elif cpm <= 10.00:
            status, cor = "Boa ✅", "🟢"
        elif cpm <= 20.00:
            status, cor = "Normal 😐", "🟡"
        else:
            status, cor = "Cara 🆘", "🔴"
    
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
        
        # ADICIONEI O CAMPO 'objective' AQUI
        fields = [
            'campaign_name', 'spend', 'impressions', 'clicks', 
            'cpc', 'ctr', 'reach', 'frequency', 'cpm', 'actions', 'objective'
        ]
        
        insights = account.get_insights(fields=fields, params=params)
        
        dados_lista = []
        total_gasto = 0.0
        total_resultados = 0
        
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
                total_resultados += res_campanha
                
                ctr = float(item.get('ctr', 0) if 'ctr' in item else 0)
                cpm = float(item.get('cpm', 0) if 'cpm' in item else 0)
                
                # Calcular CPA (Custo por Ação) para a saúde
                cpa = (gasto / res_campanha) if res_campanha > 0 else 0
                
                # Objetivo da campanha (Ex: OUTCOME_LEADS)
                obj_fb = item.get('objective', 'UNKNOWN')

                # Calcular a Saúde
                saude = classificar_campanha(obj_fb, ctr, cpm, cpa)

                dados_lista.append({
                    'Campanha': item.get('campaign_name'),
                    'Status': saude, # Nova Coluna
                    'Objetivo': obj_fb.replace('OUTCOME_', '').title(), # Limpa o nome (ex: Leads)
                    'Gasto': gasto,
                    'Impressões': int(item.get('impressions', 0)),
                    'Alcance': int(item.get('reach', 0)),
                    'Frequência': float(item.get('frequency', 0)),
                    'Cliques': int(item.get('clicks', 0)),
                    'CPC': float(item.get('cpc', 0) if 'cpc' in item else 0),
                    'CTR': ctr,
                    'CPM': cpm,
                    'Resultados': res_campanha,
                    'CPA': cpa
                })
        
        df = pd.DataFrame(dados_lista)
        
        return {
            'id': account_id,
            'nome': nome_da_conta,
            'df': df,
            'gasto_total': total_gasto,
            'campanhas_ativas': len(df),
            'resultados_total': total_resultados
        }

    except Exception as e:
        return {'id': account_id, 'nome': f"Erro: {account_id}", 'df': pd.DataFrame(), 'gasto_total': 0.0, 'campanhas_ativas': 0, 'resultados_total': 0}

# --- INTERFACE ---
st.title("🧠 Monitor Inteligente (TV Mode)")

# Barra lateral com relógio da última atualização
with st.sidebar:
    st.caption(f"Última atualização: {time.strftime('%H:%M:%S')}")
    if st.button("Forçar Atualização"):
        st.cache_data.clear()
        st.rerun()

mapa_datas = { "Hoje": "today", "Ontem": "yesterday", "Últimos 7 Dias": "last_7d", "Este Mês": "this_month", "Máximo": "maximum" }

c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    objetivo = st.selectbox("📂 Visualizar Métricas de:", ["Visão Geral", "Tráfego", "Alcance", "Conversão"])
with c2:
    label_data = st.selectbox("📅 Período:", list(mapa_datas.keys()))
with c3:
    criterio_ordem = st.selectbox("🔃 Ordenar:", ["Nome", "Maior Gasto", "Pior Performance"])

st.divider()

# --- PROCESSAMENTO ---
contas_ids = carregar_credenciais()
barra = st.progress(0, text="A analisar campanhas...")
lista_contas = []

for i, cid in enumerate(contas_ids):
    barra.progress(int(((i+1)/len(contas_ids))*100))
    lista_contas.append(obter_dados_conta(cid, mapa_datas[label_data]))

barra.empty()

# Ordenação (Incluindo lógica nova)
if criterio_ordem == "Nome": lista_contas.sort(key=lambda x: x['nome'].lower())
elif criterio_ordem == "Maior Gasto": lista_contas.sort(key=lambda x: x['gasto_total'], reverse=True)

# --- EXIBIÇÃO ---
total_geral = sum(c['gasto_total'] for c in lista_contas)
st.metric("Investimento Total na Tela", f"R$ {total_geral:.2f}")

for dados in lista_contas:
    df = dados['df']
    if df.empty and dados['gasto_total'] == 0: continue # Pula contas vazias para economizar espaço na TV

    with st.expander(f"🏢 {dados['nome']} | R$ {dados['gasto_total']:.2f}", expanded=True):
        if not df.empty:
            # Seleção de colunas baseada no objetivo visual
            cols_base = ['Status', 'Campanha', 'Gasto']
            
            if objetivo == "Visão Geral":
                cols_extra = ['Objetivo', 'Resultados', 'CPA', 'CTR']
            elif objetivo == "Tráfego":
                cols_extra = ['Cliques', 'CTR', 'CPC']
            elif objetivo == "Alcance":
                cols_extra = ['Impressões', 'CPM', 'Frequência']
            elif objetivo == "Conversão":
                cols_extra = ['Resultados', 'CPA', 'Objetivo']
            
            cols_finais = cols_base + cols_extra
            
            # Tabela
            st.dataframe(
                df[cols_finais],
                column_config={
                    "Gasto": st.column_config.NumberColumn(format="R$ %.2f"),
                    "CPA": st.column_config.NumberColumn(format="R$ %.2f", label="Custo/Res."),
                    "CPM": st.column_config.NumberColumn(format="R$ %.2f"),
                    "CPC": st.column_config.NumberColumn(format="R$ %.2f"),
                    "CTR": st.column_config.NumberColumn(format="%.2f%%"),
                    "Status": st.column_config.TextColumn(label="Saúde"),
                },
                hide_index=True
            )
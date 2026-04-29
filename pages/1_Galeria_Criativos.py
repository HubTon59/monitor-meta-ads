import streamlit as st
import os
import warnings
from html import escape
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.advideo import AdVideo
from facebook_business.adobjects.adimage import AdImage

# --- SILENCIAR WARNINGS DA API NO TERMINAL ---
warnings.filterwarnings('ignore', category=UserWarning, module='facebook_business')

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Galeria de Criativos",
    page_icon=":material/perm_media:",
    layout="wide"
)

st.title(":material/perm_media: Galeria de Criativos")

# --- SELETOR DE PERÍODO (Igual ao Dashboard) ---
presets_datas = { 
    "Hoje": "today", "Ontem": "yesterday", "Últimos 7 Dias": "last_7d", 
    "Este Mês": "this_month", "Personalizado 📅": "custom"
}

c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    st.markdown("Visualize as artes em das campanhas ativas no período selecionado.")
with c2:
    label_periodo = st.selectbox("📅 Período de Análise:", list(presets_datas.keys()))
with c3:
    filtro_visualizacao = st.selectbox(
        "👁️ Exibição:",
        ["Ocultar Contas Zeradas", "Mostrar Todas as Contas"],
        index=0,
    )

periodo_final_api = None
if label_periodo == "Personalizado 📅":
    datas_sel = st.date_input("Início e Fim:", [])
    if len(datas_sel) == 2:
        periodo_final_api = {'since': datas_sel[0].strftime('%Y-%m-%d'), 'until': datas_sel[1].strftime('%Y-%m-%d')}
    else:
        st.warning("Selecione o intervalo de datas completo para continuar.")
        st.stop()
else:
    periodo_final_api = presets_datas[label_periodo]

# --- INICIALIZAÇÃO DA API ---
@st.cache_resource
def iniciar_api():
    load_dotenv()
    app_id = os.getenv('FB_APP_ID')
    app_secret = os.getenv('FB_APP_SECRET')
    access_token = os.getenv('FB_ACCESS_TOKEN')
    ids_string = os.getenv('FB_ACCOUNT_IDS')
    
    if not all([app_id, access_token, ids_string]):
        st.error("Credenciais ausentes no .env")
        st.stop()
        
    FacebookAdsApi.init(app_id, app_secret, access_token)
    return [cid.strip() for cid in ids_string.split(',')]

def render_preview_html(midia):
    url = midia.get('cover_url') if midia.get('tipo') == 'video' else midia.get('url')
    if midia.get('tipo') == 'video':
        url = midia.get('cover_url') or midia.get('url')
    if not url:
        return

    title = "Vídeo" if midia.get('tipo') == 'video' else "Imagem"
    width = midia.get('original_width') or midia.get('width')
    height = midia.get('original_height') or midia.get('height')
    ratio_style = f"aspect-ratio: {width} / {height};" if width and height else ""
    extra_caption = f"<div style='font-size:0.8rem;opacity:0.75;margin-top:0.35rem;'>{width} × {height}px</div>" if width and height else ""

    st.markdown(
        f"""
        <div style="width:100%; {ratio_style}">
            <img src="{escape(url)}" alt="{escape(title)}" style="width:100%; height:auto; display:block; border-radius:12px; object-fit:contain;" />
        </div>
        {extra_caption}
        """,
        unsafe_allow_html=True,
    )

# --- FUNÇÕES DE PROCESSAMENTO ---
@st.cache_data(ttl=3600, show_spinner=False)
def buscar_imagem_original_por_hash(account_id, image_hash):
    if not account_id or not image_hash:
        return None
    try:
        account = AdAccount(account_id)
        imagens = account.get_ad_images(
            fields=[
                AdImage.Field.url,
                AdImage.Field.original_width,
                AdImage.Field.original_height,
                AdImage.Field.width,
                AdImage.Field.height,
                AdImage.Field.hash,
            ],
            params={'hashes': [image_hash]},
        )
        if imagens:
            imagem = imagens[0]
            url = imagem.get('url')
            if url:
                return {
                    'url': url,
                    'tipo': 'imagem',
                    'origem': 'original',
                    'original_width': imagem.get('original_width'),
                    'original_height': imagem.get('original_height'),
                    'width': imagem.get('width'),
                    'height': imagem.get('height'),
                }
    except Exception:
        pass
    return None


def extrair_midias_do_criativo(creative, account_id):
    """Extrai a mídia em ALTA RESOLUÇÃO e identifica se é Vídeo ou Imagem."""
    midias = []
    
    tipo = 'imagem'
    if 'video_id' in creative:
        tipo = 'video'
        
    url_final = None
    origem_final = 'fallback'
    imagem_principal_encontrada = False

    def primeiro_valor_util(dados, chaves):
        if not isinstance(dados, dict):
            return None
        for chave in chaves:
            valor = dados.get(chave)
            if valor:
                return valor
        return None

    creative_thumbnail_url = creative.get('thumbnail_url')

    def buscar_video_midias(video_id, fallback_cover_url=None):
        if not video_id:
            return {'video_url': None, 'cover_url': fallback_cover_url, 'cover_origem': 'thumbnail'}
        try:
            video = AdVideo(video_id).api_get(fields=['source', 'thumbnail_url', 'picture'])
            cover_url = fallback_cover_url or video.get('thumbnail_url') or video.get('picture')
            return {
                'video_url': video.get('source'),
                'cover_url': cover_url,
                'cover_origem': 'preview' if fallback_cover_url else ('original' if video.get('thumbnail_url') or video.get('picture') else 'thumbnail'),
            }
        except Exception:
            return {'video_url': None, 'cover_url': fallback_cover_url, 'cover_origem': 'preview' if fallback_cover_url else 'thumbnail'}

    def extrair_hash_imagem(dados):
        if not isinstance(dados, dict):
            return None
        for chave in ('image_hash', 'hash', 'original_image_hash'):
            if dados.get(chave):
                return dados.get(chave)
        imagem = dados.get('image')
        if isinstance(imagem, dict):
            for chave in ('image_hash', 'hash'):
                if imagem.get(chave):
                    return imagem.get(chave)
        return None

    def adicionar_midia(url, tipo_midia, origem_midia):
        if url:
            midias.append({'url': url, 'tipo': tipo_midia, 'origem': origem_midia})

    def adicionar_video(video_url, cover_url, cover_origem):
        midias.append({
            'tipo': 'video',
            'origem': 'original' if video_url else cover_origem,
            'url': cover_url or video_url,
            'video_url': video_url,
            'cover_url': cover_url,
            'cover_origem': cover_origem,
            'video_id': None,
        })

    def adicionar_video_com_id(video_id, video_url, cover_url, cover_origem):
        midias.append({
            'tipo': 'video',
            'origem': 'original' if video_url else cover_origem,
            'url': cover_url or video_url,
            'video_url': video_url,
            'cover_url': cover_url,
            'cover_origem': cover_origem,
            'video_id': video_id,
        })

    def pontuar_midia(midia):
        score = 0
        if midia.get('tipo') == 'imagem':
            score += 20
        elif midia.get('tipo') == 'video':
            score += 10

        origem = midia.get('origem')
        if origem == 'original':
            score += 10
        elif origem == 'preview':
            score += 4
        elif origem == 'thumbnail':
            score += 1
        return score
    
    # 1. Prioridade Máxima: Object Story Spec (A resolução HD original fica aqui)
    oss = creative.get('object_story_spec', {})
    if oss:
        if 'video_data' in oss:
            tipo = 'video'
            video_data = oss['video_data']
            video_info = buscar_video_midias(video_data.get('video_id'), fallback_cover_url=creative_thumbnail_url)
            url_final = video_info.get('cover_url') or primeiro_valor_util(video_data, ['image_url', 'thumbnail_url', 'picture']) or creative_thumbnail_url
            origem_final = video_info.get('cover_origem', 'thumbnail')
            if video_info.get('video_url'):
                adicionar_video_com_id(video_data.get('video_id'), video_info['video_url'], url_final, origem_final)
                url_final = None
        elif 'photo_data' in oss:
            tipo = 'imagem'
            photo_data = oss['photo_data']
            image_hash = extrair_hash_imagem(photo_data)
            if image_hash:
                imagem_original = buscar_imagem_original_por_hash(account_id, image_hash)
                if imagem_original:
                    midias.append(imagem_original)
                    imagem_principal_encontrada = True
            if not url_final:
                url_final = primeiro_valor_util(photo_data, ['url', 'image_url', 'image_uri'])
                origem_final = 'original' if url_final else origem_final
        elif 'link_data' in oss:
            # Em links, o Meta às vezes esconde um vídeo ou uma imagem
            link_data = oss['link_data']
            image_hash = extrair_hash_imagem(link_data)
            if image_hash:
                imagem_original = buscar_imagem_original_por_hash(account_id, image_hash)
                if imagem_original:
                    midias.append(imagem_original)
                    imagem_principal_encontrada = True
            if not url_final:
                url_final = primeiro_valor_util(link_data, ['image_url', 'picture'])
                if url_final:
                    origem_final = 'preview'
            
    # 2. Se não encontrou no OSS, tenta a raiz
    if not url_final:
        url_final = creative_thumbnail_url or creative.get('thumbnail_url')
        if url_final:
            origem_final = 'preview'
        else:
            url_final = creative.get('image_url')
            if url_final:
                origem_final = 'preview'

    if not url_final and creative.get('video_id'):
        tipo = 'video'
        video_id = creative.get('video_id')
        video_info = buscar_video_midias(video_id, fallback_cover_url=creative_thumbnail_url)
        url_final = video_info.get('cover_url') or creative_thumbnail_url
        origem_final = video_info.get('cover_origem', 'thumbnail')
        if video_info.get('video_url'):
            adicionar_video_com_id(video_id, video_info['video_url'], url_final, origem_final)
            url_final = None
        
    # 3. Tratamento para DCO (Asset Feed Spec - Criativos Dinâmicos)
    afs = creative.get('asset_feed_spec', {})
    if afs:
        if 'images' in afs:
            for img in afs['images']:
                if isinstance(img, dict):
                    image_hash = extrair_hash_imagem(img)
                    if image_hash:
                        imagem_original = buscar_imagem_original_por_hash(account_id, image_hash)
                        if imagem_original:
                            midias.append(imagem_original)
                            continue
                    url_img = primeiro_valor_util(
                        img,
                        ['url', 'image_url', 'original_image_url', 'resized_image_url']
                    )
                    if not url_img and isinstance(img.get('image'), dict):
                        url_img = primeiro_valor_util(
                            img['image'],
                            ['url', 'image_url', 'original_image_url', 'resized_image_url']
                        )
                    if url_img:
                        midias.append({'url': url_img, 'tipo': 'imagem', 'origem': 'preview'})
        if 'videos' in afs:
            for vid in afs['videos']:
                if isinstance(vid, dict):
                    video_id = vid.get('video_id')
                    video_info = buscar_video_midias(video_id, fallback_cover_url=creative_thumbnail_url)
                    url_video = video_info.get('video_url')
                    cover_url = video_info.get('cover_url')
                    origem_video = video_info.get('cover_origem', 'thumbnail')
                    if url_video or cover_url:
                        adicionar_video_com_id(video_id, url_video, cover_url, origem_video)

    if url_final and not (tipo == 'imagem' and imagem_principal_encontrada):
        adicionar_midia(url_final, tipo, origem_final)
        
    return midias

def buscar_criativos_da_conta(account_id, periodo_api):
    """Busca alinhada com o período selecionado no UI."""
    try:
        account = AdAccount(account_id)
        try:
            nome_conta = account.api_get(fields=['name'])['name']
        except:
            nome_conta = f"Conta {account_id}"

        # PASSO 1: Filtro de Campanha baseado na Data Selecionada
        params_insights = {
            'effective_status': ['ACTIVE'], 
            'level': 'campaign'
        }
        
        # Aplica o formato correto de data (preset ou custom dict)
        if isinstance(periodo_api, dict):
            params_insights['time_range'] = periodo_api
        else:
            params_insights['date_preset'] = periodo_api

        try:
            insights = account.get_insights(
                fields=['campaign_id', 'campaign_name'], 
                params=params_insights
            )
        except Exception as e:
            if "permission" in str(e).lower() or "200" in str(e):
                return {'id': account_id, 'nome': nome_conta, 'campanhas': {}, 'erro': "Sem permissão de acesso."}
            return {'id': account_id, 'nome': nome_conta, 'campanhas': {}, 'erro': f"Erro insights: {e}"}

        if not insights:
            return {'id': account_id, 'nome': nome_conta, 'campanhas': {}, 'erro': None}

        campanhas_dict = {}

        # PASSO 2: Buscar os anúncios dessas campanhas
        for item in insights:
            camp_id = item['campaign_id']
            nome_campanha = item.get('campaign_name', 'Campanha Desconhecida')
            
            try:
                camp = Campaign(camp_id)
                ads = camp.get_ads(fields=['creative'], params={'effective_status': ['ACTIVE']})
                
                if not ads:
                    continue
                    
                if nome_campanha not in campanhas_dict:
                    campanhas_dict[nome_campanha] = []
                    
                for ad in ads:
                    if 'creative' in ad and 'id' in ad['creative']:
                        c_id = ad['creative']['id']
                        c = AdCreative(c_id).api_get(fields=[
                            'name', 'image_url', 'thumbnail_url', 'video_id', 'object_id',
                            'asset_feed_spec', 'object_story_spec'
                        ], params={'thumbnail_width': 1080, 'thumbnail_height': 1080})
                        
                        lista_midias = extrair_midias_do_criativo(c, account_id)
                        campanhas_dict[nome_campanha].extend(lista_midias)
            except:
                continue 

        return {'id': account_id, 'nome': nome_conta, 'campanhas': campanhas_dict, 'erro': None}
        
    except Exception as e:
        return {'id': account_id, 'nome': account_id, 'campanhas': {}, 'erro': f"Falha na conexão: {e}"}

# O cache agora "sabe" qual é o período e recarrega se tu mudares a data
@st.cache_data(ttl=600)
def carregar_galeria(lista_ids, periodo_api):
    resultados = []
    barra = st.progress(0, text=f"🔎 A procurar criativos para o período selecionado...")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Passamos a data para dentro do executor
        futures = {executor.submit(buscar_criativos_da_conta, cid, periodo_api): cid for cid in lista_ids}
        for i, future in enumerate(as_completed(futures)):
            barra.progress(int(((i + 1) / len(lista_ids)) * 100), text=f"A analisar conta {i+1} de {len(lista_ids)}...")
            resultados.append(future.result())
            
    barra.empty()
    return resultados


def pontuar_midia(midia):
    score = 0
    if midia.get('tipo') == 'imagem':
        score += 20
    elif midia.get('tipo') == 'video':
        score += 10
        if midia.get('video_url'):
            score += 5

    origem = midia.get('origem')
    if origem == 'original':
        score += 10
    elif origem == 'preview':
        score += 4
    elif origem == 'thumbnail':
        score += 1
    return score

def deduplicar_midias(midias):
    melhores = {}
    for midia in midias:
        url = midia.get('cover_url') if midia.get('tipo') == 'video' else midia.get('url')
        if not url:
            url = midia.get('url')
        if not url:
            continue
        atual = melhores.get(url)
        if atual is None or pontuar_midia(midia) > pontuar_midia(atual):
            melhores[url] = midia
    return sorted(melhores.values(), key=pontuar_midia, reverse=True)


@st.cache_data(ttl=86400, show_spinner=False)
def baixar_bytes_midia(url):
    if not url:
        return None
    with urllib.request.urlopen(url, timeout=30) as resposta:
        return resposta.read()

col_reload, col_spacer = st.columns([1, 3])
with col_reload:
    if st.button("🔄 Recarregar Galeria", use_container_width=True):
        carregar_galeria.clear()
        st.rerun()

# --- EXECUÇÃO E LAYOUT ---
contas_ids = iniciar_api()

st.divider()

with st.spinner("A carregar mídias de alta resolução..."):
    # Passamos o período selecionado para a função de carga
    dados_galeria = carregar_galeria(contas_ids, periodo_final_api)

dados_galeria.sort(key=lambda item: item['nome'].lower())

# --- RENDERIZAÇÃO DA INTERFACE ---
contas_com_dados_exibidas = 0

for dados in dados_galeria:
    if dados['erro']:
        st.warning(f"⚠️ **{dados['nome']}**: {dados['erro']}")
        continue

    if filtro_visualizacao == "Ocultar Contas Zeradas" and not dados['campanhas']:
        continue

    qtd_campanhas = len(dados['campanhas'])
    contas_com_dados_exibidas += 1

    with st.expander(f"📁 **{dados['nome']}** ({qtd_campanhas} campanhas no período)", expanded=True):
        if qtd_campanhas == 0:
            st.info(f"⏸️ **{dados['nome']}**: Nenhuma campanha gerou resultados neste período.")
            continue

        for campanha_nome, midias in dados['campanhas'].items():
            midias_unicas = deduplicar_midias(midias)
            
            if not midias_unicas:
                continue
                
            st.markdown(f"#### 🏷️ {campanha_nome}")
            
            colunas = st.columns(4)
            for index, midia in enumerate(midias_unicas):
                col_atual = colunas[index % 4]
                
                with col_atual:
                    with st.container(border=True):
                        # Indicador Visual Elegante
                        if midia['tipo'] == 'video':
                            if midia.get('cover_origem') == 'preview':
                                st.caption("🎬 **Vídeo (capa em alta)**")
                            else:
                                st.caption("🎬 **Vídeo (thumbnail)**")
                        else:
                            if midia.get('origem') == 'original':
                                st.caption("🖼️ **Imagem original**")
                            else:
                                st.caption("🖼️ **Preview da imagem**")
                              
                        # Mídia e Botão
                        render_preview_html(midia)

                        if midia['tipo'] == 'video':
                            video_link = midia.get('video_url') or (f"https://www.facebook.com/watch/?v={midia.get('video_id')}" if midia.get('video_id') else None)
                            if video_link:
                                st.link_button("▶ Assistir vídeo", video_link, use_container_width=True)
                            if midia.get('cover_url'):
                                st.link_button("🖼️ Ver capa original", midia['cover_url'], use_container_width=True)

                        alvo_download = midia.get('video_url') or midia.get('cover_url') or midia.get('url')
                        nome_arquivo = (
                            f"video_{midia.get('video_id') or 'midia'}.mp4"
                            if midia.get('tipo') == 'video' and midia.get('video_url')
                            else (f"video_{midia.get('video_id') or 'midia'}_capa.jpg" if midia.get('tipo') == 'video' else "midia.jpg")
                        )
                        dados_download = baixar_bytes_midia(alvo_download)
                        if dados_download:
                            mime = "video/mp4" if nome_arquivo.endswith('.mp4') else "image/jpeg"
                            st.download_button(
                                label="⬇️ Baixar Mídia",
                                data=dados_download,
                                file_name=nome_arquivo,
                                mime=mime,
                                use_container_width=True,
                                key=f"download-{midia.get('tipo')}-{midia.get('video_id') or midia.get('url')}"
                            )
            st.divider()

if contas_com_dados_exibidas == 0:
    st.divider()
    st.subheader("Nenhuma conta com anúncios ativos no período selecionado.")

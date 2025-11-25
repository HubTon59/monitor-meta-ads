import sys
import os
from dotenv import load_dotenv
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount

# 1. Carregar variáveis
load_dotenv()

my_app_id = os.getenv('FB_APP_ID')
my_app_secret = os.getenv('FB_APP_SECRET')
my_access_token = os.getenv('FB_ACCESS_TOKEN')
# Agora lemos a lista de IDs
ids_string = os.getenv('FB_ACCOUNT_IDS')

def inicializar_api():
    if not my_app_id or not my_access_token:
        print("ERRO: Credenciais ausentes no .env")
        sys.exit(1)
    try:
        FacebookAdsApi.init(my_app_id, my_app_secret, my_access_token)
        print("\n=== Conexão API Iniciada com Sucesso ===\n")
    except Exception as e:
        print(f"Erro na conexão: {e}")
        sys.exit(1)

def obter_metricas(account_id):
    try:
        account = AdAccount(account_id)
        
        # --- MUDANÇA AQUI ---
        # Filtros para gestão em Tempo Real
        params = {
            'date_preset': 'today',          # Apenas dados de Hoje
            'effective_status': ['ACTIVE'],  # Apenas campanhas que estão Ligadas
            'level': 'campaign'
        }
        fields = ['campaign_name', 'spend', 'impressions', 'clicks', 'cpc', 'ctr']

        print(f"[{account_id}] A recolher dados de HOJE (Apenas Ativas)...")
        
        insights = account.get_insights(fields=fields, params=params)

        if not insights:
            print(f"   >> Nenhuma campanha ativa a gastar hoje.\n")
            print("="*70 + "\n")
            return

        # Cabeçalho Ajustado
        print(f"   {'CAMPANHA':<40} | {'GASTO':<10} | {'CLIQUES':<8} | {'CPC':<6}")
        print("   " + "-" * 75)

        total_gasto = 0.0

        for item in insights:
            nome = item.get('campaign_name')
            # O nome pode ser longo, vamos cortar se passar de 38 caracteres para não quebrar a tabela
            if len(nome) > 38:
                nome = nome[:35] + "..."

            gasto = float(item.get('spend', 0))
            cliques = item.get('clicks', 0)
            cpc = float(item.get('cpc', 0) if 'cpc' in item else 0)
            
            total_gasto += gasto

            print(f"   {nome:<40} | {gasto:<10.2f} | {cliques:<8} | {cpc:<6.2f}")
        
        print("   " + "-" * 75)
        print(f"   TOTAL GASTO HOJE: {total_gasto:.2f}")
        print("="*70 + "\n")

    except Exception as e:
        print(f"   [ERRO] Falha na conta {account_id}: {e}\n")

# --- EXECUÇÃO PRINCIPAL ---
if __name__ == "__main__":
    inicializar_api()

    # Verifica se existem IDs configurados
    if not ids_string:
        print("ERRO: Nenhum ID de conta encontrado no .env (FB_ACCOUNT_IDS)")
    else:
        # Transforma a string "act_1,act_2" numa lista ["act_1", "act_2"]
        lista_de_contas = ids_string.split(',')

        print(f"Iniciando monitorização de {len(lista_de_contas)} contas...\n")

        # O Loop Mágico: passa por cada conta da lista
        for conta_atual in lista_de_contas:
            # .strip() remove espaços em branco acidentais
            obter_metricas(conta_atual.strip())
            
    print("--- Fim da Execução ---")
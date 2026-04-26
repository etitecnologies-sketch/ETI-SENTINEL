import requests
import time
import sys

# URLs do Sistema ETI SENTINEL
API_URL = "https://monitoring-system-production-1e5a.up.railway.app"
FRONTEND_URL = "https://powerful-unity-production-c566.up.railway.app"
WS_URL = "https://monitoring-system-production-1e5a.up.railway.app/publish" # Endpoint interno via Ingest

def check_url(name, url):
    print(f"🔍 Verificando {name}: {url}...")
    try:
        start = time.time()
        # Tenta um GET simples com timeout de 10s
        response = requests.get(url, timeout=10)
        end = time.time()
        latency = round((end - start) * 1000, 2)
        
        if response.status_code == 200:
            print(f"✅ {name} está ONLINE! (Status: 200, Latência: {latency}ms)")
            return True
        elif response.status_code == 502:
            print(f"❌ {name} retornou 502 Bad Gateway. (O serviço no Railway provavelmente está travado)")
        elif response.status_code == 404:
            print(f"❌ {name} retornou 404 Not Found. (URL incorreta ou serviço não publicado)")
        else:
            print(f"⚠️ {name} retornou Status {response.status_code}.")
        return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Erro de Conexão: Não foi possível conectar ao host {name}.")
    except requests.exceptions.Timeout:
        print(f"❌ Timeout: O servidor de {name} demorou demais para responder.")
    except Exception as e:
        print(f"❌ Erro inesperado em {name}: {str(e)}")
    return False

def diagnostic():
    print("="*50)
    print("🚀 ETI SENTINEL - Script de Diagnóstico")
    print("="*50)
    
    # 1. Testar Ingest API
    api_ok = check_url("Ingest API (Backend)", f"{API_URL}/auth/status")
    
    print("-" * 30)
    
    # 2. Testar Frontend
    frontend_ok = check_url("Dashboard (Frontend)", FRONTEND_URL)
    
    print("-" * 30)
    
    # 3. Resumo e Sugestões
    print("\n📝 RESUMO DO DIAGNÓSTICO:")
    if api_ok and frontend_ok:
        print("🎉 Tudo parece estar funcionando corretamente!")
    elif not api_ok:
        print("🚨 PROBLEMA NO BACKEND (API):")
        print("   - O Frontend não consegue logar porque a API não responde.")
        print("   - Ação sugerida: Vá no Railway, entre no serviço 'ingest-api' e faça um RESTART.")
    elif not frontend_ok:
        print("🚨 PROBLEMA NO FRONTEND:")
        print("   - A interface visual pode estar fora do ar.")
        print("   - Ação sugerida: Verifique o serviço 'frontend' no Railway.")
    
    print("\n💡 DICA: Se a API estiver 502, verifique os logs no Railway para ver se há erros de conexão com o Banco de Dados (PostgreSQL).")
    print("="*50)

if __name__ == "__main__":
    diagnostic()

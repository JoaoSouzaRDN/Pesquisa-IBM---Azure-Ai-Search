from flask import Flask, request, jsonify
import requests
import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env (para desenvolvimento local)
load_dotenv()

app = Flask(__name__)

# Configurações do Azure AI Search (obtidas do ambiente)
AZURE_SEARCH_SERVICE_NAME = os.environ.get("AZURE_SEARCH_SERVICE_NAME")
AZURE_SEARCH_INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME")
AZURE_SEARCH_API_KEY = os.environ.get("AZURE_SEARCH_API_KEY")
AZURE_SEARCH_API_VERSION = "2025-09-01"

# API Key para proteger o seu middleware (watsonx Orchestrate enviará esta chave)
MIDDLEWARE_API_KEY = os.environ.get("MIDDLEWARE_API_KEY")

# Campos do seu índice do Azure AI Search que você deseja mapear
AZURE_SEARCH_FIELDS = "title, content, url"

# Rota raiz para verificar se o serviço está online
@app.route("/", methods=["GET"])
def home():
    return "Middleware Azure AI Search para watsonx Orchestrate está online!", 200

@app.route("/search", methods=["POST"])
def search():
    # LOG DE DIAGNÓSTICO: Imprime todos os cabeçalhos recebidos
    app.logger.info("--- CABEÇALHOS RECEBIDOS ---")
    for header, value in request.headers.items():
        app.logger.info(f"{header}: {value}")
    app.logger.info("---------------------------")

    # Tenta pegar a chave de qualquer lugar possível
    recebida = (request.headers.get("X-API-Key") or 
                request.headers.get("Authorization") or 
                request.headers.get("api-key")) # Algumas ferramentas usam assim

    if recebida and recebida.startswith("Bearer "):
        recebida = recebida.split(" ")[1]
    
    # Se mesmo assim não vier nada, vamos aceitar temporariamente para ver a pesquisa funcionar
    # DESCOMENTE A LINHA ABAIXO SE QUISER TESTAR SEM TRAVA:
    # return process_search() 

    if recebida != MIDDLEWARE_API_KEY:
        app.logger.warning(f"ACESSO NEGADO: Chave recebida '{recebida}' não bate com a esperada.")
        return jsonify({"error": "Unauthorized"}), 401

    return process_search()

def process_search():
    # Coloque aqui o restante do seu código de pesquisa (Azure, etc)
    # ... (o código que você já tem)

    # 1. Validação das variáveis de ambiente essenciais
    if not all([AZURE_SEARCH_SERVICE_NAME, AZURE_SEARCH_INDEX_NAME, AZURE_SEARCH_API_KEY, MIDDLEWARE_API_KEY]):
        missing_vars = [var_name for var_name, var_value in {
            "AZURE_SEARCH_SERVICE_NAME": AZURE_SEARCH_SERVICE_NAME,
            "AZURE_SEARCH_INDEX_NAME": AZURE_SEARCH_INDEX_NAME,
            "AZURE_SEARCH_API_KEY": AZURE_SEARCH_API_KEY,
            "MIDDLEWARE_API_KEY": MIDDLEWARE_API_KEY
        }.items() if not var_value]
        error_msg = f"Configuration error: Missing environment variables: {', '.join(missing_vars)}"
        app.logger.error(f"Erro: {error_msg}")
        return jsonify({"error": error_msg}), 500

    # 2. Validação da API Key do Middleware
    recebida = request.headers.get("Authorization")
    
    # Se a IBM enviar como "ApiKey teste123", nós limpamos o prefixo
    if recebida and recebida.startswith("ApiKey "):
        recebida = recebida.replace("ApiKey ", "")

    app.logger.info(f"Chave limpa para comparação: {recebida}")

    if recebida != MIDDLEWARE_API_KEY:
        app.logger.warning(f"ACESSO NEGADO: Chave '{recebida}' inválida.")
        return jsonify({"error": "Unauthorized"}), 401



    # 3. Obter a requisição do watsonx Orchestrate
    try:
        watsonx_request = request.get_json(force=True) # force=True para garantir que o body seja JSON
        app.logger.info(f"Requisição do watsonx Orchestrate: {watsonx_request}")
    except Exception as e:
        app.logger.error(f"Erro ao parsear JSON da requisição do watsonx Orchestrate: {e}")
        return jsonify({"error": "Invalid JSON in request body"}), 400

    query = watsonx_request.get('query')

    if not query:
        app.logger.warning("Parâmetro 'query' ausente na requisição do watsonx Orchestrate.")
        return jsonify({"error": "Query parameter 'query' is missing in watsonx request"}), 400

    # 4. Construir a requisição para o Azure AI Search
    azure_search_url = f"https://{AZURE_SEARCH_SERVICE_NAME}.search.windows.net/indexes/{AZURE_SEARCH_INDEX_NAME}/docs/search?api-version={AZURE_SEARCH_API_VERSION}"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_SEARCH_API_KEY
    }
    azure_search_payload = {
        "search": query,
        "queryType": "simple",
        "searchMode": "all",
        "searchFields": AZURE_SEARCH_FIELDS,
        "select": AZURE_SEARCH_FIELDS,
        "top": 5 # Limitar o número de resultados para o watsonx Orchestrate
    }
    app.logger.info(f"Enviando requisição ao Azure AI Search: URL={azure_search_url}, Payload={azure_search_payload}")

    # 5. Chamar o Azure AI Search
    try:
        azure_response = requests.post(azure_search_url, headers=headers, json=azure_search_payload)
        azure_response.raise_for_status() # Levanta um erro para códigos de status HTTP ruins (4xx ou 5xx)
        azure_results = azure_response.json()
        app.logger.info(f"Resposta do Azure AI Search recebida (Status: {azure_response.status_code}): {azure_results}")
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Erro ao chamar Azure AI Search: {e}")
        # Tenta extrair mais detalhes do erro HTTP, se disponível
        if hasattr(e, 'response') and e.response is not None:
            app.logger.error(f"Azure AI Search Response Error: {e.response.text}")
            return jsonify({"error": f"Failed to connect to Azure AI Search: {e.response.text}"}), e.response.status_code
        return jsonify({"error": "Failed to connect to Azure AI Search"}), 500

    # 6. Mapear os resultados do Azure AI Search para o formato do watsonx Orchestrate
    search_results = []
    for doc in azure_results.get('value', []):
        search_results.append({
            "title": doc.get('title', 'No Title'),
            "body": doc.get('content', 'No Content'),
            "url": doc.get('url', '#')
            # Você pode adicionar lógica para 'highlight' se o Azure AI Search retornar essa informação
        })
    app.logger.info(f"Resultados mapeados para watsonx Orchestrate: {search_results}")

    return jsonify({"search_results": search_results})

if __name__ == '__main__':
    # Para desenvolvimento local, você pode definir as variáveis de ambiente aqui para testes
    # ou confiar no .env carregado por load_dotenv()
    app.run(host='0.0.0.0', port=5000)

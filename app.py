from flask import Flask, request, jsonify
import requests
import os
from dotenv import load_dotenv

#Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

app = Flask(__name__)

# Configurações do Azure AI Search (obtenha do portal do Azure)
AZURE_SEARCH_SERVICE_NAME = os.environ.get("AZURE_SEARCH_SERVICE_NAME")
AZURE_SEARCH_INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME")
AZURE_SEARCH_API_KEY = os.environ.get("AZURE_SEARCH_API_KEY")
AZURE_SEARCH_API_VERSION = "2025-09-01"

# API Key para proteger o seu middleware (watsonx Orchestrate enviará esta chave)
MIDDLEWARE_API_KEY = os.environ.get("MIDDLEWARE_API_KEY")

# Campos do seu índice do Azure AI Search que você deseja mapear
AZURE_SEARCH_FIELDS = "title, content, url"

@app.route("/search", methods=["POST"])
def search():
    # 1. Validação da API Key do Middleware
    if not MIDDLEWARE_API_KEY:
        print("Erro: MIDDLEWARE_API_KEY não configurada no ambiente.")
        return jsonify({"error": "Middleware API Key not configured"}), 500

    if request.headers.get("X-API-Key") != MIDDLEWARE_API_KEY:
        return jsonify({"error": "Unauthorized: Invalid Middleware API Key"}), 401

    watsonx_request = request.get_json()
    query = watsonx_request.get('query') if watsonx_request else None

    if not query:
        return jsonify({"error": "Query parameter is missing"}), 400

    # Construir a requisição para o Azure AI Search
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
        "top": 5
    }

    try:
        azure_response = requests.post(azure_search_url, headers=headers, json=azure_search_payload)
        azure_response.raise_for_status()
        azure_results = azure_response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao chamar Azure AI Search: {e}")
        return jsonify({"error": "Failed to connect to Azure AI Search"}), 500

    # Mapear os resultados do Azure AI Search para o formato do watsonx Orchestrate
    search_results = []
    for doc in azure_results.get('value', []):
        search_results.append({
            "title": doc.get('title', 'No Title'),
            "body": doc.get('content', 'No Content'),
            "url": doc.get('url', '#')
        })

    return jsonify({"search_results": search_results})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
from flask import Flask, request, jsonify
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configurações do Azure (Pegando do ambiente do Render)
AZURE_SEARCH_SERVICE_NAME = os.environ.get("AZURE_SEARCH_SERVICE_NAME")
AZURE_SEARCH_INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX_NAME")
AZURE_SEARCH_API_KEY = os.environ.get("AZURE_SEARCH_API_KEY")
AZURE_SEARCH_API_VERSION = "2025-09-01"
MIDDLEWARE_API_KEY = os.environ.get("MIDDLEWARE_API_KEY")
AZURE_SEARCH_FIELDS = "title, content, url"

@app.route("/", methods=["GET"])
def home():
    return "Middleware Online!", 200

@app.route("/search", methods=["POST"])
def search():
    # 1. Captura o que veio da IBM
    auth_header = request.headers.get("Authorization")
    app.logger.info(f"Header bruto recebido: {auth_header}")

    # 2. Limpa o prefixo 'ApiKey ' se ele existir
    recebida = auth_header
    if auth_header and auth_header.startswith("ApiKey "):
        recebida = auth_header.replace("ApiKey ", "")
    
    app.logger.info(f"Chave após limpeza: {recebida}")
    app.logger.info(f"Chave esperada (do Render): {MIDDLEWARE_API_KEY}")

    # 3. Compara
    if recebida != MIDDLEWARE_API_KEY:
        app.logger.warning("ACESSO NEGADO: Chaves não conferem.")
        return jsonify({"error": "Unauthorized"}), 401

    # 4. Se passou, segue para a pesquisa no Azure
    watsonx_request = request.get_json(force=True)
    query = watsonx_request.get('query')
    
    if not query:
        return jsonify({"error": "Query missing"}), 400

    azure_url = f"https://{AZURE_SEARCH_SERVICE_NAME}.search.windows.net/indexes/{AZURE_SEARCH_INDEX_NAME}/docs/search?api-version={AZURE_SEARCH_API_VERSION}"
    
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_SEARCH_API_KEY
    }
    
    payload = {
        "search": query,
        "select": AZURE_SEARCH_FIELDS,
        "top": 5
    }

    try:
        app.logger.info(f"Pesquisando no Azure: {query}" )
        response = requests.post(azure_url, headers=headers, json=payload)
        response.raise_for_status()
        results = response.json()
        
        search_results = []
        for doc in results.get('value', []):
            search_results.append({
                "title": doc.get('title', 'Sem Título'),
                "body": doc.get('content', 'Sem Conteúdo'),
                "url": doc.get('url', '#')
            })
        
        return jsonify({"search_results": search_results})

    except Exception as e:
        app.logger.error(f"Erro no Azure: {str(e)}")
        return jsonify({"error": "Erro na busca"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

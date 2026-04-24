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
AZURE_SEARCH_API_VERSION = "2024-07-01"
MIDDLEWARE_API_KEY = os.environ.get("MIDDLEWARE_API_KEY")

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
    try:
        watsonx_request = request.get_json(force=True)
        query = watsonx_request.get('query')
    except Exception as e:
        app.logger.error(f"Erro ao ler JSON da IBM: {str(e)}")
        return jsonify({"error": "Invalid JSON"}), 400
    
    if not query:
        return jsonify({"error": "Query missing"}), 400

    azure_url = f"https://{AZURE_SEARCH_SERVICE_NAME}.search.windows.net/indexes/{AZURE_SEARCH_INDEX_NAME}/docs/search?api-version={AZURE_SEARCH_API_VERSION}"
    
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_SEARCH_API_KEY
    }
    
    # Payload para o Azure (Removido o 'select' para evitar erro de campo inexistente)
    payload = {
        "search": query,
        "top": 5
    }

    try:
        app.logger.info(f"Pesquisando no Azure: {query}")
        response = requests.post(azure_url, headers=headers, json=payload)
        
        # DEBUG: Se o Azure retornar erro, imprime a mensagem real da Microsoft
        if response.status_code != 200:
            app.logger.error(f"DETALHE DO ERRO AZURE (Status {response.status_code}): {response.text}")
        
        response.raise_for_status()
        results = response.json()
        
        search_results = []
        for doc in results.get('value', []):
            # Mapeamento inteligente: tenta os nomes mais comuns do Azure RAG
            titulo = doc.get('title') or doc.get('metadata_storage_name') or doc.get('id') or 'Sem Título'
            conteudo = doc.get('content') or doc.get('chunk') or doc.get('text') or 'Sem Conteúdo'
            link = doc.get('url') or doc.get('metadata_storage_path') or '#'

            search_results.append({
                "title": titulo,
                "body": conteudo,
                "url": link
            })
        
        return jsonify({"search_results": search_results})

    except Exception as e:
        app.logger.error(f"Erro na integração: {str(e)}")
        return jsonify({"error": "Erro na busca"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

from flask import Flask, request, jsonify, send_from_directory
from graph_service import query_graph_by_router, test_neo4j
from line_service import handle_line_event

from pyngrok import ngrok
import os

app = Flask(__name__)

# ===== 基本 API =====
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok"})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/test/neo4j", methods=["GET"])
def test_db():
    try:
        return jsonify(test_neo4j()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 200

@app.route("/graph/query", methods=["POST"])
def graph_query():
    try:
        payload = request.get_json(force=True) or {}

        # 如果 Dify 傳來的是 JSON 字串，轉成 dict
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)

        # 如果 Dify 傳來 {"text": "...json..."} 這種格式，也處理
        if isinstance(payload, dict) and "text" in payload and isinstance(payload["text"], str):
            try:
                payload = json.loads(payload["text"])
            except Exception:
                pass

        print("DEBUG payload =", payload)

        result = query_graph_by_router(payload)

        print("DEBUG result =", result)
        return jsonify(result), 200

    except Exception as e:
        print("ERROR /graph/query =", str(e))
        return jsonify({
            "graph_result": [{
                "query_type": "system_error",
                "found": False,
                "message": str(e)
            }]
        }), 200

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("/content/test/static", filename)

@app.route("/line/webhook", methods=["POST"])
def line_webhook():
    body = request.get_json(force=True) or {}
    events = body.get("events", [])

    for event in events:
        handle_line_event(event)

    return "OK", 200


# ===== 啟動區（重點）=====
if __name__ == "__main__":

    # 設定 ngrok token
    from config import NGROK_AUTH_TOKEN

    NGROK_TOKEN = NGROK_AUTH_TOKEN
    if not NGROK_TOKEN:
        raise Exception("請先設定 NGROK_AUTH_TOKEN")

    ngrok.set_auth_token(NGROK_TOKEN)

    # 關閉舊 tunnel（避免錯誤）
    try:
        for t in ngrok.get_tunnels():
            ngrok.disconnect(t.public_url)
    except:
        pass

    public_url = ngrok.connect(5000).public_url

    print("🚀 Server running")
    print("LINE webhook:", public_url + "/line/webhook")
    print("Dify graph API:", public_url + "/graph/query")
    print("Neo4j test:", public_url + "/test/neo4j")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
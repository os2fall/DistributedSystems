from flask import Flask, request, jsonify

app = Flask(__name__)

registry = {}

@app.route("/register", methods=["POST"])
def register_service():
    """Ендпоінт для реєстрації мікросервісів при їх старті"""
    data = request.get_json()
    
    if not data or "service_name" not in data or "url" not in data:
        return jsonify({"error": "Invalid request. 'service_name' and 'url' are required."}), 400

    service_name = data["service_name"]
    url = data["url"]
    
    if service_name not in registry:
        registry[service_name] = set()
        
    registry[service_name].add(url)
    print(f"[INFO] Registered {service_name} at {url}")
    
    return jsonify({"message": f"Service {service_name} registered successfully"}), 201

@app.route("/services/<service_name>", methods=["GET"])
def get_service_urls(service_name):
    """Ендпоінт для отримання списку всіх зареєстрованих адрес конкретного сервісу"""
    if service_name not in registry or not registry[service_name]:
        return jsonify({"error": f"Service {service_name} not found or no instances available"}), 404

    urls = list(registry[service_name])
    return jsonify({"service_name": service_name, "urls": urls}), 200

@app.route("/services", methods=["GET"])
def get_all_services():
    """Допоміжний ендпоінт, щоб подивитися всі зареєстровані сервіси (корисно для дебагу)"""
    formatted_registry = {k: list(v) for k, v in registry.items()}
    return jsonify(formatted_registry), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
import time
import random
from uuid import uuid4
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

LOGGING_NODES = [
    "http://logging-service-1:8081/logging",
    "http://logging-service-2:8081/logging",
    "http://logging-service-3:8081/logging"
]

COUNTER_SERVICE_URL = "http://counter-service:8082"

time_logging = 0.0
time_counter = 0.0

def call_logging_service(method, json_data=None):
    global time_logging
    nodes = LOGGING_NODES.copy()
    random.shuffle(nodes)
    
    for url in nodes:
        try:
            start_time = time.time()
            if method == "POST":
                resp = requests.post(url, json=json_data, timeout=2)
            else:
                resp = requests.get(url, timeout=2)
            
            if resp.status_code in [200, 201]:
                time_logging += (time.time() - start_time)
                return resp
        except requests.exceptions.RequestException:
            continue
            
    raise Exception("Всі екземпляри logging-service недоступні")

@app.route("/", methods=["POST"])
def process_transaction():
    global time_counter
    
    data = request.get_json()
    if not data or "user_Id" not in data or "amount" not in data:
        return jsonify({"error": "Bad request"}), 400

    user_id = data["user_Id"]
    amount = data["amount"]
    transaction_id = str(uuid4())

    log_data = {
        "transaction_Id": transaction_id, 
        "msg": {"user_Id": user_id, "amount": amount}
    }

    try:
        call_logging_service("POST", log_data)

        counter_data = {"user_Id": user_id, "amount": amount}
        start_time = time.time()
        counter_resp = requests.post(f"{COUNTER_SERVICE_URL}/transaction", json=counter_data, timeout=5)
        time_counter += (time.time() - start_time)

        if counter_resp.status_code == 200:
            balance = counter_resp.json().get("balance")
            return jsonify({"transaction_Id": transaction_id, "balance": balance}), 200
        else:
            return jsonify({"error": "Counter service error"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/user/<user_id>", methods=["GET"])
def get_user_data(user_id):
    global time_counter
    
    try:
        log_resp = call_logging_service("GET")
        
        start_time = time.time()
        count_resp = requests.get(f"{COUNTER_SERVICE_URL}/user/{user_id}", timeout=5)
        time_counter += (time.time() - start_time)

        all_messages = log_resp.json()
        
        user_transactions = [
            m for m in all_messages if isinstance(m, dict) and m.get("user_Id") == user_id
        ]

        balance = count_resp.json().get("balance", 0.0)

        return jsonify({"balance": balance, "transactions": user_transactions}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/accounts", methods=["GET"])
def get_accounts():
    global time_counter
    try:
        start_time = time.time()
        count_resp = requests.get(f"{COUNTER_SERVICE_URL}/accounts", timeout=5)
        time_counter += (time.time() - start_time)
        return jsonify(count_resp.json()), 200
    except Exception:
        return jsonify({"error": "Counter service unavailable"}), 500

@app.route("/metrics", methods=["GET", "DELETE"])
def handle_metrics():
    global time_logging, time_counter
    if request.method == "GET":
        return jsonify({
            "time_logging": round(time_logging, 4), 
            "time_counter": round(time_counter, 4)
        }), 200
    elif request.method == "DELETE":
        time_logging = 0.0
        time_counter = 0.0
        return jsonify({"status": "metrics reset"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
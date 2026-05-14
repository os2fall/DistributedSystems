import os
import time
import random
import json
from uuid import uuid4
import requests
from flask import Flask, request, jsonify
import hazelcast
import threading

app = Flask(__name__)

CONFIG_SERVER_URL = os.getenv("CONFIG_SERVER_URL", "http://config-server:8000")
SELF_URL = os.getenv("SELF_URL", "http://127.0.0.1:8080")

client = hazelcast.HazelcastClient(
    cluster_name="khashcha_lab_2",
    cluster_members=["hz1:5701", "hz2:5701", "hz3:5701"]
)
tx_queue = client.get_queue("transaction_queue").blocking()

time_logging = 0.0
time_counter = 0.0

def register_service():
    payload = {
        "service_name": "facade-service",
        "url": SELF_URL
    }
    while True:
        try:
            response = requests.post(f"{CONFIG_SERVER_URL}/register", json=payload, timeout=5)
            if response.status_code == 201:
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(5)

def get_service_urls(service_name):
    try:
        resp = requests.get(f"{CONFIG_SERVER_URL}/services/{service_name}", timeout=2)
        if resp.status_code == 200:
            return resp.json().get("urls", [])
    except requests.exceptions.RequestException:
        pass
    return []

def call_logging_service(method, json_data=None):
    global time_logging
    
    urls = get_service_urls("logging-service")
    if not urls:
        raise Exception("logging-service is unavailable")
        
    random.shuffle(urls)
    
    for url in urls:
        try:
            start_time = time.time()
            if method == "POST":
                resp = requests.post(f"{url}/logging", json=json_data, timeout=2)
            else:
                resp = requests.get(f"{url}/logging", timeout=2)
            
            if resp.status_code in [200, 201]:
                time_logging += (time.time() - start_time)
                return resp
        except requests.exceptions.RequestException:
            continue
            
    raise Exception("All logging-service instances are down")

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

        counter_msg = {"user_Id": user_id, "amount": amount, "transaction_Id": transaction_id}
        
        start_time = time.time()
        tx_queue.put(json.dumps(counter_msg))
        time_counter += (time.time() - start_time)

        return jsonify({"transaction_Id": transaction_id, "status": "In Queue"}), 202

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/user/<user_id>", methods=["GET"])
def get_user_data(user_id):
    global time_counter
    
    try:
        log_resp = call_logging_service("GET")
        
        counter_urls = get_service_urls("counter-service")
        if not counter_urls:
            raise Exception("counter-service is unavailable")
            
        counter_url = random.choice(counter_urls)
        
        start_time = time.time()
        count_resp = requests.get(f"{counter_url}/user/{user_id}", timeout=5)
        time_counter += (time.time() - start_time)

        all_messages = log_resp.json()
        
        user_transactions = [
            m for m in all_messages if isinstance(m, dict) and m.get("user_Id") == user_id
        ]

        balance = count_resp.json().get("balance", 0.0) if count_resp.status_code == 200 else 0.0

        return jsonify({"balance": balance, "transactions": user_transactions}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/accounts", methods=["GET"])
def get_accounts():
    global time_counter
    try:
        counter_urls = get_service_urls("counter-service")
        if not counter_urls:
            raise Exception("counter-service is unavailable")
            
        counter_url = random.choice(counter_urls)
        
        start_time = time.time()
        count_resp = requests.get(f"{counter_url}/accounts", timeout=5)
        time_counter += (time.time() - start_time)
        return jsonify(count_resp.json()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    threading.Thread(target=register_service, daemon=True).start()
    app.run(host="0.0.0.0", port=8080, threaded=True)
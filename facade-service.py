import time
from uuid import uuid4
import requests
from flask import Flask, request, jsonify
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

app = Flask(__name__)

logging_service = "http://logging-service:8081/logging"
counter_service = "http://counter-service:8082"

time_logging = 0.0
time_counter = 0.0

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=2))
def send_request(method, url, json_data=None):
    if method == "POST":
        return requests.post(url, json=json_data, timeout=5)
    return requests.get(url, timeout=5)

@app.route("/", methods=["POST"])
def process_transaction():
    global time_logging, time_counter
    
    data = request.get_json()
    if not data or "user_Id" not in data or "amount" not in data:
        return jsonify({"error": "Bad request"}), 400

    user_id = data["user_Id"]
    amount = data["amount"]
    transaction_id = str(uuid4())

    msg = {"user_Id": user_id, "amount": amount}
    log_data = {"transaction_Id": transaction_id, "msg": msg}

    try:
        start_time = time.time()
        send_request("POST", logging_service, log_data)
        time_logging += (time.time() - start_time)

        counter_data = {"user_Id": user_id, "amount": amount}
        start_time = time.time()
        counter_resp = send_request("POST", f"{counter_service}/transaction", counter_data)
        time_counter += (time.time() - start_time)

        balance = counter_resp.json().get("balance")
        return jsonify({"transaction_Id": transaction_id, "balance": balance}), 200

    except RetryError:
        return jsonify({"error": "Internal services unavailable"}), 500

@app.route("/user/<user_id>", methods=["GET"])
def get_user(user_id):
    global time_logging, time_counter
    
    try:
        start_time = time.time()
        log_resp = send_request("GET", logging_service)
        time_logging += (time.time() - start_time)
        
        start_time = time.time()
        count_resp = send_request("GET", f"{counter_service}/user/{user_id}")
        time_counter += (time.time() - start_time)

        all_messages = log_resp.json()
        
        user_transactions = []
        for msg in all_messages:
            if isinstance(msg, dict) and msg.get("user_Id") == user_id:
                user_transactions.append(msg)

        balance = count_resp.json().get("balance", 0.0)

        return jsonify({"balance": balance, "transactions": user_transactions}), 200

    except RetryError:
        return jsonify({"error": "Internal services unavailable"}), 500

@app.route("/accounts", methods=["GET"])
def get_accounts():
    global time_counter
    try:
        start_time = time.time()
        count_resp = send_request("GET", f"{counter_service}/accounts")
        time_counter += (time.time() - start_time)
        return jsonify(count_resp.json()), 200
    except RetryError:
        return jsonify({"error": "Counter service unavailable"}), 500

@app.route("/metrics", methods=["GET", "DELETE"])
def metrics():
    global time_logging, time_counter
    if request.method == "GET":
        return jsonify({"time_logging": time_logging, "time_counter": time_counter}), 200
    elif request.method == "DELETE":
        time_logging = 0.0
        time_counter = 0.0
        return jsonify({"status": "metrics reset"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
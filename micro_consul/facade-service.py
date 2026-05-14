import os
import time
import random
import json
from uuid import uuid4
import requests
from flask import Flask, request, jsonify
import hazelcast
import consul
import threading

app = Flask(__name__)

CONSUL_HOST = os.getenv("CONSUL_HOST", "localhost")
SERVICE_IP = os.getenv("SERVICE_IP", "127.0.0.1")
SERVICE_PORT = 8080
SERVICE_NAME = "facade-service"

c = consul.Consul(host=CONSUL_HOST, port=8500)

time_logging = 0.0
time_counter = 0.0

def get_consul_kv(key, default_value):
    index, data = c.kv.get(key)
    if data is None:
        c.kv.put(key, default_value)
        return default_value
    return data['Value'].decode('utf-8')

def get_service_addresses(service_name):
    index, nodes = c.health.service(service_name, passing=True)
    addresses = []
    for node in nodes:
        addr = node['Service']['Address']
        port = node['Service']['Port']
        addresses.append(f"http://{addr}:{port}")
    return addresses

def register_with_consul():
    service_id = f"{SERVICE_NAME}-{SERVICE_IP}-{SERVICE_PORT}"
    check = consul.Check.http(f"http://{SERVICE_IP}:{SERVICE_PORT}/health", interval="10s")
    c.agent.service.register(
        name=SERVICE_NAME,
        service_id=service_id,
        address=SERVICE_IP,
        port=SERVICE_PORT,
        check=check
    )

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "UP"}), 200

hz_members_str = get_consul_kv("config/hazelcast/members", "hz1:5701,hz2:5701,hz3:5701")
hz_members = hz_members_str.split(",")

hz_client = hazelcast.HazelcastClient(
    cluster_name="khashcha_lab_2",
    cluster_members=hz_members
)

queue_name = get_consul_kv("config/mq/queue_name", "transaction_queue")
tx_queue = hz_client.get_queue(queue_name).blocking()

def call_logging_service(method, json_data=None):
    global time_logging
    
    urls = get_service_addresses("logging-service")
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
        
        counter_urls = get_service_addresses("counter-service")
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
        counter_urls = get_service_addresses("counter-service")
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
    register_with_consul()
    app.run(host="0.0.0.0", port=SERVICE_PORT, threaded=True)
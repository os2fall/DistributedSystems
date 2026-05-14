import os
import time
import json
import threading
import requests
from flask import Flask, jsonify
from pymongo import MongoClient
import hazelcast
import consul
import atexit

app = Flask(__name__)

CONSUL_HOST = os.getenv("CONSUL_HOST", "localhost")
SERVICE_IP = os.getenv("SERVICE_IP", "127.0.0.1")
SERVICE_PORT = 8082
SERVICE_NAME = "counter-service"

c = consul.Consul(host=CONSUL_HOST, port=8500)

client_db = MongoClient("mongodb://mongodb:27017/")
db = client_db["banking_db"]
balances_collection = db["balances"]

def setup_mq_config():
    mq_config_key = "config/mq/queue_name"
    index, data = c.kv.get(mq_config_key)
    
    if data is None:
        queue_name = "transaction_queue"
        c.kv.put(mq_config_key, queue_name)
        return queue_name
    else:
        queue_name = data['Value'].decode('utf-8')
        return queue_name

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
    atexit.register(lambda: c.agent.service.deregister(service_id))

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "UP"}), 200

hz_client = hazelcast.HazelcastClient(
    cluster_name="khashcha_lab_2",
    cluster_members=["hz1:5701", "hz2:5701", "hz3:5701"]
)

queue_name = setup_mq_config()
tx_queue = hz_client.get_queue(queue_name).blocking()

def consume_messages():
    while True:
        try:
            msg_str = tx_queue.take()
            if msg_str:
                data = json.loads(msg_str)
                user_id = data.get("user_Id")
                amount = float(data.get("amount", 0))
                
                if user_id:
                    balances_collection.find_one_and_update(
                        {"user_Id": user_id},
                        {"$inc": {"balance": amount}},
                        upsert=True
                    )
        except Exception:
            time.sleep(1)

@app.route("/user/<user_id>", methods=["GET"])
def get_user_balance(user_id):
    user_doc = balances_collection.find_one({"user_Id": user_id})
    balance = user_doc["balance"] if user_doc else 0.0
    return jsonify({"user_Id": user_id, "balance": balance}), 200

@app.route("/accounts", methods=["GET"])
def get_all_balances():
    accounts = list(balances_collection.find({}, {"_id": 0}))
    accounts_dict = {acc["user_Id"]: acc["balance"] for acc in accounts}
    return jsonify(accounts_dict), 200

if __name__ == "__main__":
    register_with_consul()
    threading.Thread(target=consume_messages, daemon=True).start()
    app.run(host="0.0.0.0", port=SERVICE_PORT, threaded=True)
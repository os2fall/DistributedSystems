import os
import time
import json
import threading
import requests
from flask import Flask, jsonify
from pymongo import MongoClient
import hazelcast

app = Flask(__name__)

CONFIG_SERVER_URL = os.getenv("CONFIG_SERVER_URL", "http://config-server:8000")
SELF_URL = os.getenv("SELF_URL", "http://127.0.0.1:8082")

client_db = MongoClient("mongodb://mongodb:27017/")
db = client_db["banking_db"]
balances_collection = db["balances"]

hz_client = hazelcast.HazelcastClient(
    cluster_name="khashcha_lab_2",
    cluster_members=["hz1:5701", "hz2:5701", "hz3:5701"]
)
tx_queue = hz_client.get_queue("transaction_queue").blocking()

def register_service():
    payload = {
        "service_name": "counter-service",
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
    threading.Thread(target=register_service, daemon=True).start()
    threading.Thread(target=consume_messages, daemon=True).start()
    app.run(host="0.0.0.0", port=8082, threaded=True)
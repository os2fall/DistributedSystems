import os
import requests
from flask import Flask, request, jsonify
import hazelcast
import consul
import atexit

app = Flask(__name__)

CONSUL_HOST = os.getenv("CONSUL_HOST", "localhost")
SERVICE_IP = os.getenv("SERVICE_IP", "127.0.0.1")
SERVICE_PORT = 8081
SERVICE_NAME = "logging-service"

c = consul.Consul(host=CONSUL_HOST, port=8500)

def setup_hazelcast_config():
    hz_config_key = "config/hazelcast/members"
    index, data = c.kv.get(hz_config_key)
    
    if data is None:
        default_members = "hz1:5701,hz2:5701,hz3:5701"
        c.kv.put(hz_config_key, default_members)
        return default_members.split(",")
    else:
        members_str = data['Value'].decode('utf-8')
        return members_str.split(",")

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

hz_members = setup_hazelcast_config()

client = hazelcast.HazelcastClient(
    cluster_name="khashcha_lab_2",
    cluster_members=hz_members
)
msg_map = client.get_map("messages").blocking()

@app.route("/logging", methods=["POST", "GET"])
def data_logger():
    if request.method == "POST":
        data = request.get_json()
        if not data or "transaction_Id" not in data or "msg" not in data:
            return jsonify({"error": "Invalid request"}), 400

        transaction_id = data["transaction_Id"]
        msg = data["msg"]

        if msg_map.contains_key(transaction_id):
            return jsonify({"error": "Conflict"}), 409

        msg_map.put(transaction_id, msg)
        return jsonify({"success": "Logged"}), 201

    elif request.method == "GET":
        return jsonify(msg_map.values()), 200

    return jsonify({"error": "Method Not Allowed"}), 405

if __name__ == "__main__":
    register_with_consul()
    app.run(host="0.0.0.0", port=SERVICE_PORT, threaded=True)
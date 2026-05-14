from flask import Flask, request, jsonify
import hazelcast

app = Flask(__name__)

client = hazelcast.HazelcastClient(
    cluster_name="khashcha_lab_2",
    cluster_members=["hz1:5701", "hz2:5701", "hz3:5701"]
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
    app.run(host="0.0.0.0", port=8081, threaded=True)
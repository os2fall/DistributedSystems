from flask import Flask, request, jsonify

app = Flask(__name__)

msg_store = {}

@app.route("/logging", methods=["POST", "GET"])
def data_logger():
    if request.method == "POST":
        data = request.get_json()
        
        if not data or "transaction_Id" not in data or "msg" not in data:
            return jsonify({"error": "Invalid request parameters"}), 400

        transaction_id = data["transaction_Id"]
        msg = data["msg"]

        if transaction_id in msg_store:
            return jsonify({"error": "Conflict due to duplicate transaction_Id"}), 409

        msg_store[transaction_id] = msg
        print(f"- Message Logged: {transaction_id} -> {msg}")
        return jsonify({"success": "Message Was Logged"}), 201

    elif request.method == "GET":
        return jsonify(list(msg_store.values())), 200

    return jsonify({"error": "Method Not Allowed"}), 405

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081)
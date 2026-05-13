from flask import Flask, request, jsonify

app = Flask(__name__)

balances = {}

@app.route("/transaction", methods=["POST"])
def process_transaction():
    data = request.get_json()
    
    if not data or "user_Id" not in data or "amount" not in data:
        return jsonify({"error": "Invalid request"}), 400

    user_id = data["user_Id"]
    try:
        amount = float(data["amount"])
    except ValueError:
        return jsonify({"error": "Amount must be a number"}), 400

    if user_id not in balances:
        balances[user_id] = 0.0

    balances[user_id] += amount
    
    print(f"- Transaction processed for {user_id}: {amount}. New balance: {balances[user_id]}")
    return jsonify({"user_Id": user_id, "balance": balances[user_id]}), 200

@app.route("/user/<user_id>", methods=["GET"])
def get_user_balance(user_id):
    balance = balances.get(user_id, 0.0)
    return jsonify({"user_Id": user_id, "balance": balance}), 200

@app.route("/accounts", methods=["GET"])
def get_all_balances():
    return jsonify(balances), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8082)
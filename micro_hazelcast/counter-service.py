from flask import Flask, request, jsonify
from pymongo import MongoClient

app = Flask(__name__)

client = MongoClient("mongodb://mongodb:27017/")
db = client["banking_db"]
balances_collection = db["balances"]

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

    result = balances_collection.find_one_and_update(
        {"user_Id": user_id},
        {"$inc": {"balance": amount}},
        upsert=True,
        return_document=True
    )
    
    return jsonify({"user_Id": user_id, "balance": result["balance"]}), 200

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
    app.run(host="0.0.0.0", port=8082, threaded=True)
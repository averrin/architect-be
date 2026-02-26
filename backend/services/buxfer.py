import httpx
from firebase_client import get_db
from models.buxfer import Account, Transaction, Budget
from firebase_admin import firestore

BASE_URL = "https://www.buxfer.com/api"

async def buxfer_login(client, username, password):
    resp = await client.post(f"{BASE_URL}/login", data={
        "userid": username,
        "password": password
    })
    data = resp.json()
    if data.get("response", {}).get("status") != "OK":
        raise Exception("Login failed")
    return data["response"]["token"]

async def fetch_buxfer_data(uid, username, password):
    async with httpx.AsyncClient() as client:
        try:
            token = await buxfer_login(client, username, password)

            # Accounts
            resp = await client.get(f"{BASE_URL}/accounts", params={"token": token})
            accounts_data = resp.json().get("response", {}).get("accounts", [])
            accounts = [Account(
                id=str(a["id"]),
                name=a["name"],
                bank=a.get("bank", ""),
                balance=float(a.get("balance", 0)),
                currency=a.get("currency"),
                lastSynced=str(a.get("lastSynced", "")),
                type=None
            ) for a in accounts_data]

            # Transactions (last 30 days)
            resp = await client.get(f"{BASE_URL}/transactions", params={"token": token, "days": 30})
            txs_data = resp.json().get("response", {}).get("transactions", [])
            transactions = [Transaction(
                id=str(t["id"]),
                description=t["description"],
                date=t["date"],
                type=t["type"],
                amount=float(t["amount"]),
                currency=None,
                accountId=str(t["accountId"]),
                tags=t.get("tags"),
                accountName=t.get("accountName"),
                status=t.get("status")
            ) for t in txs_data]

            # Budgets
            resp = await client.get(f"{BASE_URL}/budgets", params={"token": token})
            budgets_data = resp.json().get("response", {}).get("budgets", [])
            budgets = [Budget(
                id=str(b["id"]),
                name=b["name"],
                limit=float(b["limit"]),
                amount=float(b["amount"]),
                spent=float(b.get("balance", 0)),
                period=b.get("period", "monthly"),
                currentPeriod=None,
                balance=float(b.get("balance", 0))
            ) for b in budgets_data]

            return accounts, transactions, budgets

        except Exception as e:
            print(f"Buxfer error for {uid}: {e}")
            return None, None, None

async def update_buxfer(uid: str):
    db = get_db()
    settings_ref = db.document(f"users/{uid}/settings/current")
    settings_snap = settings_ref.get()

    if not settings_snap.exists:
        return

    user_settings = settings_snap.to_dict()
    username = user_settings.get("buxferUsername")
    password = user_settings.get("buxferPassword")

    if not username or not password:
        return

    accounts, transactions, budgets = await fetch_buxfer_data(uid, username, password)

    if accounts:
        db.document(f"users/{uid}/buxfer/accounts").set({
            "accounts": [a.model_dump() for a in accounts],
            "updatedAt": firestore.SERVER_TIMESTAMP
        })

    if transactions:
        db.document(f"users/{uid}/buxfer/transactions").set({
            "transactions": [t.model_dump() for t in transactions],
            "updatedAt": firestore.SERVER_TIMESTAMP
        })

    if budgets:
         db.document(f"users/{uid}/buxfer/budgets").set({
            "budgets": [b.model_dump() for b in budgets],
            "updatedAt": firestore.SERVER_TIMESTAMP
        })

    print(f"Buxfer updated for {uid}")

async def run_buxfer_job():
    db = get_db()
    users = db.collection("users").stream()
    for user in users:
        await update_buxfer(user.id)

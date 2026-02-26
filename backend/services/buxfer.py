import httpx
from firebase_client import get_db
from models.buxfer import Account, Transaction, Budget
from firebase_admin import firestore
from logger import logger
from utils.user_data import get_active_users
import asyncio

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
            logger.info("========")
            transactions = []
            for t in txs_data:
                try:
                    # Transfers use fromAccount/toAccount instead of accountId
                    account_id = t.get("accountId")
                    account_name = t.get("accountName")
                    if not account_id and "fromAccount" in t:
                        account_id = t["fromAccount"]["id"]
                        account_name = t["fromAccount"]["name"]
                    transactions.append(Transaction(
                        id=str(t["id"]),
                        description=t["description"],
                        date=t["date"],
                        type=t["type"],
                        amount=float(t["amount"]),
                        currency=None,
                        accountId=str(account_id) if account_id else "",
                        tags=t.get("tags"),
                        accountName=account_name,
                        status=t.get("status")
                    ))
                except Exception as e:
                    logger.error(f"Error parsing transaction for {uid}: {e} | raw: {t}")

            # Budgets
            resp = await client.get(f"{BASE_URL}/budgets", params={"token": token})
            budgets_data = resp.json().get("response", {}).get("budgets", [])
            budgets = []
            for b in budgets_data:
                try:
                    budgets.append(Budget(
                        id=str(b["id"]),
                        name=b["name"],
                        limit=float(b.get("limit", 0)),
                        amount=float(b.get("amount", 0)),
                        spent=float(b.get("spent", b.get("balance", 0))),
                        period=b.get("period", "monthly"),
                        currentPeriod=b.get("currentPeriod"),
                        balance=float(b.get("balance", 0))
                    ))
                except Exception as e:
                    logger.error(f"Error parsing budget for {uid}: {e} | raw: {b}")

            return accounts, transactions, budgets

        except Exception as e:
            logger.error(f"Buxfer error for {uid}: {e}")
            return None, None, None

async def update_buxfer(uid: str, user_settings: dict):
    logger.debug(f"Updating buxfer for {uid}")
    db = get_db()

    if not user_settings:
        logger.debug(f"No settings for user {uid}")
        return

    username = user_settings.get("buxferEmail")
    password = user_settings.get("buxferPassword")

    if not username or not password:
        logger.debug(f"No Buxfer credentials for user {uid}")
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

    logger.info(f"Buxfer updated for {uid}")

async def run_buxfer_job():
    logger.info("Starting Buxfer job")
    db = get_db()

    try:
        users_with_settings = await asyncio.to_thread(get_active_users, db)
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return

    logger.info(f"Found {len(users_with_settings)} users to process for Buxfer")

    for uid, settings_data in users_with_settings:
        await update_buxfer(uid, settings_data)

    logger.info("Buxfer job completed")

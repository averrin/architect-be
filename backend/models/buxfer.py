from pydantic import BaseModel

class Account(BaseModel):
    id: str
    name: str
    bank: str
    balance: float
    currency: str | None
    lastSynced: str | None
    type: str | None

class Transaction(BaseModel):
    id: str
    description: str
    date: str
    type: str
    amount: float
    currency: str | None
    accountId: str
    tags: str | None
    accountName: str | None
    status: str | None

class Budget(BaseModel):
    id: str
    name: str
    limit: float
    amount: float
    spent: float
    period: str
    currentPeriod: str | None
    balance: float | None

from fastapi import FastAPI
from contextlib import asynccontextmanager
from config import get_settings
from firebase_client import init_firebase
from scheduler import start_scheduler
from commands.listener import start_listener
import threading

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_firebase()
    start_scheduler()

    # Start Firestore listener
    watch = start_listener()

    yield

    # Shutdown
    if watch:
        watch.unsubscribe()

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/status")
def status():
    return {
        "status": "running",
        "version": "0.1.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)

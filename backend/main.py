from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from config import get_settings
from firebase_client import init_firebase
from scheduler import start_scheduler
from commands.listener import start_listener
from logger import logger
import threading
import asyncio

# Job imports for manual triggering
from services.weather import run_weather_job
from services.news import run_news_job
from services.buxfer import run_buxfer_job
from services.github_actions import run_github_job
from services.jules import run_jules_job
from services.forecast import run_forecast_job
from services.models_sync import run_models_sync_job

settings = get_settings()

JOBS = {
    "weather": run_weather_job,
    "news": run_news_job,
    "buxfer": run_buxfer_job,
    "github": run_github_job,
    "jules": run_jules_job,
    "forecast": run_forecast_job,
    "models_sync": run_models_sync_job
}

async def run_initial_jobs():
    logger.info("Triggering initial jobs...")
    try:
        await run_weather_job()
        await run_news_job()
        await run_buxfer_job()
        await run_github_job()
        await run_jules_job()
        await run_forecast_job()
        await run_models_sync_job()
        logger.info("Initial jobs completed.")
    except Exception as e:
        logger.error(f"Error running initial jobs: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting application...")
    init_firebase()
    start_scheduler()

    # Trigger jobs in background
    asyncio.create_task(run_initial_jobs())

    # Start Firestore listener
    watch = start_listener()

    yield

    # Shutdown
    if watch:
        watch.unsubscribe()
    logger.info("Application shutdown.")

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/status")
def status():
    return {
        "status": "running",
        "version": "0.1.0",
        "jobs": list(JOBS.keys())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)

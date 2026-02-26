from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from config import get_settings
from firebase_client import init_firebase
from scheduler import start_scheduler
from commands.listener import start_listener
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
        "version": "0.1.0",
        "jobs": list(JOBS.keys())
    }

@app.post("/trigger/{job_name}")
async def trigger_job(job_name: str):
    job_func = JOBS.get(job_name)
    if not job_func:
        raise HTTPException(status_code=404, detail="Job not found")

    # Run the job in the background or await it?
    # Awaiting it allows us to return the result/status immediately for testing.
    try:
        await job_func()
        return {"status": "success", "job": job_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import get_settings
from services.weather import run_weather_job
from services.news import run_news_job
from services.buxfer import run_buxfer_job
from services.github_actions import run_github_job
from services.jules import run_jules_job
from services.forecast import run_forecast_job
from services.models_sync import run_models_sync_job

settings = get_settings()

scheduler = AsyncIOScheduler()

def start_scheduler():
    scheduler.add_job(run_weather_job, 'interval', minutes=settings.WEATHER_INTERVAL_MINUTES)
    scheduler.add_job(run_news_job, 'interval', minutes=settings.NEWS_INTERVAL_MINUTES)
    scheduler.add_job(run_buxfer_job, 'interval', minutes=settings.BUXFER_INTERVAL_MINUTES)
    scheduler.add_job(run_github_job, 'interval', minutes=settings.GITHUB_WATCHER_INTERVAL_MINUTES)
    scheduler.add_job(run_jules_job, 'interval', minutes=settings.JULES_INTERVAL_MINUTES)

    # Daily forecast at specific hour
    scheduler.add_job(run_forecast_job, 'cron', hour=settings.FORECAST_HOUR)

    # Models sync
    scheduler.add_job(run_models_sync_job, 'interval', hours=settings.MODELS_SYNC_INTERVAL_HOURS)

    scheduler.start()

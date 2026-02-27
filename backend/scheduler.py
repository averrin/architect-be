from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import get_settings
from services.weather import run_weather_job
from services.news import run_news_job
from services.buxfer import run_buxfer_job
from services.github_actions import run_github_job
from services.jules import run_jules_job
from services.dashboard import run_dashboard_discovery_job, run_dashboard_status_job
from services.forecast import run_forecast_job
from services.models_sync import run_models_sync_job
from services.heartbeat import run_fcm_heartbeat_job
from services.reminders import run_reminders_job
from logger import logger

settings = get_settings()

scheduler = AsyncIOScheduler()

def start_scheduler():
    if settings.ENABLE_WEATHER_JOB:
        scheduler.add_job(run_weather_job, 'interval', minutes=settings.WEATHER_INTERVAL_MINUTES)
    else:
        logger.info("Weather job disabled via config")

    if settings.ENABLE_NEWS_JOB:
        scheduler.add_job(run_news_job, 'interval', minutes=settings.NEWS_INTERVAL_MINUTES)
    else:
        logger.info("News job disabled via config")

    if settings.ENABLE_BUXFER_JOB:
        scheduler.add_job(run_buxfer_job, 'interval', minutes=settings.BUXFER_INTERVAL_MINUTES)
    else:
        logger.info("Buxfer job disabled via config")

    if settings.ENABLE_GITHUB_JOB:
        scheduler.add_job(run_github_job, 'interval', seconds=settings.GITHUB_WATCHER_INTERVAL_SECONDS)
    else:
        logger.info("GitHub job disabled via config")

    if settings.ENABLE_JULES_JOB:
        scheduler.add_job(run_jules_job, 'interval', seconds=settings.JULES_INTERVAL_SECONDS)
    else:
        logger.info("Jules job disabled via config")

    if settings.ENABLE_FCM_HEARTBEAT_JOB:
        scheduler.add_job(run_fcm_heartbeat_job, 'interval', minutes=settings.FCM_HEARTBEAT_INTERVAL_MINUTES)
    else:
        logger.info("FCM Heartbeat job disabled via config")

    if settings.ENABLE_REMINDERS_JOB:
        scheduler.add_job(run_reminders_job, 'interval', seconds=settings.REMINDERS_INTERVAL_SECONDS)
    else:
        logger.info("Reminders job disabled via config")

    scheduler.add_job(run_dashboard_discovery_job, 'interval', minutes=settings.DASHBOARD_DISCOVERY_INTERVAL_MINUTES)
    scheduler.add_job(run_dashboard_status_job, 'interval', seconds=settings.DASHBOARD_STATUS_INTERVAL_SECONDS)


    # Daily forecast at specific hour
    if settings.ENABLE_FORECAST_JOB:
        scheduler.add_job(run_forecast_job, 'cron', hour=settings.FORECAST_HOUR)
    else:
        logger.info("Forecast job disabled via config")

    # Models sync
    if settings.ENABLE_MODELS_SYNC_JOB:
        scheduler.add_job(run_models_sync_job, 'interval', hours=settings.MODELS_SYNC_INTERVAL_HOURS)
    else:
        logger.info("Models sync job disabled via config")

    scheduler.start()

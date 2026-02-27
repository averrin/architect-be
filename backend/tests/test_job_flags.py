import pytest
from unittest.mock import patch, MagicMock
from backend.config import Settings
from backend.scheduler import start_scheduler
from backend.main import run_initial_jobs

@pytest.fixture
def mock_settings():
    return Settings(
        ENABLE_WEATHER_JOB=True,
        ENABLE_NEWS_JOB=True,
        ENABLE_BUXFER_JOB=True,
        ENABLE_GITHUB_JOB=True,
        ENABLE_JULES_JOB=False,
        ENABLE_FORECAST_JOB=False,
        ENABLE_MODELS_SYNC_JOB=False,
        ENABLE_FCM_HEARTBEAT_JOB=True
    )

def test_scheduler_jobs(mock_settings):
    with patch('backend.scheduler.settings', mock_settings), \
         patch('backend.scheduler.scheduler') as mock_scheduler, \
         patch('backend.scheduler.run_weather_job') as mock_weather, \
         patch('backend.scheduler.run_jules_job') as mock_jules:

        start_scheduler()

        # Verify added jobs
        # We need to check if add_job was called with specific functions
        # This is a bit tricky because we're passing functions, but we can check call counts or specific calls

        job_calls = [call.args[0] for call in mock_scheduler.add_job.call_args_list]

        assert mock_weather in job_calls
        assert mock_jules not in job_calls

        assert mock_scheduler.start.called

@pytest.mark.asyncio
async def test_initial_jobs(mock_settings):
    with patch('backend.main.settings', mock_settings), \
         patch('backend.main.run_weather_job') as mock_weather, \
         patch('backend.main.run_jules_job') as mock_jules, \
         patch('backend.main.run_news_job'), \
         patch('backend.main.run_buxfer_job'), \
         patch('backend.main.run_github_job'), \
         patch('backend.main.run_forecast_job') as mock_forecast, \
         patch('backend.main.run_models_sync_job') as mock_models_sync, \
         patch('backend.main.run_fcm_heartbeat_job'):

        await run_initial_jobs()

        assert mock_weather.called
        assert not mock_jules.called
        assert not mock_forecast.called
        assert not mock_models_sync.called

# AI Inbox Backend

Python backend for the AI Inbox mobile app.

## Setup

1. Create a virtual environment: `python -m venv venv`
2. Activate: `source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in the values.
5. Run: `uvicorn main:app --reload`

## Docker

`docker build -t ai-inbox-backend .`
`docker run -p 8000:8000 --env-file .env ai-inbox-backend`

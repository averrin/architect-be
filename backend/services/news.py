import httpx
import feedparser
from firebase_client import get_db
from models.news import Article, ArticleSource
from config import get_settings
from firebase_admin import firestore
import asyncio
from logger import logger

settings = get_settings()

async def fetch_newsapi(api_key, topics):
    if not topics:
        return []

    q = " OR ".join(topics)
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": q,
        "apiKey": api_key,
        "pageSize": 20,
        "language": "en"
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            articles = []
            for item in data.get("articles", []):
                 src = item.get("source", {})
                 articles.append(Article(
                     source=ArticleSource(id=src.get("id"), name=src.get("name", "Unknown")),
                     author=item.get("author"),
                     title=item.get("title"),
                     description=item.get("description"),
                     url=item.get("url"),
                     urlToImage=item.get("urlToImage"),
                     publishedAt=item.get("publishedAt"),
                     content=item.get("content"),
                     matchedTopic=None
                 ))
            return articles
    except Exception as e:
        logger.error(f"NewsAPI error: {e}")
        return []

def fetch_rss(feed_url):
    try:
        feed = feedparser.parse(feed_url)
        articles = []
        for entry in feed.entries:
            # Map RSS entry to Article
            articles.append(Article(
                source=ArticleSource(id=None, name=feed.feed.get("title", "RSS")),
                author=entry.get("author"),
                title=entry.get("title"),
                description=entry.get("summary"),
                url=entry.get("link"),
                urlToImage=None,
                publishedAt=entry.get("published", ""),
                content=entry.get("content", [{"value": None}])[0]["value"] if "content" in entry else None,
                matchedTopic=None
            ))
        return articles
    except Exception as e:
        logger.error(f"RSS error {feed_url}: {e}")
        return []

async def update_news(uid: str):
    logger.debug(f"Updating news for {uid}")
    db = get_db()
    settings_ref = db.document(f"users/{uid}/settings/current")
    settings_snap = settings_ref.get()

    if not settings_snap.exists:
        logger.debug(f"No settings for user {uid}")
        return

    user_settings = settings_snap.to_dict()
    news_api_key = user_settings.get("newsApiKey") or settings.DEFAULT_NEWS_API_KEY
    topics = user_settings.get("newsTopics", [])
    rss_feeds = user_settings.get("rssFeeds", [])

    all_articles = []

    if news_api_key and topics:
        news_articles = await fetch_newsapi(news_api_key, topics)
        all_articles.extend(news_articles)

    for feed in rss_feeds:
        rss_articles = await asyncio.to_thread(fetch_rss, feed)
        all_articles.extend(rss_articles)

    # Deduplicate by URL
    unique_articles = {a.url: a for a in all_articles}.values()

    # Store
    if unique_articles:
        articles_data = [a.model_dump() for a in unique_articles]
        db.document(f"users/{uid}/news/latest").set({
            "articles": articles_data,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"News updated for {uid}")
    else:
        logger.debug(f"No news found for {uid}")

async def run_news_job():
    logger.info("Starting news job")
    db = get_db()
    users = db.collection("users").stream()
    for user in users:
        await update_news(user.id)
    logger.info("News job completed")

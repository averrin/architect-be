from pydantic import BaseModel

class ArticleSource(BaseModel):
    id: str | None
    name: str

class Article(BaseModel):
    source: ArticleSource
    author: str | None
    title: str
    description: str | None
    url: str
    urlToImage: str | None
    publishedAt: str     # ISO string
    content: str | None
    matchedTopic: str | None

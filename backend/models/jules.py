from pydantic import BaseModel

class JulesSession(BaseModel):
    name: str
    id: str
    title: str
    state: str
    url: str
    createTime: str
    updateTime: str
    githubMetadata: dict | None  # owner, repo, pullRequestNumber, branch

from pydantic import BaseModel
from typing import List, Optional
from models.jules import JulesSession
from models.github import WatchedRunData

class JointSessionModel(BaseModel):
    session: JulesSession
    run: Optional[WatchedRunData] = None

class DashboardData(BaseModel):
    jointSessions: List[JointSessionModel]
    masterRuns: List[WatchedRunData]
    updatedAt: int  # timestamp ms

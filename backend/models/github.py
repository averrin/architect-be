from pydantic import BaseModel

class WatchedRunData(BaseModel):
    runId: int
    name: str
    headBranch: str
    headCommitMessage: str | None
    status: str          # queued, in_progress, completed
    conclusion: str | None
    estimatedDuration: int  # ms
    startTime: int       # timestamp ms
    lastChecked: int
    progress: float      # 0-1
    artifactUrl: str | None
    htmlUrl: str
    owner: str
    repo: str
    prMerged: bool | None = None    # PR merged state (if run is linked to a PR)
    prState: str | None = None      # PR state: open, closed, merged

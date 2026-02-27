from pydantic import BaseModel

class CoolifyApplication(BaseModel):
    id: int
    uuid: str
    name: str
    fqdn: str | None
    status: str
    gitRepository: str | None
    gitBranch: str | None
    buildPack: str | None
    projectUuid: str | None = None
    environmentUuid: str | None = None
    lastChecked: int

class CoolifyDeployment(BaseModel):
    id: int
    applicationId: str
    deploymentUuid: str
    pullRequestId: int
    forceRebuild: bool
    commit: str | None
    status: str
    isWebhook: bool
    isApi: bool
    createdAt: str
    updatedAt: str
    currentProcessId: str | None
    restartOnly: bool
    gitType: str | None
    serverId: int | None
    applicationName: str | None
    serverName: str | None
    deploymentUrl: str | None
    destinationId: str | None
    onlyThisServer: bool
    rollback: bool
    commitMessage: str | None
    lastChecked: int

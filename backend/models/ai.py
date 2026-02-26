from pydantic import BaseModel

class Action(BaseModel):
    type: str            # 'create_event'
    title: str
    description: str | None
    startTime: str | None
    durationMinutes: int | None
    recurrence: list[str] | None

class ProcessedNote(BaseModel):
    title: str
    filename: str
    tags: list[str]
    folder: str
    frontmatter: dict
    summary: str
    body: str
    icon: str | None
    fileData: dict | None
    links: list | None
    actions: list[Action] | None

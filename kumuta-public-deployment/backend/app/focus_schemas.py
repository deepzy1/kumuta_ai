from datetime import date, datetime, timezone
from typing import Literal
from pydantic import Field, model_validator
from .study_schemas import Strict, Name, Body, ID, Milestone, Revision

class GoalData(Strict):
    title: Name
    description: Body = ''
    target_date: date | None = None
    milestones: list[Milestone] = Field(default_factory=list, max_length=100)
    task_ids: list[ID] = Field(default_factory=list, max_length=200)
    status: Literal['active','completed','archived'] = 'active'
class GoalEdit(GoalData, Revision): pass

class Start(Strict):
    kind: Literal['focus','short_break','long_break','tracking'] = 'focus'
    planned_seconds: int | None = Field(default=1500, ge=1, le=86400)
    project_id: ID | None = None
    task_id: ID | None = None
    notes: Body = ''
    @model_validator(mode='after')
    def duration(self):
        if self.kind=='tracking': self.planned_seconds=None
        elif self.planned_seconds is None: raise ValueError('Set a timer duration.')
        if self.task_id is not None and self.project_id is None: raise ValueError('Task tracking requires its project.')
        return self

class EntryData(Strict):
    project_id: ID | None = None
    task_id: ID | None = None
    started_at: datetime
    ended_at: datetime
    notes: Body = ''
    @model_validator(mode='after')
    def interval(self):
        if self.started_at.tzinfo is None or self.ended_at.tzinfo is None: raise ValueError('Time entries require timezones.')
        if not self.started_at < self.ended_at: raise ValueError('End must follow start.')
        if (self.ended_at-self.started_at).total_seconds()>604800: raise ValueError('Split entries longer than a week.')
        if self.ended_at>datetime.now(timezone.utc): raise ValueError('Time entries cannot end in the future.')
        if self.task_id is not None and self.project_id is None: raise ValueError('Choose the task project.')
        return self
class EntryEdit(EntryData, Revision): pass
class Preferences(Strict):
    focus_seconds: int = Field(default=1500, ge=1, le=86400)
    short_break_seconds: int = Field(default=300, ge=1, le=86400)
    long_break_seconds: int = Field(default=900, ge=1, le=86400)
    revision: int = Field(ge=0)

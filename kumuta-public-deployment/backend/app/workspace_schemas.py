"""Bounded, explicit inputs for local workspace operations."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ColumnName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Color = Annotated[str, StringConstraints(pattern=r'^#[0-9a-fA-F]{6}$')]
Icon = Literal['folder', 'code', 'book', 'briefcase', 'star', 'home', 'target']
Priority = Literal['none', 'low', 'medium', 'high', 'urgent']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Revision(Strict):
    revision: int = Field(ge=1)


class WorkspaceCreate(Strict):
    name: Name


class WorkspaceEdit(Revision):
    name: Name


class ConfirmDelete(Revision):
    confirm_name: str = Field(min_length=1, max_length=120)


class ProjectCreate(Strict):
    name: ProjectName
    description: str = Field(default='', max_length=5000)
    icon: Icon = 'folder'
    color: Color = '#ea580c'


class ProjectEdit(Revision):
    name: ProjectName | None = None
    description: str | None = Field(default=None, max_length=5000)
    icon: Icon | None = None
    color: Color | None = None
    archived: bool | None = None

    @model_validator(mode='after')
    def reject_null_fields(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Project fields cannot be null')
        return self


class ColumnCreate(Strict):
    name: ColumnName
    is_done: bool = False
    board_revision: int = Field(ge=1)


class ColumnEdit(Strict):
    name: ColumnName | None = None
    is_done: bool | None = None
    board_revision: int = Field(ge=1)

    @model_validator(mode='after')
    def reject_null_fields(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Column fields cannot be null')
        return self


class ColumnDelete(Strict):
    board_revision: int = Field(ge=1)
    destination_id: int | None = Field(default=None, gt=0)


class Move(Strict):
    # before_id=None means append; anchors must be in the same destination list.
    before_id: int | None = Field(default=None, gt=0)
    board_revision: int = Field(ge=1)


class TaskMove(Move):
    column_id: int = Field(gt=0)


class TaskCreate(Strict):
    title: Title
    description: str = Field(default='', max_length=20000)
    column_id: int = Field(gt=0)
    parent_id: int | None = Field(default=None, gt=0)
    priority: Priority = 'none'
    due_date: date | None = None


class CheckItem(Strict):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    completed: bool = False


class TaskEdit(Revision):
    document_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, max_length=20)
    title: Title | None = None
    description: str | None = Field(default=None, max_length=20000)
    priority: Priority | None = None
    due_date: date | None = None
    checklist: list[CheckItem] | None = Field(default=None, max_length=100)

    @model_validator(mode='after')
    def reject_null_fields(self):
        for key in self.model_fields_set - {'due_date'}:
            if getattr(self, key) is None:
                raise ValueError(f'{key} cannot be null')
        return self


class NoteCreate(Strict):
    title: Title
    content: str = Field(default='', max_length=100000)
    pinned: bool = False


class NoteEdit(NoteCreate, Revision):
    pass


class ConversationCreate(Strict):
    project_id: int | None = Field(default=None, gt=0)


class ConversationProject(ConversationCreate):
    # Compare-and-swap avoids silent concurrent moves, including unlinking.
    expected_project_id: int | None = Field(gt=0)

from datetime import date, datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Name = Annotated[str, Field(min_length=1, max_length=200)]
Body = Annotated[str, Field(max_length=50000)]
ID = Annotated[int, Field(gt=0)]

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Revision(Strict):
    revision: int = Field(ge=1)

class CourseData(Strict):
    title: Name
    description: Body = ''
    objectives: Body = ''
    archived: bool = False
    origin: Literal['manual', 'ai'] = 'manual'

class ChapterData(Strict):
    course_id: ID
    title: Name

class LessonData(ChapterData):
    chapter_id: ID
    content: Body = ''
    notes: Body = ''
    completed: bool = False
    origin: Literal['manual', 'ai'] = 'manual'

class ResourceData(Strict):
    course_id: ID
    title: Name
    url: str = Field(default='', max_length=2000)
    document_id: ID | None = None
    @model_validator(mode='after')
    def location(self):
        from urllib.parse import urlparse
        if self.url and (urlparse(self.url).scheme not in ('http', 'https') or not urlparse(self.url).hostname):
            raise ValueError('Use a complete HTTP or HTTPS resource URL.')
        if not self.url and self.document_id is None:
            raise ValueError('Choose a document or enter a URL.')
        return self

class Question(Strict):
    prompt: Name
    kind: Literal['single', 'multiple', 'boolean', 'short']
    options: list[Name] = Field(default_factory=list, max_length=12)
    answers: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(min_length=1, max_length=12)
    explanation: str = Field(default='', max_length=4000)
    @model_validator(mode='after')
    def valid(self):
        if self.kind != 'short':
            if len(self.options) < 2 or len(set(self.options)) != len(self.options) or not set(self.answers) <= set(self.options):
                raise ValueError('Objective answers must reference unique options.')
            if len(set(self.answers)) != len(self.answers):
                raise ValueError('Duplicate answers.')
            if self.kind != 'multiple' and len(self.answers) != 1:
                raise ValueError('Choose exactly one correct answer.')
            if self.kind == 'boolean' and self.options != ['True', 'False']:
                raise ValueError('True/false options must be True and False.')
        return self

class QuizData(Strict):
    course_id: ID
    title: Name
    questions: list[Question] = Field(min_length=1, max_length=100)
    published: bool = False
    origin: Literal['manual', 'ai'] = 'manual'

class DeckData(Strict):
    course_id: ID
    title: Name

class CardData(Strict):
    deck_id: ID
    front: Annotated[str, Field(min_length=1, max_length=10000)]
    back: Annotated[str, Field(min_length=1, max_length=10000)]
    origin: Literal['manual', 'ai'] = 'manual'

class Milestone(Strict):
    title: Name
    target_date: date | None = None
    completed: bool = False

class PlannedSession(Strict):
    title: Name
    starts_at: datetime
    minutes: int = Field(ge=1, le=1440)
    completed: bool = False
    @field_validator('starts_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None: raise ValueError('Session time requires a timezone.')
        return value

class PlanData(Strict):
    title: Name
    description: Body = ''
    target_date: date | None = None
    target_minutes: int = Field(default=30, ge=1, le=10080)
    cadence: Literal['daily', 'weekly'] = 'daily'
    milestones: list[Milestone] = Field(default_factory=list, max_length=100)
    sessions: list[PlannedSession] = Field(default_factory=list, max_length=200)
    course_ids: list[ID] = Field(default_factory=list, max_length=100)
    task_ids: list[ID] = Field(default_factory=list, max_length=200)
    origin: Literal['manual', 'ai'] = 'manual'

class Submission(Revision):
    answers: list[list[Annotated[str, Field(max_length=2000)]]] = Field(max_length=100)

class Rating(Revision):
    rating: int = Field(ge=1, le=4)

class Move(Revision):
    before_id: ID | None = None

class Tutor(Strict):
    course_id: ID
    level: Literal['beginner', 'intermediate', 'advanced'] = 'beginner'
    depth: Literal['brief', 'balanced', 'detailed'] = 'balanced'


class CourseRequest(Strict):
    topic: Name
    objective: str = Field(default='', max_length=4000)
    difficulty: Literal['beginner', 'intermediate', 'advanced'] = 'beginner'
    source: Literal['topic', 'document', 'url'] = 'topic'
    document_id: ID | None = None
    url: str = Field(default='', max_length=2000)
    confirm_source: bool = False


class OutlineLesson(Strict):
    title: Name
    content: str = Field(default='', max_length=8000)


class OutlineChapter(Strict):
    title: Name
    lessons: list[OutlineLesson] = Field(min_length=1, max_length=4)


class CourseOutline(CourseData):
    chapters: list[OutlineChapter] = Field(min_length=1, max_length=4)

    @model_validator(mode='after')
    def bounded(self):
        if len(self.model_dump_json().encode('utf-8')) > 50000:
            raise ValueError('Keep the course outline below 50 KB.')
        return self


class SaveOutline(Strict):
    outline: CourseOutline
    document_id: ID | None = None
    url: str = Field(default='', max_length=2000)

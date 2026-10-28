"""Allowlisted, bounded declarative analysis. No expression or code fields."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Filter(Strict):
    column: str = Field(min_length=1, max_length=120)
    op: Literal['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains', 'in', 'is_missing', 'not_missing']
    value: str | int | float | bool | list[str | int | float | bool] | None = None

    @field_validator('value')
    @classmethod
    def bounded(cls, value):
        import math
        values = value if isinstance(value, list) else [value]
        if len(values) > 50 or any(isinstance(v, str) and len(v) > 4000 or isinstance(v, float) and not math.isfinite(v) for v in values):
            raise ValueError('Filter value limit exceeded.')
        return value

    @model_validator(mode='after')
    def shape(self):
        if self.op == 'in' and not isinstance(self.value, list): raise ValueError('in requires a list.')
        if self.op != 'in' and isinstance(self.value, list): raise ValueError('Only in accepts a list.')
        if self.op not in ('is_missing', 'not_missing') and self.value is None: raise ValueError('Filter needs a value.')
        return self


class Group(Strict):
    column: str = Field(min_length=1, max_length=120)
    period: Literal['day', 'week', 'month', 'quarter', 'year'] | None = None


class Metric(Strict):
    op: Literal['count', 'sum', 'average', 'min', 'max', 'distinct_count']
    column: str | None = Field(None, min_length=1, max_length=120)
    alias: str = Field(min_length=1, max_length=60, pattern=r'^[A-Za-z][A-Za-z0-9_ ]*$')

    @model_validator(mode='after')
    def needs_column(self):
        if self.op != 'count' and self.column is None: raise ValueError('Metric needs a column.')
        return self


class Derived(Strict):
    op: Literal['ratio', 'difference']
    numerator: str = Field(min_length=1, max_length=60)
    denominator: str = Field(min_length=1, max_length=60)
    alias: str = Field(min_length=1, max_length=60, pattern=r'^[A-Za-z][A-Za-z0-9_ ]*$')
    scale: Literal[1, 100] = 1


class Sort(Strict):
    column: str = Field(min_length=1, max_length=120)
    descending: bool = False


class AnalysisSpec(Strict):
    sheet: str | None = Field(None, max_length=120)
    operation: Literal['rows', 'aggregate', 'missing', 'describe'] = 'aggregate'
    columns: list[str] = Field(default_factory=list, max_length=20)
    filters: list[Filter] = Field(default_factory=list, max_length=12)
    group_by: list[Group] = Field(default_factory=list, max_length=2)
    metrics: list[Metric] = Field(default_factory=list, max_length=8)
    derived: list[Derived] = Field(default_factory=list, max_length=4)
    sort: list[Sort] = Field(default_factory=list, max_length=3)
    limit: int = Field(100, ge=1, le=500)
    offset: int = Field(0, ge=0, le=50000)
    chart: Literal['table', 'bar', 'line', 'area', 'pie', 'donut', 'kpi', 'scatter'] = 'bar'

    @field_validator('columns')
    @classmethod
    def columns_valid(cls, values):
        if any(not v or len(v) > 120 for v in values) or len(values) != len(set(values)): raise ValueError('Select unique named columns.')
        return values

    @model_validator(mode='after')
    def meaningful(self):
        if self.operation != 'aggregate' and (self.metrics or self.group_by or self.derived): raise ValueError('Metrics/grouping apply only to aggregate.')
        if self.operation == 'aggregate' and not self.metrics: raise ValueError('Choose at least one metric.')
        if self.operation == 'aggregate' and self.columns: raise ValueError('Use groups and metrics for aggregate columns.')
        aliases = [m.alias for m in self.metrics] + [d.alias for d in self.derived]
        if len(set(aliases)) != len(aliases): raise ValueError('Metric aliases must be unique.')
        names = {m.alias for m in self.metrics}
        if any(d.numerator not in names or d.denominator not in names for d in self.derived): raise ValueError('Derived metrics reference base metric aliases only.')
        if len({g.column for g in self.group_by}) != len(self.group_by): raise ValueError('Duplicate group column.')
        if set(aliases) & {g.column for g in self.group_by}: raise ValueError('Metric aliases must differ from group names.')
        return self


class Question(Strict):
    dataset_id: int = Field(gt=0)
    sheet: str | None = Field(None, max_length=120)
    question: str = Field(min_length=1, max_length=2000)
    @field_validator('question')
    @classmethod
    def not_blank(cls, value):
        if not value.strip(): raise ValueError('Ask a question.')
        return value.strip()

"""D7-7 explicit scope and restricted calculation contracts."""
from typing import Literal
from pydantic import Field
from .canvas_artifacts import Strict
from .data_schemas import AnalysisSpec


class AnalysisTask(Strict):
    source_id: int = Field(gt=0)
    spec: AnalysisSpec


class IntelligenceRequest(Strict):
    schema_version: Literal[1] = 1
    scope: Literal['selection', 'resource', 'selected', 'board']
    operation: Literal['ask', 'search', 'summarize', 'compare', 'analyze', 'visualize', 'report'] = 'ask'
    query: str = Field(default='', max_length=4000)
    full_document: bool = False
    confirm_full: bool = False
    max_results: int = Field(default=12, ge=1, le=24)
    analyses: list[AnalysisTask] = Field(default_factory=list, max_length=4)


class AnalysisPlan(Strict):
    analyses: list[AnalysisTask] = Field(min_length=1, max_length=4)

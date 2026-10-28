"""Strict generated data contracts. Executable Custom UI has no enabled route."""
import re
import json
from typing import Annotated, Literal
from pydantic import Field, field_validator, model_validator
from .canvas_artifacts import ArtifactID, Strict
from .quickui import Specification
from .canvas_selection import SelectionRequest

Coordinate = Annotated[float, Field(ge=-1e6, le=1e6)]


class Node(Strict):
    id: ArtifactID
    type: Literal['rectangle', 'diamond', 'ellipse']
    x: Coordinate
    y: Coordinate
    width: float = Field(ge=100, le=1200)
    height: float = Field(ge=50, le=1200)
    text: str = Field(max_length=200)


class Edge(Strict):
    from_: ArtifactID = Field(alias='from')
    to: ArtifactID


class NativeDiagram(Strict):
    nodes: list[Node] = Field(min_length=1, max_length=100)
    edges: list[Edge] = Field(max_length=200)

    @model_validator(mode='after')
    def references(self):
        ids = {n.id for n in self.nodes}
        if len(ids) != len(self.nodes) or any(e.from_ not in ids or e.to not in ids or e.from_ == e.to for e in self.edges):
            raise ValueError('Diagram IDs and relationships must be valid.')
        return self


class GenerationRequest(Strict):
    selection: SelectionRequest | None = None
    request_key: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    prompt: str = Field(min_length=1, max_length=4000)
    engine: Literal['auto', 'A', 'B', 'C'] = 'auto'
    mode: Literal['auto', 'chat', 'ui', 'diagram'] | None = None
    model: str | None = Field(default=None, max_length=160)
    artifact_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    conversation_id: int | None = Field(default=None, gt=0)
    output_format: Literal['auto', 'kumuta-json-v1', 'openui-lang-v1'] = 'auto'

    @field_validator('prompt')
    @classmethod
    def meaningful_prompt(cls,value):
        value=value.strip()
        if not value: raise ValueError('Write a message or describe your artifact.')
        return value


class PlacementRequest(Strict):
    expected_revision: int = Field(ge=0)
    operation: Literal['insert', 'replace', 'remove', 'selection'] = 'insert'
    version: int = Field(ge=1)
    elements: list[dict] = Field(default_factory=list, max_length=400)


class DuplicateRequest(Strict):
    request_key: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    version: int = Field(ge=1)


class RenderReport(Strict):
    status: Literal['ready', 'failed']


class CanvasPreferences(Strict):
    mode: Literal['auto', 'chat', 'ui', 'diagram']


def route_mode(prompt, mode='auto', previous=None):
    if mode != 'auto':
        return {'chat':'T', 'ui':'B', 'diagram':'A'}[mode]
    text = re.sub(r'^(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?', '', prompt.lower().strip())
    if re.search(r'\b(markdown|code block|plain text|text only)\b', text):
        return 'T'
    # Ordinary questions and code/table explanations need no artifact request.
    if re.match(r"^(explain|what\b|why\b|how\b|tell me|describe|compare|summari[sz]e|thanks|thank you|hi\b|hello\b|write (?:code|a function)|show (?:me )?(?:the )?code)", text):
        return 'T'
    if previous in ('A', 'B') and re.match(r'^(make (?:it|this)|change|update|add|remove|replace|increase|decrease|use |turn (?:it|this))\b', text):
        return previous
    # Explicit financial what-if requests benefit from editable, locally
    # calculated inputs. Ordinary arithmetic and explanations stay conversational.
    if re.search(r'\b(calculate|forecast|project|estimate|model)\b',text) and re.search(r'\b(revenue|profit|margin|growth|loan|interest|mortgage|repayment|investment|cash flow)\b',text):
        return 'B'
    if re.match(r'^(show|list|display|filter|sort)\b',text) and not re.search(r'\b(how|why|explain)\b',text) and re.search(r'\b(table|records|rows|dataset|inventory|opportunities|customers)\b',text):
        return 'B'
    # Mentioning a widget alone is not a command to create one.
    create = re.search(r'\b(create|build|draw|generate|design|make|plot|convert|recreate|turn|interactive)\b', text)
    if create or len(text.split()) <= 5:
        if re.search(r'\b(diagram|flowchart|architecture|mind ?map|excalidraw)\b', text):
            return 'A'
        if re.search(r'\b(ui|interface|dashboard|calculator|chart|graph|plot|histogram|timeline|kpi|checklist|progress|form|widget)\b', text):
            return 'B'
        if create and re.search(r'\btable\b', text):
            return 'B'
    return 'T'


def route_engine(prompt, override='auto'):
    if override != 'auto':
        return override
    text = prompt.lower()
    if re.search(r'\b(javascript|custom html|3d|simulation|webgl)\b', text):
        return 'C'
    if re.search(r'\b(chart|dashboard|calculator|table|timeline|kpi|checklist|progress|form|input|dropdown)\b', text):
        return 'B'
    return 'A'


def validate_generated(engine, answer, output_format='kumuta-json-v1'):
    if len(answer.encode('utf-8')) > 100000:
        raise ValueError('Generated specification exceeds 100000 bytes.')
    if engine == 'A':
        payload = NativeDiagram.model_validate_json(answer).model_dump(by_alias=True)
    elif engine == 'B':
        from .canvas_openui import FORMAT, LEGACY, parse_program
        if output_format not in (FORMAT, LEGACY): raise ValueError('Unknown structured format.')
        spec = Specification.model_validate(parse_program(answer)) if output_format == FORMAT else Specification.model_validate_json(answer)
        # Canvas diagrams belong to native A. No Markdown/URL/script or source
        # identifiers from a model are interpreted as authorized resources.
        if any(b.type == 'diagram' or b.type == 'markdown' and output_format != FORMAT or b.sources for b in spec.blocks):
            raise ValueError('Use native diagrams or supported structured widgets without source references.')
        payload = spec.model_dump()
    else:
        raise ValueError('Custom generation requires the sandbox security gate.')
    result = {'engine': engine, 'capabilities': ['local-state'] if engine == 'B' else [], 'payload': payload}
    if engine == 'B' and output_format == 'openui-lang-v1': result['format'] = output_format
    if len(json.dumps(result, ensure_ascii=False).encode()) > 100000:
        raise ValueError('Normalized specification exceeds 100000 bytes.')
    return result

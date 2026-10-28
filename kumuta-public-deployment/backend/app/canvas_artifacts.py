"""D7-3 manual renderer contracts; no jobs, providers or executable runtime."""
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .quickui import Specification


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)

    @field_validator('schema_version', mode='before', check_fields=False)
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError('Artifact schema version must be an integer.')
        return value


ArtifactID = Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,128}$')]


class CustomUI(Strict):
    html: str = Field(max_length=60000)
    css: str = Field(default='', max_length=20000)
    javascript: str = Field(default='', max_length=20000)


def validate_state(spec, state):
    if not isinstance(state, dict):
        raise ValueError('Interaction state must be an object.')
    for key, value in state.items():
        if not key.isascii() or not key.isdigit() or str(int(key)) != key or int(key) >= len(spec.blocks):
            raise ValueError('Unknown interaction block.')
        block = spec.blocks[int(key)]
        if block.type == 'calculator':
            from .intelligent_ui import validate_formula
            if isinstance(value, dict):
                if block.operation != 'formula' or set(value) != {'values','expressions'} or not isinstance(value['expressions'],list) or len(value['expressions'])!=len(block.formulas):
                    raise ValueError('Invalid formula interaction state.')
                for i, expression in enumerate(value['expressions']): validate_formula(expression, len(block.inputs), i)
                value=value['values']
            if not isinstance(value, list) or len(value) != len(block.inputs):
                raise ValueError('Calculator state must match inputs.')
            if any(type(v) not in (float, int) or not i.min <= v <= i.max or i.kind=='select' and v not in i.options for v, i in zip(value, block.inputs)):
                raise ValueError('Calculator state is outside input bounds.')
        elif block.type == 'checklist':
            if not isinstance(value, list) or len(value) != len(block.items) or any(type(v) is not bool for v in value):
                raise ValueError('Checklist state must match items.')
        elif block.type == 'form':
            if not isinstance(value, dict) or set(value) - {'values', 'submitted'} or not isinstance(value.get('values'), list) or len(value['values']) != len(block.fields) or type(value.get('submitted', False)) is not bool:
                raise ValueError('Form state must match fields.')
            for field, item in zip(block.fields, value['values']):
                if field.kind in ('checkbox', 'switch'):
                    if type(item) is not bool: raise ValueError('Toggle state must be boolean.')
                elif not isinstance(item, str) or len(item) > 4000:
                    raise ValueError('Form text exceeds 4000 characters.')
                elif field.kind in ('select', 'radio') and item not in field.options:
                    raise ValueError('Selection must match a declared option.')
        elif block.type == 'table':
            from .intelligent_ui import validate_table_state
            validate_table_state(block,value)
        elif block.type == 'chart':
            if not isinstance(value, list) or len(value) != len(set(map(str, value))) or any(type(v) is not int or not 0 <= v < len(block.series) for v in value):
                raise ValueError('Chart state must contain unique hidden series indexes.')
        else:
            raise ValueError('This component has no persistent interaction state.')


class WidgetLayout(Strict):
    auto_width: bool = True
    auto_height: bool = True


class StructuredArtifact(Strict):
    id: ArtifactID
    engine: Literal['B']
    schema_version: Literal[1] = 1
    anchor_id: ArtifactID
    capabilities: list[Literal['local-state']] = Field(default_factory=list, max_length=1)
    payload: Specification
    format: Literal['kumuta-json-v1', 'openui-lang-v1'] = 'kumuta-json-v1'
    layout: WidgetLayout = Field(default_factory=WidgetLayout)
    state: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def state_contract(self):
        validate_state(self.payload, self.state)
        if self.state and 'local-state' not in self.capabilities:
            raise ValueError('State requires the local-state capability.')
        return self


class CustomArtifact(Strict):
    id: ArtifactID
    engine: Literal['C']
    schema_version: Literal[1] = 1
    anchor_id: ArtifactID
    capabilities: list = Field(default_factory=list, max_length=0)
    payload: CustomUI
    state: dict = Field(default_factory=dict, max_length=0)


Artifact = Annotated[StructuredArtifact | CustomArtifact, Field(discriminator='engine')]


def validate_artifacts(artifacts, elements):
    if len(json.dumps([a.model_dump() for a in artifacts], ensure_ascii=False).encode()) > 512000:
        raise ValueError('Artifacts exceed 512000 bytes.')
    ids, anchors = set(), set()
    elements = {e['id']: e for e in elements}
    for artifact in artifacts:
        if artifact.id in ids or artifact.anchor_id in anchors:
            raise ValueError('Duplicate artifact or anchor ID.')
        ids.add(artifact.id)
        anchors.add(artifact.anchor_id)
        anchor = elements.get(artifact.anchor_id)
        if not anchor or anchor['type'] != 'rectangle' or anchor.get('frameId') or anchor.get('groupIds'):
            raise ValueError('Artifact requires an ungrouped native rectangle outside frames.')
        if anchor.get('angle', 0) != 0 or not 240 <= anchor['width'] <= 2400 or not 160 <= anchor['height'] <= 2400:
            raise ValueError('Artifact anchors require zero rotation, width 240–2400 and height 160–2400.')

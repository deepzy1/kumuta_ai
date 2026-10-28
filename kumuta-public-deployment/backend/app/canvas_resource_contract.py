"""Reference-only resource contracts. No extracted text or bytes in scenes."""
from typing import Literal
from pydantic import Field, model_validator
from .canvas_artifacts import Strict, ArtifactID


class ResourceRef(Strict):
    schema_version: Literal[1] = 1
    kind: Literal['document', 'dataset', 'image']
    source_id: int = Field(gt=0)
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    page: int | None = Field(default=None, ge=1, le=200)
    block_id: int | None = Field(default=None, gt=0)
    start: int | None = Field(default=None, ge=0, le=250000)
    end: int | None = Field(default=None, gt=0, le=250000)
    sheet: str | None = Field(default=None, min_length=1, max_length=120)
    row_start: int = Field(default=0, ge=0, le=50000)
    row_end: int = Field(default=25, ge=1, le=50000)
    columns: list[int] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def bounds(self):
        if self.row_end <= self.row_start or self.row_end-self.row_start>100:
            raise ValueError('Choose 1–100 rows.')
        if len(set(self.columns))!=len(self.columns) or any(c<0 or c>=200 for c in self.columns):
            raise ValueError('Choose distinct supported columns.')
        if (self.start is None)!=(self.end is None) or self.start is not None and (self.end<=self.start or self.block_id is None):
            raise ValueError('Passage offsets require a block and ordered bounds.')
        if self.kind!='document' and any(v is not None for v in (self.page,self.block_id,self.start,self.end)):
            raise ValueError('Page/block references belong to documents.')
        if self.kind!='dataset' and (self.sheet is not None or self.columns or self.row_start!=0 or self.row_end!=25):
            raise ValueError('Sheet/range references belong to datasets.')
        return self


class ResourceFrame(Strict):
    schema_version: Literal[1] = 1
    id: ArtifactID
    anchor_id: ArtifactID
    reference: ResourceRef


def validate_frames(frames, elements, artifacts):
    ids=set();anchors={a.anchor_id for a in artifacts}
    byid={e['id']:e for e in elements}
    for f in frames:
        e=byid.get(f.anchor_id)
        if f.id in ids or f.anchor_id in anchors or not e or e['type']!='rectangle' or e.get('angle',0)!=0 or e.get('groupIds') or e.get('frameId') or not 240<=e['width']<=2400 or not 160<=e['height']<=2400:
            raise ValueError('Resource frames require unique unrotated, ungrouped rectangle anchors, 240–2400 by 160–2400.')
        ids.add(f.id);anchors.add(f.anchor_id)

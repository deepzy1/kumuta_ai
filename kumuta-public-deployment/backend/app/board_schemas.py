"""Original bounded scene contract for native Excalidraw 0.18 elements.

No renderer code is copied or executed. Unsupported executable embeds/customData
are rejected until their later renderer contracts exist.
"""
import base64
import binascii
import json
import math
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from .canvas_artifacts import Artifact, validate_artifacts
from .canvas_resource_contract import ResourceFrame, validate_frames

MAX_SCENE_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_SCENE_BYTES + 4096
Identity = Annotated[int, Field(strict=True, gt=0)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class BoardCreate(Strict):
    workspace_id: Identity
    project_id: Identity | None = None
    title: Title = 'Untitled board'


class BoardEdit(Strict):
    title: Title | None = None
    status: Literal['active', 'archived'] | None = None

    @model_validator(mode='after')
    def supplied_fields(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Supply a title or status; null is not supported.')
        return self


class ExpectedRevision(Strict):
    expected_revision: int = Field(strict=True, ge=0)


class ConversationLink(Strict):
    conversation_id: Identity


class ResourceLink(Strict):
    document_id: Identity


def finite_tree(value, depth=0):
    if depth > 20:
        raise ValueError('Scene nesting exceeds 20 levels.')
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Scene numbers must be finite.')
    if isinstance(value, dict):
        for item in value.values(): finite_tree(item, depth + 1)
    elif isinstance(value, list):
        for item in value: finite_tree(item, depth + 1)


def safe_link(value):
    if value is None: return
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid element link.')
    parsed = urlsplit(value)
    if parsed.scheme not in ('https', 'http', 'mailto') or (parsed.scheme != 'mailto' and not parsed.hostname):
        raise ValueError('Only http, https and mailto element links are supported.')
    if parsed.username or parsed.password:
        raise ValueError('Credentials in links are unsupported.')


COMMON_FIELDS = set('id type x y width height angle strokeColor backgroundColor fillStyle strokeWidth strokeStyle roundness roughness opacity seed version versionNonce index isDeleted groupIds frameId boundElements updated link locked'.split())
TYPE_FIELDS = {
    'rectangle': set(), 'diamond': set(), 'ellipse': set(),
    'frame': {'name'}, 'magicframe': {'name'},
    'text': set('fontSize fontFamily text textAlign verticalAlign containerId originalText autoResize lineHeight'.split()),
    'line': set('points lastCommittedPoint startBinding endBinding startArrowhead endArrowhead'.split()),
    'arrow': set('points lastCommittedPoint startBinding endBinding startArrowhead endArrowhead elbowed fixedSegments startIsSpecial endIsSpecial'.split()),
    'freedraw': set('points pressures simulatePressure lastCommittedPoint'.split()),
    'image': set('fileId status scale crop'.split()),
}


def number(value, *, minimum=None):
    if type(value) not in (int, float) or abs(value) > 1e15 or not math.isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError('Invalid scene geometry or number.')


def point(value):
    if not isinstance(value, list) or len(value) != 2: raise ValueError('Invalid point.')
    for coordinate in value: number(coordinate)


def identifier(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128: raise ValueError('Invalid scene ID.')


def validate_element(e):
    if not isinstance(e, dict) or not isinstance(e.get('type'), str) or e['type'] not in TYPE_FIELDS:
        raise ValueError('Unsupported native element type.')
    if set(e) - COMMON_FIELDS - TYPE_FIELDS[e['type']]: raise ValueError('Unsupported element fields.')
    identifier(e.get('id'))
    for key in ('x', 'y', 'width', 'height'):
        number(e.get(key), minimum=0 if key in ('width', 'height') else None)
    for key in ('angle', 'strokeWidth', 'roughness', 'opacity', 'updated', 'fontSize', 'lineHeight'):
        if key in e: number(e[key], minimum=0 if key != 'angle' else None)
    if e.get('opacity', 100) > 100: raise ValueError('Invalid opacity.')
    for key in ('seed', 'version', 'versionNonce', 'fontFamily'):
        if key in e and (type(e[key]) is not int or abs(e[key]) > 2**53): raise ValueError('Invalid element integer.')
    for key in ('isDeleted', 'locked', 'autoResize', 'elbowed', 'simulatePressure'):
        if key in e and type(e[key]) is not bool: raise ValueError('Invalid element flag.')
    for key in ('startIsSpecial', 'endIsSpecial'):
        if e.get(key) is not None and type(e[key]) is not bool: raise ValueError('Invalid segment flag.')
    for key in ('strokeColor', 'backgroundColor', 'index', 'name', 'text', 'originalText'):
        if key in e and not (key in ('index','name') and e[key] is None) and (not isinstance(e[key], str) or len(e[key]) > 100000): raise ValueError('Invalid element text.')
    if 'version' in e and e['version'] < 1: raise ValueError('Invalid element version.')
    enums = {'fillStyle': {'hachure','cross-hatch','solid','zigzag'}, 'strokeStyle': {'solid','dashed','dotted'},
             'textAlign': {'left','center','right'}, 'verticalAlign': {'top','middle','bottom'}, 'status': {'pending','saved','error'}}
    for key, allowed in enums.items():
        if key in e and (not isinstance(e[key], str) or e[key] not in allowed): raise ValueError('Invalid element style/status.')
    for key in ('frameId', 'containerId', 'fileId'):
        if e.get(key) is not None: identifier(e[key])
    groups = e.get('groupIds', [])
    if not isinstance(groups, list) or len(groups) > 100: raise ValueError('Invalid groups.')
    for group in groups: identifier(group)
    if e.get('boundElements') is not None:
        if not isinstance(e['boundElements'], list) or len(e['boundElements']) > 10000: raise ValueError('Invalid bindings.')
        for b in e['boundElements']:
            if not isinstance(b, dict) or set(b) != {'id','type'} or b['type'] not in ('arrow','text'): raise ValueError('Invalid binding.')
            identifier(b['id'])
    for key in ('startBinding','endBinding'):
        b = e.get(key)
        if b is not None:
            if not isinstance(b, dict) or not {'elementId','focus','gap'} <= set(b) or set(b) - {'elementId','focus','gap','fixedPoint'}: raise ValueError('Invalid point binding.')
            identifier(b['elementId']); number(b['focus']); number(b['gap'], minimum=0)
            if 'fixedPoint' in b: point(b['fixedPoint'])
    if e.get('roundness') is not None:
        r = e['roundness']
        if not isinstance(r, dict) or set(r) - {'type','value'} or type(r.get('type')) is not int or r['type'] not in (1,2,3): raise ValueError('Invalid roundness.')
        if 'value' in r: number(r['value'], minimum=0)
    if e['type'] in ('line','arrow','freedraw'):
        if not isinstance(e.get('points'), list) or not 1 <= len(e['points']) <= 20000: raise ValueError('Invalid points.')
        for p in e['points']: point(p)
    if e.get('lastCommittedPoint') is not None: point(e['lastCommittedPoint'])
    if e.get('fixedSegments') is not None:
        if not isinstance(e['fixedSegments'], list) or len(e['fixedSegments']) > 20000: raise ValueError('Invalid fixed segments.')
        for s in e['fixedSegments']:
            if not isinstance(s, dict) or set(s) != {'start','end','index'} or type(s['index']) is not int: raise ValueError('Invalid fixed segment.')
            point(s['start']); point(s['end'])
    if 'pressures' in e:
        if not isinstance(e['pressures'], list) or len(e['pressures']) > 20000: raise ValueError('Invalid pressures.')
        for p in e['pressures']:
            number(p, minimum=0)
            if p > 1: raise ValueError('Invalid pressure.')
    if e['type'] == 'text' and not isinstance(e.get('text'), str): raise ValueError('Text element requires text.')
    arrowheads = {'arrow','bar','dot','circle','circle_outline','triangle','triangle_outline','diamond','diamond_outline','crowfoot_one','crowfoot_many','crowfoot_one_or_many'}
    for key in ('startArrowhead','endArrowhead'):
        if e.get(key) is not None and (not isinstance(e[key], str) or e[key] not in arrowheads): raise ValueError('Invalid arrowhead.')
    if e['type'] == 'image':
        if 'scale' not in e: raise ValueError('Image requires scale.')
        point(e['scale'])
        if any(v not in (-1,1) for v in e['scale']): raise ValueError('Invalid image scale.')
        if e.get('crop') is not None:
            c = e['crop']
            if not isinstance(c, dict) or set(c) != {'x','y','width','height','naturalWidth','naturalHeight'}: raise ValueError('Invalid crop.')
            for v in c.values(): number(v, minimum=0)
    safe_link(e.get('link'))


class Scene(Strict):
    type: Literal['excalidraw'] = 'excalidraw'
    version: Literal[2] = 2
    source: Annotated[str, StringConstraints(max_length=2048)] | None = None
    elements: list[dict] = Field(max_length=10000)
    appState: dict = Field(default_factory=dict)
    files: dict = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)
    resources: list[ResourceFrame] = Field(default_factory=list, max_length=100)

    @field_validator('version', mode='before')
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int: raise ValueError('Scene version must be an integer.')
        return value

    @model_validator(mode='before')
    @classmethod
    def bounded(cls, value):
        finite_tree(value)
        try: size = len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'))
        except (TypeError, UnicodeError): raise ValueError('Scene must be valid UTF-8 JSON.') from None
        if size > MAX_SCENE_BYTES: raise HTTPException(413, 'Scene exceeds 8 MiB.')
        return value

    @field_validator('appState')
    @classmethod
    def persistent_state(cls, value):
        # Persist drawing settings only, never selection, collaborators, tools,
        # menus, pointer state, editor caches, or browser dimensions.
        result = {k: v for k, v in value.items() if k in ('viewBackgroundColor','gridSize','gridStep','gridModeEnabled')}
        if 'viewBackgroundColor' in result and (not isinstance(result['viewBackgroundColor'], str) or len(result['viewBackgroundColor']) > 100): raise ValueError('Invalid background.')
        for key in ('gridSize','gridStep'):
            if result.get(key) is not None: number(result[key], minimum=0)
        if 'gridModeEnabled' in result and type(result['gridModeEnabled']) is not bool: raise ValueError('Invalid grid mode.')
        return result

    @model_validator(mode='after')
    def validate_scene(self):
        ids = set()
        if len(self.files) > 100: raise ValueError('Use at most 100 image files.')
        for e in self.elements:
            validate_element(e)
            if e['id'] in ids: raise ValueError('Duplicate element ID.')
            ids.add(e['id'])
        for key, f in self.files.items():
            identifier(key)
            if not isinstance(f, dict) or set(f) - {'id','mimeType','dataURL','created','lastRetrieved','version'} or f.get('id') != key: raise ValueError('Invalid file record.')
            mime = f.get('mimeType')
            if mime not in ('image/png','image/jpeg','image/webp','image/gif'): raise ValueError('Only PNG, JPEG, WebP and GIF scene files are supported.')
            url = f.get('dataURL')
            prefix = f'data:{mime};base64,'
            if not isinstance(url, str) or not url.startswith(prefix): raise ValueError('Files require inline image data; remote/path references are unsupported.')
            try: raw = base64.b64decode(url[len(prefix):], validate=True)
            except (ValueError, binascii.Error): raise ValueError('Invalid image encoding.') from None
            signatures = {'image/png': raw.startswith(b'\x89PNG\r\n\x1a\n'), 'image/jpeg': raw.startswith(b'\xff\xd8\xff'), 'image/webp': raw.startswith(b'RIFF') and raw[8:12] == b'WEBP', 'image/gif': raw[:6] in (b'GIF87a',b'GIF89a')}
            if not signatures[mime] or len(raw) > 5 * 1024 * 1024: raise ValueError('Invalid image signature or image exceeds 5 MiB.')
            for field in ('created','lastRetrieved','version'):
                if field in f: number(f[field], minimum=0)
            f.pop('lastRetrieved', None)
        for e in self.elements:
            if e.get('fileId') is not None and e['fileId'] not in self.files: raise ValueError('Missing image file reference.')
            refs = [e.get('frameId'), e.get('containerId')]
            refs += [b['id'] for b in e.get('boundElements') or []]
            refs += [e[k]['elementId'] for k in ('startBinding','endBinding') if e.get(k)]
            if any(ref is not None and ref not in ids for ref in refs): raise ValueError('Dangling element reference.')
        validate_artifacts(self.artifacts, self.elements)
        validate_frames(self.resources, self.elements, self.artifacts)
        return self


class SceneSave(ExpectedRevision):
    schema_version: Literal[1] = 1
    scene: Scene

    @field_validator('schema_version', mode='before')
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int: raise ValueError('Schema version must be an integer.')
        return value

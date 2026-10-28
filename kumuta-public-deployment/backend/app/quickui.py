"""Bounded, content-only QuickUI v1 contract. No generated HTML, CSS or code execution."""
import json
import math
import re
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

Label = Annotated[str, Field(max_length=300)]
Text = Annotated[str, Field(max_length=12000)]
Number = Annotated[float, Field(ge=-1e12, le=1e12)]

class Block(Strict):
    title: Label = ''
    span: Literal[1, 2] = 1
    sources: list[Annotated[int, Field(ge=1, le=100)]] = Field(default_factory=list, max_length=20)

class Markdown(Block):
    type: Literal['markdown']
    text: Text

class ColumnFormat(Strict):
    kind: Literal['text','number','currency','percent','date','status'] = 'text'
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')] = 'USD'
    decimals: int = Field(default=2, ge=0, le=8)

class Table(Block):
    type: Literal['table']
    columns: list[Label] = Field(min_length=1, max_length=12)
    rows: list[list[Label | Number]] = Field(max_length=1000)
    formats: list[ColumnFormat] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def rectangular(self):
        if self.formats and len(self.formats) != len(self.columns):
            raise ValueError('Column formats must match columns')
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError('Table rows must match columns')
        return self

class Card(Strict):
    label: Label
    value: Label | Number = ''
    detail: Label = ''

class Cards(Block):
    type: Literal['cards']
    items: list[Card] = Field(min_length=1, max_length=20)

class Series(Strict):
    name: Label
    values: list[Number] = Field(min_length=1, max_length=100)

class Chart(Block):
    type: Literal['chart']
    kind: Literal['bar', 'line', 'area', 'stacked', 'scatter', 'pie', 'donut'] = 'bar'
    labels: list[Label] = Field(min_length=1, max_length=100)
    series: list[Series] = Field(min_length=1, max_length=8)
    unit: Label = ''
    colors: list[Annotated[str, Field(pattern=r'^#[0-9a-fA-F]{6}$')]] = Field(default_factory=list, max_length=8)

    @model_validator(mode='after')
    def aligned(self):
        if any(len(s.values) != len(self.labels) for s in self.series):
            raise ValueError('Chart series must match labels')
        if self.kind in ('pie','donut') and (len(self.series) != 1 or any(v < 0 for v in self.series[0].values) or sum(self.series[0].values) <= 0):
            raise ValueError('Pie/donut require one positive-total nonnegative series.')
        if self.kind == 'scatter':
            try: xs = [float(v) for v in self.labels]
            except ValueError: raise ValueError('Scatter labels must be numeric x coordinates.') from None
            if any(not math.isfinite(v) or abs(v)>1e12 for v in xs): raise ValueError('Invalid scatter coordinates.')
        return self

class Event(Strict):
    when: Label
    title: Label
    detail: Label = ''

class Timeline(Block):
    type: Literal['timeline']
    items: list[Event] = Field(min_length=1, max_length=40)

class Diagram(Block):
    type: Literal['diagram']
    syntax: Literal['sequence', 'mermaid'] = 'sequence'
    text: Annotated[str, Field(min_length=1, max_length=10000)]

    @field_validator('text')
    @classmethod
    def no_directives(cls, value):
        if re.search(r'%%\{|^\s*---|\b(click|callback|javascript|style|classDef|linkStyle)\b|<\s*[A-Za-z!/]', value, re.I | re.M):
            raise ValueError('Diagram contains unsafe directives')
        return value

class Formula(Strict):
    label: Label
    expression: Annotated[str, Field(min_length=1, max_length=240)]
    unit: Label = ''

class Input(Strict):
    label: Label
    kind: Literal['number','currency','percent','select'] = 'number'
    options: list[Number] = Field(default_factory=list, max_length=30)
    value: Number
    min: Number = 0
    max: Number = 100
    step: Annotated[float, Field(gt=0, le=1e12)] = 1

    @model_validator(mode='after')
    def bounded(self):
        if not self.min <= self.value <= self.max or self.min >= self.max:
            raise ValueError('Input needs min <= value <= max and min < max')
        if self.kind == 'select' and (not self.options or self.value not in self.options or len(set(self.options))!=len(self.options) or any(not self.min<=v<=self.max for v in self.options)):
            raise ValueError('Dropdown values must match unique bounded options.')
        return self

class Calculator(Block):
    type: Literal['calculator']
    operation: Literal['sum', 'product', 'compound', 'loan', 'formula']
    inputs: list[Input] = Field(min_length=1, max_length=6)
    unit: Label = ''
    formulas: list[Formula] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def valid_operation(self):
        from .intelligent_ui import validate_formula
        if (self.operation == 'formula') != bool(self.formulas):
            raise ValueError('Formula calculators require declared formulas, fixed calculators omit them.')
        for i, formula in enumerate(self.formulas):
            validate_formula(formula.expression, len(self.inputs), i)
        if self.operation in ('compound', 'loan') and len(self.inputs) != 3:
            raise ValueError('compound/loan need principal, annual rate percent, years')
        if self.operation in ('compound', 'loan') and any(i.min < 0 for i in self.inputs):
            raise ValueError('Financial inputs must be nonnegative')
        return self

class ProgressItem(Strict):
    label: Label
    value: Annotated[float, Field(ge=0, le=1e12)]
    max: Annotated[float, Field(gt=0, le=1e12)] = 100

class Progress(Block):
    type: Literal['progress']
    items: list[ProgressItem] = Field(min_length=1, max_length=20)

class CheckItem(Strict):
    text: Label
    checked: bool = False

class Checklist(Block):
    type: Literal['checklist']
    items: list[CheckItem] = Field(min_length=1, max_length=50)

class FormField(Strict):
    label: Label
    kind: Literal['text', 'textarea', 'select', 'checkbox', 'radio', 'switch'] = 'text'
    options: list[Label] = Field(default_factory=list, max_length=30)
    value: str | bool = ''

    @model_validator(mode='after')
    def valid_value(self):
        if self.kind in ('checkbox', 'switch'):
            if type(self.value) is not bool:
                raise ValueError('Toggle values must be boolean.')
        elif not isinstance(self.value, str) or len(self.value) > 4000:
            raise ValueError('Form text exceeds 4000 characters.')
        if self.kind in ('select', 'radio') and (not self.options or len(set(self.options)) != len(self.options) or self.value not in self.options):
            raise ValueError('Selection must match a unique declared option.')
        return self


class Form(Block):
    type: Literal['form']
    fields: list[FormField] = Field(min_length=1, max_length=30)
    submit_label: Label = 'Submit'


Component = Annotated[Markdown | Table | Cards | Chart | Timeline | Diagram | Calculator | Progress | Checklist | Form, Field(discriminator='type')]

class Specification(Strict):
    version: Literal[1] = 1
    title: Label = ''
    blocks: list[Component] = Field(min_length=1, max_length=16)

class Color(Strict):
    mode: Literal['system', 'solid', 'gradient', 'custom'] = 'system'
    colors: list[str] = Field(default_factory=lambda: ['#c45d32'], min_length=1, max_length=6)
    angle: int = Field(default=120, ge=0, le=360)
    stops: list[Annotated[int, Field(ge=0, le=100)]] = Field(default_factory=lambda: [0], min_length=1, max_length=6)

    @field_validator('colors')
    @classmethod
    def hex_colors(cls, values):
        if any(not re.fullmatch(r'#[0-9a-fA-F]{6}', x) for x in values):
            raise ValueError('Colors must be six-digit HEX values')
        return [x.lower() for x in values]

    @model_validator(mode='after')
    def valid_stops(self):
        if len(self.colors) != len(self.stops) or sorted(self.stops) != self.stops:
            raise ValueError('Provide sorted stops for every color')
        if self.mode == 'gradient' and len(self.colors) < 2:
            raise ValueError('A gradient needs at least two colors')
        if self.mode != 'gradient' and len(self.colors) != 1:
            raise ValueError('Solid colors need one color and stop')
        return self

class Appearance(Strict):
    color: Color = Field(default_factory=Color)
    style: Literal['minimal', 'modern', 'professional', 'playful', 'custom'] = 'modern'
    appearance: Literal['light', 'dark', 'system'] = 'system'
    density: Literal['compact', 'comfortable', 'spacious'] = 'comfortable'
    radius: int = Field(default=12, ge=0, le=28)

class CanvasAppearance(Strict):
    inherit: bool = True
    accent: str = '#c45d32'
    widget_color: Color = Field(default_factory=Color)
    chart_colors: list[str] = Field(default_factory=lambda: ['#2563eb','#ea580c','#059669','#7c3aed','#db2777','#0891b2','#b45309','#475569'], min_length=1, max_length=8)
    appearance: Literal['light', 'dark', 'system'] = 'system'
    density: Literal['compact', 'comfortable', 'spacious'] = 'comfortable'

    @field_validator('accent')
    @classmethod
    def valid_accent(cls, value):
        return Color.hex_colors([value])[0]

    @field_validator('chart_colors')
    @classmethod
    def valid_chart_colors(cls, values):
        return Color.hex_colors(values)

class Preferences(Appearance):
    behavior: Literal['automatic', 'prefer', 'disabled'] = 'automatic'
    canvas: CanvasAppearance = Field(default_factory=CanvasAppearance)

# Shared compact content contract; server-side Specification remains authoritative.
BLOCK_PROMPT = '''Blocks have type,title?,span?(1|2),sources?([source numbers]); supported types/fields:
markdown: text; table: columns(string[]),rows(cell[][]); cards: items[{label,value,detail?}]; chart: kind(bar|line|area|stacked|scatter|pie|donut),labels(string[]),series[{name,values(number[])}],unit?; timeline: items[{when,title,detail?}]; diagram: syntax(sequence|mermaid),text (sequence uses "A -> B: message"; mermaid has no directives, styles or HTML); calculator: operation(sum|product|compound|loan|formula),inputs[{label,value,min,max,step}],unit? (compound/loan inputs: principal,annual rate percent,years); progress: items[{label,value,max}]; checklist: items[{text,checked?}]. Formula calculators also require formulas:[{label,expression,unit?}] with up to 12 arithmetic results using x1..x6 input references and earlier r1..r12 results, + - * / ^ and parentheses only. Never execute code. Tables optionally declare formats:[{kind:text|number|currency|percent|date|status,currency?:ISO code,decimals?:0..8}] matching columns. Chart colors?:HEX[] overrides, scatter labels are numeric x coordinates; pie/donut require one nonnegative series. Inputs kind?:number|currency|percent|select and options?:number[]. At most 16 blocks, 100 chart points, 8 series, 1000 bounded table result rows.'''
FORM_BLOCK_PROMPT = 'Canvas also supports form: fields[{label,kind(text|textarea|select|checkbox|radio|switch),options?(string[]),value(string|boolean)}],submit_label?. Select/radio values must match a declared option; checkbox/switch values must be boolean. Submission saves locally only. At most 30 fields and 4000 characters per field.'
# One optional compact fence in the same streamed completion; no second model call.
PROMPT = ('\nQuickUI: for comparisons, plans, charts, diagrams or interactive explanations, answer with a short Markdown introduction then ONE ```quickui fenced JSON object {"version":1,"title":"...","blocks":[...]}. Simple questions: Markdown only. Never generate HTML/CSS/JS or appearance settings. '
          + BLOCK_PROMPT + ' Use only supplied/sourced numbers; identify examples. Cite grounded sources in Markdown and block sources. No other fields. Layout and colors are rendered locally.\n')
FENCE = re.compile(r'^```quickui\s*\n(.*?)^```\s*$', re.M | re.S)

def fallback(spec):
    parts = [f'## {spec["title"]}' if spec['title'] else '']
    for b in spec['blocks']:
        if b.get('title'):
            parts.append('### ' + b['title'])
        kind = b['type']
        if kind == 'markdown':
            parts.append(b['text'])
        elif kind == 'table':
            def cell(v):
                return str(v).replace('|', '\\|').replace('\n', ' ')
            parts.append('\n'.join(['| ' + ' | '.join(map(cell, b['columns'])) + ' |', '| ' + ' | '.join(['---'] * len(b['columns'])) + ' |'] + ['| ' + ' | '.join(map(cell, row)) + ' |' for row in b['rows']]))
        elif kind == 'chart':
            parts.extend(f'- {s["name"]}: ' + ', '.join(f'{label}: {value:g} {b["unit"]}' for label, value in zip(b['labels'], s['values'])) for s in b['series'])
        elif kind == 'diagram':
            parts.append('```text\n' + b['text'] + '\n```')
        elif kind == 'form':
            parts.extend(f'- {field["label"]}: {field["value"]}' for field in b['fields'])
        elif kind == 'calculator':
            parts.append(f'Calculation: {b["operation"]}. ' + '; '.join(f'{i["label"]}: {i["value"]:g}' for i in b['inputs']))
            if b['operation']=='formula':
                from .intelligent_ui import calculator_results
                parts.extend(f"- {r['label']}: {r['value'] if r['value'] is not None else r['error']} {r.get('unit','')} ({r['expression']})" for r in calculator_results(b,None))
        else:
            for item in b['items']:
                if kind == 'checklist':
                    parts.append(f'- [{"x" if item["checked"] else " "}] {item["text"]}')
                elif kind == 'timeline':
                    parts.append(f'- **{item["when"]} — {item["title"]}** {item["detail"]}')
                elif kind == 'progress':
                    parts.append(f'- {item["label"]}: {item["value"]:g} / {item["max"]:g}')
                else:
                    parts.append(f'- **{item["label"]}: {item["value"]}** {item["detail"]}')
    return '\n\n'.join(filter(None, parts))

def extract(answer):
    match = FENCE.search(answer)
    if not match:
        return answer, None, None
    try:
        if len(match[1]) > 100000:
            raise ValueError('Specification too large')
        spec = Specification.model_validate_json(match[1]).model_dump()
    except (ValidationError, ValueError, RecursionError):
        return answer + '\n\n> QuickUI could not be validated. The original response is shown above.', None, 'invalid_specification'
    markdown = (answer[:match.start()] + answer[match.end():]).strip()
    return (markdown + '\n\n' + fallback(spec)).strip(), spec, None

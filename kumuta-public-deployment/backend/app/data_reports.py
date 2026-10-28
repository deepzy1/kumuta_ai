"""Report configuration validation, refresh and exports share one analysis engine."""
import csv
import io
import json
import time
from fastapi import HTTPException
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select
from . import workspaces, datasets
from .data_analysis_api import result
from .data_schemas import AnalysisSpec, Strict
from .report_models import DataReport
from .database import now


class Widget(Strict):
    key: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')
    title: str = Field(min_length=1, max_length=120)
    dataset_id: int = Field(gt=0)
    source_sha256: str | None = Field(None, pattern=r'^[a-f0-9]{64}$')
    spec: AnalysisSpec
    @field_validator('title')
    @classmethod
    def clean(cls, value):
        if not value.strip(): raise ValueError('Widget needs a title.')
        return value.strip()


class ReportData(Strict):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field('', max_length=1000)
    widgets: list[Widget] = Field(default_factory=list, max_length=8)
    @field_validator('name')
    @classmethod
    def clean(cls, value):
        if not value.strip(): raise ValueError('Report needs a name.')
        return value.strip()
    @model_validator(mode='after')
    def bounded(self):
        if len({w.key for w in self.widgets}) != len(self.widgets): raise ValueError('Widget keys must be unique.')
        if len({(w.dataset_id, w.spec.sheet) for w in self.widgets}) > 4: raise ValueError('Use at most four dataset/worksheet combinations per report.')
        if len(self.model_dump_json()) > 64000: raise ValueError('Report configuration exceeds 64 KB.')
        return self


class ReportEdit(ReportData):
    revision: int = Field(ge=1)


def owned(pid, rid, user, db, writable=False):
    workspaces.owned_project(pid, user, db, writable=writable)
    row = db.scalar(select(DataReport).where(DataReport.id == rid, DataReport.owner_id == user.id, DataReport.project_id == pid))
    if row is None: raise HTTPException(404, 'Report not found in this project')
    return row


def view(row):
    return {**workspaces.fields(row, 'id project_id name description revision created_at updated_at'),
            'widgets': json.loads(row.configuration), 'ai_calls': 0}


def validate_widgets(pid, widgets, user, db):
    # Validate names/types/calculations before saving. This is local and explicit.
    cache = {}
    validated = []
    for widget in widgets:
        row = datasets.owned(pid, widget.dataset_id, user, db)
        if widget.source_sha256 is not None and widget.source_sha256 != row.sha256:
            raise HTTPException(409, 'Report source has changed. Select the dataset again.')
        key = (row.id, widget.spec.sheet)
        if key not in cache: cache[key] = datasets.sheet_data(row, widget.spec.sheet, db)
        result(row, cache[key], widget.spec)
        validated.append({**widget.model_dump(), 'source_sha256': row.sha256})
    return validated


def run(pid, report, user, db, export_all=False):
    started, cache, widgets = time.monotonic(), {}, []
    for raw in json.loads(report.configuration):
        if time.monotonic()-started > 30: raise HTTPException(422, 'Report exceeded its refresh budget. Reduce the number of widgets.')
        widget = Widget.model_validate(raw)
        try: row = datasets.owned(pid, widget.dataset_id, user, db)
        except HTTPException as exc:
            if exc.status_code == 404: raise HTTPException(409, f'Dataset unavailable for widget “{widget.title}”. Edit or remove the widget.') from None
            raise
        if row.sha256 != widget.source_sha256: raise HTTPException(409, 'Report source changed. Edit the report before refreshing.')
        key = (row.id, widget.spec.sheet)
        if key not in cache: cache[key] = datasets.sheet_data(row, widget.spec.sheet, db)
        computed = result(row, cache[key], widget.spec, export_all=export_all)
        widgets.append({'key': widget.key, 'title': widget.title, 'result': computed})
    return {'report': view(report), 'widgets': widgets, 'generated_at': now(), 'ai_calls': 0}


def safe_csv_cell(value):
    if value is None: return ''
    text = str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text


def export_csv(output):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    def write(values): writer.writerow([safe_csv_cell(v) for v in values])
    write(['Kumuta AI report', output['report']['name'], 'Refreshed', output['generated_at']])
    for widget in output['widgets']:
        data = widget['result']
        write([]); write(['Widget', widget['title'], 'Dataset', data['dataset']['name'], 'Worksheet', data['sheet']])
        write(['Source SHA-256', data['dataset']['sha256']])
        write(['Analysis specification', json.dumps(data['spec'], ensure_ascii=False)])
        write(data['columns'])
        for row in data['rows']: write(row)
        for warning in data['warnings']: write(['Warning', warning])
        if stream.tell() > 16 * 1024 * 1024: raise HTTPException(413, 'Export exceeds 16 MB. Add report filters.')
    return stream.getvalue()

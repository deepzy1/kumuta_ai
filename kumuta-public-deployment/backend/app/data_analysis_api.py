"""Deterministic requests and explicit accounted natural-language interpretation."""
from fastapi import Depends
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from .database import User
from . import datasets, data_engine, data_ai
from .data_schemas import AnalysisSpec, Question


def result(row, data, spec, *, export_all=False):
    output = data_engine.execute(data, spec, export_all=export_all)
    output['dataset'] = {k: getattr(row, k) for k in ('id', 'name', 'project_id', 'sha256', 'revision')}
    output['sheet'] = data['name']
    output['answer'] = f"Computed {output['total_results']} result rows from {output['matched_rows']} matching rows in {row.name} / {data['name']}."
    if spec.operation == 'aggregate' and len(output['rows']) == 1:
        summary = '; '.join(f'{name}: {value if value is not None else "unavailable"}' for name, value in zip(output['columns'], output['rows'][0]))
        output['answer'] = summary[:1000] + f". Calculated from {output['matched_rows']} matching rows in {row.name} / {data['name']}."
    return output


def register(app, user_dependency, db_dependency):
    @app.post('/projects/{pid}/data/datasets/{did}/analyze')
    def analyze(pid: int, did: int, spec: AnalysisSpec, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        row = datasets.owned(pid, did, user, db)
        data = datasets.sheet_data(row, spec.sheet, db)
        return result(row, data, spec)

    async def interpreted(pid, question, user, db, review=False):
        row = datasets.owned(pid, question.dataset_id, user, db)
        data = await run_in_threadpool(datasets.sheet_data, row, question.sheet, db)
        # Close authentication/read transaction before model discovery/generation.
        db.commit()
        spec, model = await data_ai.interpret(question, data, user)
        # Reauthorize after the provider call: project/dataset could have been deleted.
        db.expire_all()
        row = datasets.owned(pid, question.dataset_id, user, db)
        output = await run_in_threadpool(result, row, data, spec)
        if review:
            return {'spec': output['spec'], 'dataset': output['dataset'], 'sheet': output['sheet'],
                    'model': model, 'ai_calls': 1, 'gemini_used': True,
                    'explanation': 'Validated against actual columns, types and permitted operations. Review, then run locally.'}
        output.update(ai_calls=1, gemini_used=True, model=model)
        return output

    @app.post('/projects/{pid}/data/interpret')
    async def interpret(pid: int, question: Question, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        return await interpreted(pid, question, user, db, review=True)

    @app.post('/projects/{pid}/data/ask')
    async def ask(pid: int, question: Question, user: User = Depends(user_dependency), db: Session = Depends(db_dependency)):
        return await interpreted(pid, question, user, db)

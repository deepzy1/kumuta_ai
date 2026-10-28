"""Deterministic Python analysis over bounded source values, without AI or SQL."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
import time
from fastapi import HTTPException
from .data_schemas import AnalysisSpec

NUMERIC = {'integer', 'decimal'}


def fail(message):
    raise HTTPException(422, message)


def numeric(value):
    if value is None: return None
    try:
        number = Decimal(str(value).strip())
        if number.is_finite() and abs(number) <= Decimal('1e100'): return number
    except InvalidOperation: pass
    fail('Invalid numeric filter value.')


def instant(value, kind):
    try:
        if kind == 'date': return date.fromisoformat(str(value).strip()).isoformat()
        dt = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
        # Aware values normalize to UTC. Naive values explicitly use UTC wall time.
        return dt.replace(tzinfo=timezone.utc).isoformat() if dt.tzinfo is None else dt.astimezone(timezone.utc).isoformat()
    except ValueError: fail('Invalid ISO date/datetime filter value.')


def typed(value, kind):
    if value is None: return None
    if kind in NUMERIC: return numeric(value)
    if kind == 'boolean':
        if str(value).strip().lower() not in ('true', 'false'): fail('Boolean filters use true or false.')
        return str(value).strip().lower() == 'true'
    if kind in ('date', 'datetime'): return instant(value, kind)
    return str(value)


def execute(data, spec: AnalysisSpec, *, export_all=False):
    started = time.monotonic()
    schema = {c['name']: c for c in data['columns']}
    positions = {name: i for i, name in enumerate(schema)}
    def column(name):
        if name not in schema: fail(f'Unknown column: {name}')
        return schema[name]
    for name in spec.columns: column(name)
    for group in spec.group_by:
        if group.period and column(group.column)['type'] not in ('date', 'datetime'): fail('Date grouping requires a date/datetime column.')
        column(group.column)
    for metric in spec.metrics:
        if metric.column:
            kind = column(metric.column)['type']
            if metric.op in ('sum', 'average', 'min', 'max') and kind not in NUMERIC: fail('Numeric aggregations require an entirely numeric column; mixed/identifier columns remain strings.')
    compiled = []
    for f in spec.filters:
        kind = column(f.column)['type']
        if f.op == 'contains' and kind not in ('string', 'null'): fail('contains requires a text column.')
        expected = [typed(v, kind) for v in f.value] if f.op == 'in' else typed(f.value, kind)
        compiled.append((f, kind, expected))
    rows = []
    for index, row in enumerate(data['rows']):
        if index % 100 == 0 and time.monotonic() - started > 5: fail('Analysis exceeded five seconds; simplify filters.')
        keep = True
        for f, kind, expected in compiled:
            value = typed(row[positions[f.column]], kind)
            if f.op == 'is_missing': match = value is None
            elif f.op == 'not_missing': match = value is not None
            elif value is None: match = False  # null never satisfies ordinary comparisons
            elif f.op == 'eq': match = value == expected
            elif f.op == 'ne': match = value != expected
            elif f.op == 'in': match = value in expected
            elif f.op == 'contains': match = str(expected).casefold() in str(value).casefold()
            elif f.op == 'gt': match = value > expected
            elif f.op == 'gte': match = value >= expected
            elif f.op == 'lt': match = value < expected
            else: match = value <= expected
            if not match: keep = False; break
        if keep: rows.append(row)
    warnings = list(data['warnings'])
    excluded = {}
    with localcontext() as context:
        context.prec = 120
        if spec.operation == 'rows':
            names = spec.columns or list(schema)[:20]
            if not spec.columns and len(schema) > 20: warnings.append('Row view shows the first 20 columns. Select columns to change this.')
            kinds = {n: schema[n]['type'] for n in names}
            result = [[r[positions[n]] for n in names] for r in rows]
        elif spec.operation in ('missing', 'describe'):
            names = ['column', 'type', 'count', 'missing', 'distinct', 'min', 'max', 'sum', 'average', 'median', 'stddev_population'] if spec.operation == 'describe' else ['column', 'missing', 'present']
            kinds = {n: 'decimal' if n not in ('column', 'type') else 'string' for n in names}
            result = []
            for name in spec.columns or list(schema):
                values = [r[positions[name]] for r in rows if r[positions[name]] is not None]
                missing = len(rows) - len(values)
                if spec.operation == 'missing': result.append([name, missing, len(values)]); continue
                stats = [None] * 7
                if schema[name]['type'] in NUMERIC and values:
                    numbers = sorted(numeric(v) for v in values); total = sum(numbers, Decimal(0)); mean = total / len(numbers)
                    mid = len(numbers)//2; median = numbers[mid] if len(numbers)%2 else (numbers[mid-1]+numbers[mid])/2
                    stddev = (sum((v-mean)**2 for v in numbers)/len(numbers)).sqrt()
                    stats = [str(min(numbers)), str(max(numbers)), str(total), str(mean), str(median), str(stddev)]
                else: stats = [None] * 6
                result.append([name, schema[name]['type'], len(values), missing, len({typed(v, schema[name]['type']) for v in values}), *stats])
        else:
            groups = {}
            for index, row in enumerate(rows):
                if index % 100 == 0 and time.monotonic()-started > 5: fail('Analysis deadline exceeded.')
                key = []
                for group in spec.group_by:
                    value = typed(row[positions[group.column]], schema[group.column]['type'])
                    if value is not None and group.period:
                        value = instant(value, schema[group.column]['type'])
                        day = date.fromisoformat(value[:10])
                        if group.period == 'week': value = (day-timedelta(days=day.weekday())).isoformat()
                        elif group.period == 'month': value = value[:7]
                        elif group.period == 'quarter': value = f'{day.year}-Q{(day.month-1)//3+1}'
                        elif group.period == 'year': value = value[:4]
                        else: value = value[:10]
                    key.append(value)
                groups.setdefault(tuple(key), []).append(row)
                if len(groups) > 2000: fail('More than 2000 groups; add a filter or use coarser grouping.')
            if not spec.group_by and not groups: groups[()] = []
            names = [g.column for g in spec.group_by] + [m.alias for m in spec.metrics] + [d.alias for d in spec.derived]
            kinds = {n: 'decimal' for n in names}
            kinds.update({g.column: 'string' if g.period else schema[g.column]['type'] for g in spec.group_by})
            result = []
            for key, batch in groups.items():
                values_by_alias, output = {}, [str(v) if isinstance(v, Decimal) else v for v in key]
                for metric in spec.metrics:
                    values = [r[positions[metric.column]] for r in batch if r[positions[metric.column]] is not None] if metric.column else [1]*len(batch)
                    excluded[metric.alias] = excluded.get(metric.alias, 0) + len(batch)-len(values)
                    if metric.op == 'count': value = len(values)
                    elif metric.op == 'distinct_count': value = len({typed(v, schema[metric.column]['type']) for v in values})
                    elif not values: value = None
                    else:
                        numbers = [numeric(v) for v in values]
                        if metric.op == 'sum': value = sum(numbers, Decimal(0))
                        elif metric.op == 'average': value = sum(numbers, Decimal(0))/len(numbers)
                        elif metric.op == 'min': value = min(numbers)
                        else: value = max(numbers)
                    values_by_alias[metric.alias] = value
                    output.append(str(value) if isinstance(value, Decimal) else value)
                for metric in spec.derived:
                    a, b = values_by_alias[metric.numerator], values_by_alias[metric.denominator]
                    if a is None or b is None or metric.op == 'ratio' and b == 0:
                        value = None; warnings.append(f'{metric.alias}: missing operand or zero denominator; result unavailable.')
                    else: value = Decimal(a)/Decimal(b)*metric.scale if metric.op == 'ratio' else Decimal(a)-Decimal(b)
                    output.append(str(value) if value is not None else None)
                result.append(output)
    for sort in reversed(spec.sort):
        if sort.column not in names: fail('Sort must reference a result column/metric alias.')
        index = names.index(sort.column)
        # Nulls always last, independent of sort direction.
        populated = [r for r in result if r[index] is not None]
        result = sorted(populated, key=lambda r: typed(r[index], kinds[sort.column]), reverse=sort.descending) + [r for r in result if r[index] is None]
    total = len(result)
    result = result if export_all else result[spec.offset:spec.offset+spec.limit]
    if total > len(result): warnings.append(f'Result page shows {len(result)} of {total} rows. Calculations use all {len(rows)} matching source rows.')
    if any(g.period for g in spec.group_by): warnings.append('Datetime grouping uses UTC; naive timestamps are treated as UTC. Weeks start Monday.')
    return {'columns': names, 'rows': result, 'column_types': kinds, 'total_results': total, 'has_more': not export_all and spec.offset+len(result)<total,
            'source_rows': len(data['rows']), 'matched_rows': len(rows), 'filtered_out': len(data['rows'])-len(rows),
            'missing_excluded': excluded, 'warnings': list(dict.fromkeys(warnings)), 'spec': spec.model_dump(),
            'ai_calls': 0, 'gemini_used': False, 'calculation': 'Deterministic Python; Decimal arithmetic (120 significant digits). Nulls excluded from column metrics; count without a column counts rows.',
            'elapsed_ms': round((time.monotonic()-started)*1000, 2)}

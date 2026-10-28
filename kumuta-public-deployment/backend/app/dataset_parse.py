"""Bounded CSV/basic XLSX value reader. Child process imports only the stdlib.

Never executes formulae, external links or workbook code. Source bytes remain
canonical; blank cells alone are null, and strings/identifiers retain spelling.
"""
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET


def bounded_env(name, default, maximum):
    return max(1, min(maximum, int(os.getenv(name, str(default)))))


MAX_FILE = bounded_env('DATASET_MAX_FILE_BYTES', 4 * 1024 * 1024, 8 * 1024 * 1024)
MAX_ROWS = bounded_env('DATASET_MAX_ROWS', 20000, 50000)
MAX_COLUMNS = bounded_env('DATASET_MAX_COLUMNS', 100, 200)
MAX_CELLS = bounded_env('DATASET_MAX_CELLS', 200000, 500000)
MAX_CELL = 4000
MAX_EXPANDED = 32 * 1024 * 1024
MAX_ENTRIES = 300
MAX_SHEETS = 10
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


class ParseError(ValueError):
    pass


def value_type(value, name=''):
    if value is None or value == '': return 'null'
    v = str(value).strip()
    # Explicit identifiers, leading zeroes and >15 significant digits remain strings.
    if re.search(r'(^|[ _-])(id|code|zip|postal|phone|sku)($|[ _-])', name.lower()): return 'string'
    if re.fullmatch(r'[+-]?0\d+(\.\d+)?', v): return 'string'
    if v.lower() in ('true', 'false'): return 'boolean'
    if re.fullmatch(r'[+-]?\d+(\.\d+)?([eE][+-]?\d{1,3})?', v):
        if len(re.sub(r'\D', '', v.split('e')[0].split('E')[0]).lstrip('0')) > 15: return 'string'
        try:
            d = Decimal(v)
            if d.is_finite() and abs(d) <= Decimal('1e100'):
                return 'integer' if re.fullmatch(r'[+-]?\d+', v) else 'decimal'
        except InvalidOperation: pass
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', v): date.fromisoformat(v); return 'date'
        if re.match(r'^\d{4}-\d{2}-\d{2}T', v): datetime.fromisoformat(v.replace('Z', '+00:00')); return 'datetime'
    except ValueError: pass
    return 'string'


def summarize(name, headers, rows, warnings=None):
    if not headers or len(headers) > MAX_COLUMNS: raise ParseError(f'Use 1–{MAX_COLUMNS} columns.')
    if any(not h.strip() or len(h) > 120 or any(ord(c) < 32 for c in h) for h in headers):
        raise ParseError('Headers must be nonblank text up to 120 characters without control characters.')
    if len(set(h.strip().casefold() for h in headers)) != len(headers): raise ParseError('Duplicate column names. Rename the source headers first.')
    if len(rows) > MAX_ROWS or (len(rows) + 1) * len(headers) > MAX_CELLS: raise ParseError('Dataset row/cell limit exceeded.')
    columns = []
    for i, header in enumerate(headers):
        values = [r[i] for r in rows if r[i] not in ('', None)]
        types = {value_type(v, header) for v in values}
        kind = next(iter(types)) if len(types) == 1 else ('decimal' if types and types <= {'integer', 'decimal'} else 'datetime' if types and types <= {'date', 'datetime'} else 'string' if types else 'null')
        column = {'name': header, 'type': kind, 'missing': len(rows) - len(values), 'distinct': len(set(values)), 'mixed': len(types) > 1 and not (types <= {'integer', 'decimal'} or types <= {'date', 'datetime'})}
        if kind in ('integer', 'decimal'):
            numbers = [Decimal(v.strip()) for v in values]
            with localcontext() as context:
                context.prec = 120
                total = sum(numbers, Decimal(0))
                column.update(min=str(min(numbers)), max=str(max(numbers)), sum=str(total), average=str(total / len(numbers)))
        if kind in ('date', 'datetime'):
            if kind == 'datetime':
                from datetime import timezone
                def normalized(value):
                    dt = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
                    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
                ordered = sorted(values, key=normalized)
                column.update(min=ordered[0], max=ordered[-1])
            else: column.update(min=min(values), max=max(values))
        columns.append(column)
    return {'name': name, 'row_count': len(rows), 'column_count': len(headers), 'columns': columns,
            'warnings': warnings or [], 'rows': rows}


def parse_csv(data):
    try: content = data.decode('utf-8-sig')
    except UnicodeDecodeError: raise ParseError('CSV must be UTF-8 (BOM supported).') from None
    if any(ord(c) < 32 and c not in '\r\n\t' for c in content): raise ParseError('Binary/control characters are not supported in CSV.')
    csv.field_size_limit(MAX_CELL)
    try:
        try: delimiter = csv.Sniffer().sniff(content[:16384], delimiters=',;\t|').delimiter
        except csv.Error: delimiter = ','
        reader = csv.reader(io.StringIO(content, newline=''), delimiter=delimiter, strict=True)
        headers = next(reader, [])
        rows = []
        for row in reader:
            if not row: continue  # Only physically blank lines, not blank cells.
            if len(row) != len(headers): raise ParseError(f'Row {reader.line_num} has {len(row)} cells; expected {len(headers)}.')
            rows.append([v if v != '' else None for v in row])
            if len(rows) > MAX_ROWS or (len(rows) + 1) * len(headers) > MAX_CELLS: raise ParseError('Dataset row/cell limit exceeded.')
        return [summarize('CSV', headers, rows)]
    except csv.Error: raise ParseError('Malformed CSV quoting or cell too long (4000 characters maximum).') from None


def parse_xlsx(data):
    if not data.startswith(b'PK\x03\x04'): raise ParseError('Invalid, encrypted or unsupported XLSX workbook.')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [e.filename for e in entries]
        if len(entries) > MAX_ENTRIES or len(names) != len(set(names)): raise ParseError('Workbook entry limit or duplicate ZIP entries.')
        expanded = 0
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in entry.filename: raise ParseError('Unsafe workbook entry.')
            if entry.flag_bits & 1: raise ParseError('Encrypted workbook not supported.')
            expanded += entry.file_size
            if expanded > MAX_EXPANDED or entry.file_size > 12 * 1024 * 1024 or entry.file_size > max(1024, entry.compress_size * 200):
                raise ParseError('Workbook decompression limit exceeded.')
            lower = entry.filename.lower()
            if 'vbaproject' in lower or 'externallinks/' in lower or lower.endswith('.bin'):
                raise ParseError('Macros, binary parts and external workbook links are unsupported.')
        def xml(path):
            if path not in names: raise ParseError('Required workbook structure is missing.')
            raw = archive.read(path)
            # Reject alternate XML encodings and entity/DTD input before ET.
            if b'\x00' in raw or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper(): raise ParseError('Unsafe XML workbook content.')
            if not re.search(br'encoding\s*=\s*[\'"](?!UTF-8|utf-8|utf8|UTF8)', raw[:200]):
                return ET.fromstring(raw)
            raise ParseError('Workbook XML must use UTF-8.')
        for name in names:
            if name.endswith('.rels'):
                root = xml(name)
                if any(e.get('TargetMode', '').lower() == 'external' for e in root): raise ParseError('External workbook relationships are unsupported.')
        workbook = xml('xl/workbook.xml')
        rels = {e.get('Id'): e.get('Target', '') for e in xml('xl/_rels/workbook.xml.rels')}
        sheets = workbook.findall('s:sheets/s:sheet', NS)
        if not sheets or len(sheets) > MAX_SHEETS: raise ParseError('Workbook must have 1–10 worksheets.')
        sheet_names = [s.get('name', '') for s in sheets]
        if any(not n or len(n) > 120 for n in sheet_names) or len(set(sheet_names)) != len(sheet_names): raise ParseError('Invalid or duplicate worksheet names.')
        shared = []
        if 'xl/sharedStrings.xml' in names:
            for item in xml('xl/sharedStrings.xml').findall('s:si', NS):
                value = ''.join(item.itertext())
                if len(value) > MAX_CELL or len(shared) >= MAX_CELLS: raise ParseError('Workbook shared-string limit exceeded.')
                shared.append(value)
        date_styles = set()
        if 'xl/styles.xml' in names:
            styles = xml('xl/styles.xml')
            formats = {e.get('numFmtId'): e.get('formatCode', '') for e in styles.findall('s:numFmts/s:numFmt', NS)}
            for i, style in enumerate(styles.findall('s:cellXfs/s:xf', NS)):
                fid = style.get('numFmtId', '0')
                code = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', '', formats.get(fid, '')).lower()
                if fid in {str(n) for n in range(14, 23)} | {str(n) for n in range(45, 48)} or re.search('[yd]', code): date_styles.add(i)
        epoch1904 = workbook.find('s:workbookPr', NS)
        epoch1904 = epoch1904 is not None and epoch1904.get('date1904') in ('1', 'true')
        result, total_cells = [], 0
        for sheet in sheets:
            target = rels.get(sheet.get(f'{{{REL_NS}}}id'), '')
            path = target.lstrip('/') if target.startswith('/') else 'xl/' + target
            if '..' in PurePosixPath(path).parts or not path.startswith('xl/worksheets/'): raise ParseError('Unsupported worksheet relationship.')
            root = xml(path)
            grid, formulas, max_col, previous_row = [], 0, 0, 0
            for row in root.findall('s:sheetData/s:row', NS):
                cells, last = {}, -1
                row_number = int(row.get('r', str(previous_row + 1)))
                if row_number <= previous_row or row_number > MAX_ROWS + 1: raise ParseError('Worksheet row limit or invalid row order.')
                for cell in row.findall('s:c', NS):
                    reference = cell.get('r', '')
                    match = re.fullmatch(r'([A-Z]{1,3})([1-9]\d*)', reference)
                    if not match or int(match[2]) != row_number: raise ParseError('Invalid cell reference.')
                    index = 0
                    for letter in match[1]: index = index * 26 + ord(letter) - 64
                    index -= 1
                    if index <= last or index >= MAX_COLUMNS: raise ParseError('Worksheet column limit or duplicate/out-of-order cell.')
                    last = index; max_col = max(max_col, index + 1)
                    value = cell.find('s:v', NS)
                    value = value.text if value is not None else None
                    kind = cell.get('t', '')
                    if cell.find('s:f', NS) is not None: formulas += 1
                    if kind == 'inlineStr': value = ''.join(cell.find('s:is', NS).itertext()) if cell.find('s:is', NS) is not None else None
                    elif kind == 's':
                        if value is None or not value.isdigit() or int(value) >= len(shared): raise ParseError('Invalid shared-string reference.')
                        value = shared[int(value)]
                    elif kind == 'b':
                        if value not in ('0', '1'): raise ParseError('Invalid boolean cell.')
                        value = 'true' if value == '1' else 'false'
                    elif kind == 'e': value = None
                    elif value is not None and int(cell.get('s', '0')) in date_styles and kind not in ('str', 'd'):
                        serial = Decimal(value)
                        if not serial.is_finite() or abs(serial) > 3000000: raise ParseError('Unsupported Excel date value.')
                        if not epoch1904 and 60 <= serial < 61: raise ParseError('Excel fictitious 1900-02-29 cannot be represented. Export ISO dates.')
                        origin = datetime(1904, 1, 1) if epoch1904 else datetime(1899, 12, 31) if serial < 60 else datetime(1899, 12, 30)
                        moment = origin + timedelta(days=float(serial))
                        value = moment.date().isoformat() if serial == int(serial) else moment.isoformat()
                    if value is not None and (len(value) > MAX_CELL or any(ord(c) < 32 and c not in '\t\n\r' for c in value)): raise ParseError('Unsupported cell content/length.')
                    cells[index] = value if value != '' else None
                while len(grid) < row_number - 1: grid.append({})
                grid.append(cells); previous_row = row_number
                if len(grid) * max_col + total_cells > MAX_CELLS: raise ParseError('Workbook total cell limit exceeded.')
            total_cells += len(grid) * max_col
            if not grid or not max_col: continue
            rows = [[r.get(i) for i in range(max_col)] for r in grid]
            headers = [v or '' for v in rows.pop(0)]
            warnings = ['Excel formulas are never evaluated. Cached values may be stale; uncached formulas and error cells are missing. Dates use Excel styles and the workbook epoch; formatting is not preserved.']
            if formulas: warnings.append(f'{formulas} formula cells use cached values only.')
            result.append(summarize(sheet.get('name', 'Sheet'), headers, rows, warnings))
        if not result: raise ParseError('No nonempty worksheets with headers.')
        return result


def parse(data, format):
    if not data or len(data) > MAX_FILE: raise ParseError('Dataset file is empty or exceeds the upload limit.')
    try:
        if format == 'csv': return parse_csv(data)
        if format == 'xlsx': return parse_xlsx(data)
        raise ParseError('Use CSV or XLSX.')
    except (zipfile.BadZipFile, ET.ParseError, KeyError, OverflowError, InvalidOperation, IndexError, ValueError) as exc:
        if isinstance(exc, ParseError): raise
        raise ParseError('Malformed or unsupported workbook values/structure.') from None


if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    try:
        with open(sys.argv[1], 'rb') as stream: data = stream.read(MAX_FILE + 1)
        print(json.dumps({'sheets': parse(data, sys.argv[2])}, ensure_ascii=False))
    except ParseError as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(2)

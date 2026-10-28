"""Local extraction child. No application config, database, provider or network access.

pdfnaut supplies PDF parsing and tokenization. Original adapter handles common
text operators and embedded ToUnicode maps without bundled third-party fonts.
Unsupported font encodings fail explicitly instead of fabricating text.
"""
import io
import json
from pathlib import Path
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

MAX_TEXT = 250_000
MAX_DECODED = 8 * 1024 * 1024
MAX_PAGES = 200
WORD = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


class ExtractionError(ValueError):
    pass


def unicode_map(raw):
    # CMap mappings are read from this user's document, never bundled assets.
    from pdfnaut.cos.tokenizer import ContentStreamTokenizer
    from pdfnaut.cos.objects import PdfHexString, PdfArray
    mapping = {}
    for op in ContentStreamTokenizer(raw):
        if op.name == b'endbfchar':
            for left, right in zip(op.args[::2], op.args[1::2]):
                if isinstance(left, PdfHexString) and isinstance(right, PdfHexString):
                    try: mapping[left.value] = right.value.decode('utf-16-be')
                    except UnicodeDecodeError: pass  # Unused invalid map entries must not corrupt valid glyphs.
        elif op.name == b'endbfrange':
            for i in range(0, len(op.args) - 2, 3):
                low, high, values = op.args[i:i+3]
                if not isinstance(low, PdfHexString) or not isinstance(high, PdfHexString):
                    continue
                start, end = int.from_bytes(low.value, 'big'), int.from_bytes(high.value, 'big')
                if end - start > 65536:
                    raise ExtractionError('PDF font mapping is too large.')
                for number in range(start, end + 1):
                    if isinstance(values, PdfArray):
                        target = values[number - start].value
                    elif isinstance(values, PdfHexString):
                        target = (int.from_bytes(values.value, 'big') + number - start).to_bytes(len(values.value), 'big')
                    else:
                        raise ExtractionError('Unsupported PDF font mapping.')
                    try: mapping[number.to_bytes(len(low.value), 'big')] = target.decode('utf-16-be')
                    except UnicodeDecodeError: pass
        if len(mapping) > 65536:
            raise ExtractionError('PDF font mapping is too large.')
    return mapping


def pdf_pages(data):
    from pdfnaut import PdfDocument
    from pdfnaut.cos.objects import PdfArray, PdfHexString, PdfName, PdfStream
    from pdfnaut.cos.tokenizer import ContentStreamTokenizer
    if not data.startswith(b'%PDF-'):
        raise ExtractionError('Invalid PDF signature.')
    pdf = PdfDocument(data)
    if pdf.has_encryption:
        raise ExtractionError('Encrypted PDFs are not supported. Upload an unencrypted copy.')
    if len(pdf.pages) > MAX_PAGES:
        raise ExtractionError(f'PDF exceeds {MAX_PAGES} pages.')
    pages, decoded_bytes, total_text = [], 0, 0

    def decode_stream(stream):
        nonlocal decoded_bytes
        value = stream.decode()
        decoded_bytes += len(value)
        if decoded_bytes > MAX_DECODED:
            raise ExtractionError('PDF decompressed content exceeds the processing limit.')
        return value

    def resources_for(page):
        obj = page
        for _ in range(40):
            if obj.get('Resources') is not None:
                return obj['Resources']
            obj = obj.get('Parent')
            if obj is None:
                break
        return {}

    def text_for(streams, resources, depth=0):
        if depth > 8:
            raise ExtractionError('PDF forms are nested too deeply.')
        if not streams:
            return ''
        streams = streams if isinstance(streams, PdfArray) else [streams]
        fonts = resources.get('Font', {})
        font, result, in_text, saved_fonts = None, [], False, []
        checked, result_size = 0, 0
        maps = {}

        def font_text(value):
            raw = value.value if isinstance(value, PdfHexString) else value
            if not isinstance(raw, bytes):
                return ''
            selected = fonts.get(font, {}) if font else {}
            if font not in maps:
                cmap = selected.get('ToUnicode')
                maps[font] = unicode_map(decode_stream(cmap)) if cmap else None
            mapping = maps[font]
            if mapping:
                lengths = sorted({len(k) for k in mapping}, reverse=True)
                parts, i = [], 0
                while i < len(raw):
                    for length in lengths:
                        if raw[i:i+length] in mapping:
                            parts.append(mapping[raw[i:i+length]]); i += length; break
                    else:
                        raise ExtractionError('PDF contains unmapped text glyphs; export it as UTF-8 text or DOCX.')
                return ''.join(parts)
            encoding = selected.get('Encoding')
            name = encoding.value if isinstance(encoding, PdfName) else None
            base = selected.get('BaseFont')
            base = base.value if isinstance(base, PdfName) else b''
            subtype = selected.get('Subtype')
            if isinstance(subtype, PdfName) and subtype.value == b'Type0':
                raise ExtractionError('PDF composite fonts need a ToUnicode map. Export this file as text or DOCX.')
            if encoding is not None and name not in (b'WinAnsiEncoding', b'MacRomanEncoding', b'StandardEncoding'):
                raise ExtractionError('Custom PDF font encoding without ToUnicode is unsupported. Export as text or DOCX.')
            if b'Symbol' in base or b'ZapfDingbats' in base:
                raise ExtractionError('Symbol fonts without ToUnicode are unsupported.')
            if name == b'MacRomanEncoding':
                return raw.decode('mac_roman')
            if name == b'WinAnsiEncoding':
                return raw.decode('cp1252')
            if any(c >= 128 for c in raw):
                raise ExtractionError('Non-ASCII PDF text needs WinAnsi, MacRoman or ToUnicode encoding.')
            return raw.decode('ascii')

        for stream in streams:
            if not isinstance(stream, PdfStream):
                continue
            for op in ContentStreamTokenizer(decode_stream(stream)):
                name, args = op.name, op.args
                if name == b'BT': in_text = True
                elif name == b'ET': in_text = False; result.append('\n')
                elif name == b'q': saved_fonts.append(font)
                elif name == b'Q' and saved_fonts: font = saved_fonts.pop()
                elif name == b'Tf' and args: font = args[0].value.decode('latin1')
                elif name in (b'Td', b'TD', b'T*', b'Tm') and in_text: result.append('\n')
                elif name in (b'Tj', b"'", b'"') and in_text and args:
                    if name != b'Tj': result.append('\n')
                    result.append(font_text(args[-1]))
                elif name == b'TJ' and in_text and args:
                    for value in args[0]:
                        if isinstance(value, (bytes, PdfHexString)): result.append(font_text(value))
                        elif isinstance(value, (float, int)) and value < -120: result.append(' ')
                elif name == b'Do' and args:
                    form = resources.get('XObject', {}).get(args[0].value.decode('latin1'))
                    subtype = form.details.get('Subtype') if isinstance(form, PdfStream) else None
                    if isinstance(subtype, PdfName) and subtype.value == b'Form':
                        result.append(text_for(form, form.details.get('Resources', resources), depth+1))
                result_size += sum(map(len, result[checked:]))
                checked = len(result)
                if result_size > MAX_TEXT:
                    raise ExtractionError('Extracted text exceeds the processing limit.')
        return ''.join(result)

    for number, page in enumerate(pdf.pages, 1):
        value = re.sub(r'\n{3,}', '\n\n', text_for(page.get('Contents'), resources_for(page))).strip()
        total_text += len(value)
        if total_text > MAX_TEXT:
            raise ExtractionError('Extracted text exceeds the processing limit.')
        pages.append({'page': number, 'section': '', 'text': value})
    return pages, 'PDF text follows content-stream order; complex columns and visual tables may need manual review. OCR is off.'


def docx_pages(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 2000 or sum(i.file_size for i in infos) > MAX_DECODED:
                raise ExtractionError('DOCX expanded content exceeds the processing limit.')
            if any(i.flag_bits & 1 for i in infos):
                raise ExtractionError('Encrypted DOCX archives are not supported.')
            if 'word/document.xml' not in archive.namelist() or '[Content_Types].xml' not in archive.namelist():
                raise ExtractionError('Upload a valid DOCX document.')
            if any('vbaproject' in i.filename.casefold() for i in infos):
                raise ExtractionError('Macro-enabled documents are not supported.')
            raw = archive.read('word/document.xml')
    except zipfile.BadZipFile:
        raise ExtractionError('Invalid DOCX ZIP content.') from None
    declaration_check = raw.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in declaration_check or b'<!ENTITY' in declaration_check:
        raise ExtractionError('XML entities are not permitted in DOCX.')
    root = ET.fromstring(raw)
    body = root.find(WORD + 'body')
    if body is None:
        raise ExtractionError('DOCX has no document body.')
    blocks, heading = [], 'Document body'
    for node in body:
        if node.tag == WORD + 'p':
            value = ''.join('\t' if c.tag == WORD + 'tab' else '\n' if c.tag == WORD + 'br' else c.text or ''
                            for c in node.iter() if c.tag in (WORD+'t', WORD+'tab', WORD+'br'))
            style = node.find('.//' + WORD + 'pStyle')
            if style is not None and style.get(WORD+'val', '').lower().startswith('heading'):
                heading = value[:120] or heading
            if value.strip(): blocks.append({'page': None, 'section': heading, 'text': value.strip()})
        elif node.tag == WORD + 'tbl':
            rows = [' | '.join(' '.join(t.text or '' for t in cell.iter(WORD+'t')) for cell in row.findall(WORD+'tc')) for row in node.findall(WORD+'tr')]
            blocks.append({'page': None, 'section': heading + ' · table', 'text': '\n'.join(rows)})
    return blocks, 'DOCX references use headings/sections. Physical page numbers require a layout engine and are not invented.'


def extract(data, mime):
    if mime == 'application/pdf':
        pages, warning = pdf_pages(data)
    elif mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        pages, warning = docx_pages(data)
    else:
        try: value = data.decode('utf-8-sig')
        except UnicodeDecodeError: raise ExtractionError('Text documents must use UTF-8 encoding.') from None
        if '\x00' in value or any(ord(c) < 32 and c not in '\n\r\t\f' for c in value):
            raise ExtractionError('Binary content is not a text document.')
        pages = [{'page': None, 'section': 'Text', 'text': value}]
        warning = None
    total = sum(len(p['text']) for p in pages)
    if total > MAX_TEXT:
        raise ExtractionError(f'Document exceeds {MAX_TEXT:,} extracted characters.')
    if not any(p['text'].strip() for p in pages):
        raise ExtractionError('No readable text found. Scanned PDFs/images need OCR, which is disabled.')
    chunks = []
    for block in pages:
        value = block['text'].strip()
        start = 0
        while start < len(value):
            end = min(len(value), start + 1800)
            if end < len(value):
                split = max(value.rfind('\n', start + 900, end), value.rfind(' ', start + 900, end))
                if split > start: end = split
            chunks.append({'page': block['page'], 'section': block['section'][:120], 'content': value[start:end], 'ordinal': len(chunks)})
            if end == len(value): break
            start = max(start + 1, end - 150)
    return {'chunks': chunks, 'pages': len(pages) if mime == 'application/pdf' else 0, 'warning': warning}


if __name__ == '__main__':
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        sys.stdout.write(json.dumps(extract(Path(sys.argv[1]).read_bytes(), sys.argv[2])))
    except ExtractionError as exc:
        sys.stdout.write(json.dumps({'error': str(exc)}))
    except Exception:
        sys.stdout.write(json.dumps({'error': 'Document could not be processed safely. Check its format and encoding, then retry.'}))

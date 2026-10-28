"""Shared bounded validation for ordinary chat and Canvas uploads."""
import base64
from pathlib import Path
import pymupdf as fitz
from fastapi import HTTPException

MAX_FILE = 8 * 1024 * 1024
MAX_ATTACHMENTS = 5
MAX_TOTAL_FILES = 20 * 1024 * 1024
ALLOWED = {'image/png', 'image/jpeg', 'application/pdf'}

async def read_attachment(attachment):
    if not attachment:
        return {}
    name = Path((attachment.filename or 'upload').replace('\\', '/')).name[:255]
    mime = attachment.content_type
    if mime == 'image/webp' or name.lower().endswith('.webp'):
        raise HTTPException(415, 'WebP is blocked by the dependency policy. Use PNG or JPEG.')
    if mime not in ALLOWED:
        raise HTTPException(415, 'Only PNG, JPEG and PDF files are supported.')
    raw = await attachment.read(MAX_FILE + 1)
    if not raw or len(raw) > MAX_FILE:
        raise HTTPException(413, 'Choose a nonempty file up to 8 MB.')
    if mime == 'application/pdf':
        if not raw.startswith(b'%PDF-'):
            raise HTTPException(415, 'Invalid PDF file.')
        try:
            with fitz.open(stream=raw, filetype='pdf') as pdf:
                if pdf.needs_pass:
                    raise HTTPException(415, 'Unlock this password-protected PDF before uploading it.')
                if not 0 < pdf.page_count <= 50:
                    raise HTTPException(413, 'PDF must contain between 1 and 50 pages.')
        except (ValueError, RuntimeError):
            raise HTTPException(415, 'This PDF cannot be read.') from None
    else:
        valid = ((mime == 'image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n')) or
                 (mime == 'image/jpeg' and raw.startswith(b'\xff\xd8')) or
                 (mime == 'image/webp' and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP'))
        if not valid:
            raise HTTPException(415, 'File contents do not match the image type.')
        try:
            with fitz.open(stream=raw, filetype={'image/png': 'png', 'image/jpeg': 'jpeg', 'image/webp': 'webp'}[mime]) as image:
                if image[0].rect.width * image[0].rect.height > 40_000_000:
                    raise HTTPException(413, 'Image exceeds 40 megapixels.')
        except (ValueError, RuntimeError):
            raise HTTPException(415, 'WebP decoding is unavailable in this installation. Use PNG or JPEG.' if mime == 'image/webp' else 'This image cannot be read.') from None
    return {'attachment_name': name, 'attachment_mime': mime, 'attachment_size': len(raw),
            'attachment_data': base64.b64encode(raw).decode('ascii')}


async def read_attachments(uploads, images_only=False):
    if len(uploads) > MAX_ATTACHMENTS:
        raise HTTPException(413, 'Attach up to 5 files per message.')
    fields, total = [], 0
    for upload in uploads:
        if upload.content_type == 'image/webp' or (upload.filename or '').lower().endswith('.webp'):
            raise HTTPException(415, 'WebP decoding is unavailable under the current dependency policy. Use PNG or JPEG.')
        if images_only and upload.content_type not in ALLOWED - {'application/pdf'}:
            raise HTTPException(415, 'Canvas accepts PNG and JPEG images. Use chat Documents for PDFs.')
        validated = await read_attachment(upload)
        total += validated['attachment_size']
        if total > MAX_TOTAL_FILES:
            raise HTTPException(413, 'Attachments exceed the 20 MB total limit per message.')
        fields.append(validated)
    return fields

"""Match ListModels IDs to Google's Standard pricing, never infer tier from names."""
import asyncio
import json
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import httpx

SOURCE = 'https://ai.google.dev/gemini-api/docs/pricing?hl=en'
MAX_AGE = 7 * 86400
_cache = None
_retry_at = 0
_lock = asyncio.Lock()


class PricingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.catalog = {}
        self.ids = []
        self.mode = ''
        self.capture = None
        self.buffer = ''
        self.rows = None
        self.row = []
        self.done = False

    def handle_starttag(self, tag, attrs):
        if tag == 'h2':
            self.ids, self.mode, self.done = [], '', False
        if tag in ('h3', 'code') and self.rows is None:
            self.capture, self.buffer = tag, ''
        if tag == 'table' and not self.done and self.ids and self.mode in ('', 'standard'):
            self.rows = []
        if self.rows is not None:
            if tag == 'tr':
                self.row = []
            if tag in ('td', 'th'):
                self.capture, self.buffer = tag, ''

    def handle_data(self, data):
        if self.capture:
            self.buffer += data

    def handle_endtag(self, tag):
        if tag == self.capture:
            value = ' '.join(self.buffer.split()).lower()
            if tag == 'h3':
                self.mode = value
            elif tag == 'code' and value.startswith('gemini-') and not self.done:
                self.ids.append(value)
            elif tag in ('td', 'th'):
                self.row.append(value)
            self.capture = None
        if self.rows is not None:
            if tag == 'tr':
                self.rows.append(self.row)
            if tag == 'table':
                headers = next((r for r in self.rows if 'free tier' in r), [])
                prices = [r for r in self.rows if len(r) >= 3 and
                          (r[0].startswith('input price') or r[0].startswith('output price'))]
                tier = None
                if len(headers) >= 3 and headers[1] == 'free tier' and 'paid tier' in headers[2] and len(prices) == 2:
                    if all(r[1] == 'free of charge' for r in prices):
                        tier = 'free'
                    elif all(r[1] == 'not available' and r[2] for r in prices):
                        tier = 'paid'
                if tier:
                    self.catalog.update({name: tier for name in self.ids})
                self.rows, self.done = None, True


def parse_pricing(html):
    parser = PricingParser()
    parser.feed(html)
    if not parser.catalog:
        raise ValueError('No recognizable Standard pricing tables')
    return parser.catalog


async def catalog(refresh=False):
    global _cache, _retry_at
    async with _lock:
        if _cache is None:
            try:
                _cache = json.loads(Path(__file__).with_name('pricing_snapshot.json').read_text())
            except (OSError, ValueError):
                _cache = {'checked_at': '', 'models': {}}
        try:
            age = time.time() - datetime.fromisoformat(_cache['checked_at']).timestamp()
        except ValueError:
            age = MAX_AGE + 1
        if (refresh or age > 86400) and time.monotonic() >= _retry_at:
            try:
                async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                    response = await client.get(SOURCE)
                    response.raise_for_status()
                    verified = parse_pricing(response.text)
                _cache = {'checked_at': datetime.now(timezone.utc).isoformat(), 'models': verified}
                age = 0
            except (httpx.HTTPError, ValueError):
                # A bounded fallback is labeled with its actual verification date.
                _retry_at = time.monotonic() + 60
        return {'checked_at': _cache['checked_at'], 'models': _cache['models'] if age <= MAX_AGE else {}}


async def classify(models, refresh=False):
    verified = await catalog(refresh)
    for model in models:
        model.update(tier=verified['models'].get(model['id'], 'unknown'),
                     pricing_source=SOURCE, pricing_checked_at=verified['checked_at'])
    return sorted(models, key=lambda m: (m['tier'] != 'free', m['name'].lower()))


def free_default(models):
    free = [m for m in models if m['tier'] == 'free']
    # Prefer a lightweight stable model without pinning a version that can expire.
    free.sort(key=lambda m: ('flash-lite' not in m['id'], 'preview' in m['id'], m['id']))
    return free[0]['id'] if free else None

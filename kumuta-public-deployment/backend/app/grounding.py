"""Normalize generateContent grounding metadata without trusting provider URLs or HTML."""
from urllib.parse import urlsplit


def safe_url(value):
    try:
        p = urlsplit(value)
        return value if p.scheme in ('http', 'https') and p.hostname and not p.username and not p.password else None
    except (TypeError, ValueError):
        return None


class Grounding:
    def __init__(self, enabled):
        self.enabled = enabled
        self.sources = []
        self.citations = []
        self.queries = set()
        self.queries_reported = False
        self.entry = None

    def add(self, chunk):
        for candidate in getattr(chunk, 'candidates', None) or []:
            data = getattr(candidate, 'grounding_metadata', None)
            if data is None:
                continue
            if getattr(data, 'web_search_queries', None) is not None:
                self.queries_reported = True
            mapping = {}
            for index, item in enumerate(getattr(data, 'grounding_chunks', None) or []):
                web = getattr(item, 'web', None)
                url = safe_url(getattr(web, 'uri', None))
                if not url:
                    continue
                existing = next((i for i, s in enumerate(self.sources) if s['url'] == url), None)
                if existing is None and len(self.sources) < 100:
                    existing = len(self.sources)
                    self.sources.append({'url': url, 'title': (getattr(web, 'title', None) or urlsplit(url).hostname)[:300]})
                if existing is not None:
                    mapping[index] = existing + 1
            for support in (getattr(data, 'grounding_supports', None) or [])[:200]:
                segment = getattr(support, 'segment', None)
                refs = [mapping[i] for i in getattr(support, 'grounding_chunk_indices', None) or [] if i in mapping]
                if segment is not None and refs:
                    citation = {'text': (getattr(segment, 'text', None) or '')[:12000],
                                'start': getattr(segment, 'start_index', None), 'end': getattr(segment, 'end_index', None),
                                'sources': refs}
                    if citation not in self.citations and len(self.citations) < 200:
                        self.citations.append(citation)
            self.queries.update(q[:1000] for q in (getattr(data, 'web_search_queries', None) or []) if q.strip())
            entry = getattr(data, 'search_entry_point', None)
            html = getattr(entry, 'rendered_content', None)
            if html:
                self.entry = html[:100000]

    def view(self):
        if not self.enabled:
            return None
        return {'enabled': True, 'grounded': bool(self.sources), 'sources': self.sources,
                'citations': self.citations, 'queries': sorted(self.queries),
                'query_count': len(self.queries) if self.queries_reported else None, 'search_entry_point': self.entry}

    def cite_markdown(self, answer):
        # Grounding indices are UTF-8 bytes. Match supplied segment text first,
        # and never insert a link into a fenced UI/code block.
        inserts = {}
        encoded = answer.encode('utf-8')
        for c in self.citations:
            text = c['text']
            end = answer.find(text) + len(text) if text and text in answer else -1
            if end < 0 and isinstance(c['end'], int) and 0 < c['end'] <= len(encoded):
                try:
                    end = len(encoded[:c['end']].decode('utf-8'))
                except UnicodeDecodeError:
                    continue
            if end <= 0 or answer[:end].count('```') % 2:
                continue
            refs = inserts.setdefault(end, set())
            refs.update(c['sources'])
        for end, refs in sorted(inserts.items(), reverse=True):
            links = ' ' + ' '.join(f'[{i}]({self.sources[i-1]["url"]})' for i in sorted(refs))
            answer = answer[:end] + links + answer[end:]
        return answer

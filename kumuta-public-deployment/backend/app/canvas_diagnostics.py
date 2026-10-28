"""Bounded Canvas failure codes and messages; never persist provider error bodies."""
import asyncio
import httpx
from fastapi import HTTPException

MESSAGES = {
    '429': ('quota_exhausted', 'Google reports a quota or rate limit. Check AI Studio quota and billing, then retry later or choose an eligible model.'),
    '503': ('provider_unavailable', 'Google reports this model is temporarily busy. Retry shortly or choose another available model.'),
    '500': ('provider_unavailable', 'Google is temporarily unavailable. Retry later or choose another available model.'),
    '502': ('provider_unavailable', 'Google is temporarily unavailable. Check your connection and retry later.'),
    '504': ('provider_unavailable', 'Google did not respond in time. Retry later or choose another available model.'),
    '400': ('unsupported_request', 'Google rejected the Canvas request format for this model. Choose another available model or review generation settings.'),
    '401': ('authentication', 'Google rejected this API key. Check your key and project permissions in Settings.'),
    '403': ('authentication', 'Google denied access. Check your key, project permissions and model eligibility in Settings.'),
    '404': ('unsupported_model', 'This model is unavailable. Refresh models in Settings and choose an available model.'),
    'key_unavailable': ('authentication', 'Your saved API key cannot be read. Review the key and encryption configuration in Settings.'),
    'model_eligibility': ('unsupported_model', 'The selected model is unavailable or ineligible. Review model, pricing and key settings before retrying.'),
    'timeout': ('generation_timeout', 'Generation timed out. Retry explicitly or choose another available model.'),
    'unsupported_component': ('invalid_openui', 'The model used an unsupported OpenUI component. Use Table, Cards, Chart (bar/line), Timeline, Calculator, Progress, Checklist or Form inside one root Stack.'),
    'invalid_openui': ('invalid_openui', 'The model returned invalid OpenUI. Request supported components with fewer items, retry explicitly, or choose Legacy JSON in Generation options.'),
    'invalid_spec': ('invalid_specification', 'The model returned an invalid specification. Try fewer items or a supported component, then retry explicitly.'),
    'MAX_TOKENS': ('truncated_output', 'The model output was truncated at its token limit. Request fewer components or rows, or choose a model with a larger output budget.'),
    'blocked_output': ('blocked_output', 'Google returned blocked or empty output. Rephrase the request and retry explicitly.'),
    'stream_limit': ('invalid_openui', 'OpenUI output exceeded the bounded stream limit. Request fewer components or rows.'),
    'unknown': ('unknown_historical_error', 'Historical failure has no exact diagnostic code.'),
    'internal': ('internal_backend_error', 'An internal Canvas error interrupted generation. Refresh saved state and retry explicitly.'),
}

class CanvasFailure(HTTPException):
    def __init__(self, code):
        self.diagnostic_code = code
        super().__init__(422, MESSAGES[code][1] + ' Your accepted version is preserved. No automatic retry was made.')


def failure_code(exc, stage):
    if isinstance(exc, CanvasFailure): return exc.diagnostic_code
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)): return 'timeout'
    code = str(getattr(exc, 'code', '') or '')
    if code in MESSAGES: return code
    if isinstance(exc, HTTPException):
        if stage == 'planning' and exc.status_code == 503 and 'decrypt' in str(exc.detail): return 'key_unavailable'
        if exc.status_code in (429, 503, 502, 504): return str(exc.status_code)
        if stage == 'planning' and exc.status_code in (400, 428): return 'model_eligibility'
        return 'request_rejected'
    if isinstance(exc, httpx.TransportError): return '502'
    return 'internal'


def historical_code(error, status):
    if status == 'timed_out': return 'timeout'
    text = (error or '').lower()
    for needle, code in [('quota','429'), ('temporarily busy','503'), ('could not process','400'), ('invalid specification','invalid_spec'), ('invalid openui','invalid_openui'), ('ineligible','model_eligibility'), ('model is unavailable','404')]:
        if needle in text: return code
    return 'unknown'

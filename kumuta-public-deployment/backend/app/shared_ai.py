"""Presentation adapters over the single restricted OpenUI/QuickUI registry."""
import os
import re
from . import canvas_openui, quickui

OPENUI_FENCE = re.compile(r'^```openui(?:-lang)?\s*\n(.*?)^```[ \t]*$', re.M | re.S)


def enabled():
    return os.getenv('KUMUTA_OPENUI_ENABLED', 'true').lower() not in ('false', '0', 'no')


def chat_instructions():
    if not enabled():
        return quickui.PROMPT
    registry = canvas_openui.registry_prompt(compact=True).replace("Return only OpenUI Lang in Kumuta's restricted library.", "QuickUI uses Kumuta's restricted OpenUI component library:").replace('or code fences.', 'inside the program.')
    return ('\n' + registry + '\nMatch the interface to the question and available data. Use tables for records, charts for numerical comparisons, calculators for financial scenarios, forms/checklists for assessments, and timelines for workflows; combine components only when useful. For interactive explanations, charts, tables and forms, use the restricted OpenUI registry above. '
            'Ordinary answers remain Markdown. You may put Markdown before and after ONE ```openui fenced program. '
            'Never emit executable code, HTML, external handlers or calculated spreadsheet totals. '
            'Always wrap the program in that fence; Markdown outside it is permitted.')


def extract(answer):
    match = OPENUI_FENCE.search(answer)
    if not match:
        content, spec, error = quickui.extract(answer)
        return content, spec, quickui.FENCE.sub('', answer).strip() if spec else '', error
    try:
        if len(match[1].encode()) > 100000 or len(OPENUI_FENCE.findall(answer)) != 1:
            raise ValueError('OpenUI program limit exceeded.')
        spec = canvas_openui.parse_program(match[1])
    except (ValueError, RecursionError):
        return answer + '\n\n> Interactive UI could not be validated. The original response is shown above.', None, '', 'invalid_specification'
    introduction = (answer[:match.start()] + answer[match.end():]).strip()
    return (introduction + '\n\n' + quickui.fallback(spec)).strip(), spec, introduction, None

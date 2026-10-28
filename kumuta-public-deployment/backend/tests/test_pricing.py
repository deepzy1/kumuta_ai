import unittest
from unittest.mock import patch
import httpx
from app import pricing


def section(ids, free, mode='Standard'):
    return '<h2>Model</h2>' + ''.join(f'<code>{name}</code>' for name in ids) + f'''<h3>{mode}</h3><table>
    <tr><th></th><th>Free Tier</th><th>Paid Tier, per 1M tokens</th></tr>
    <tr><td>Input price</td><td>{free}</td><td>$1</td></tr>
    <tr><td>Output price (including thinking tokens)</td><td>{free}</td><td>$2</td></tr></table>'''


class PricingTests(unittest.IsolatedAsyncioTestCase):
    def test_standard_both_prices_exact_ids_and_aliases(self):
        html = section(['gemini-new-flash'], 'Free of charge')
        html += '<h3>Batch</h3><table><tr><td>Input price</td><td>Not available</td><td>$1</td></tr></table>'
        html += section(['gemini-new-pro', 'gemini-new-pro-customtools'], 'Not available')
        html += section(['gemini-ambiguous'], 'Check pricing')
        self.assertEqual(pricing.parse_pricing(html), {'gemini-new-flash': 'free', 'gemini-new-pro': 'paid', 'gemini-new-pro-customtools': 'paid'})
        with self.assertRaises(ValueError):
            pricing.parse_pricing('<h2>Changed page</h2>')

    async def test_expired_pricing_never_marks_models_free_after_fetch_failure(self):
        with patch.object(pricing, '_cache', {'checked_at': '2020-01-01T00:00:00+00:00', 'models': {'gemini-old': 'free'}}), patch.object(pricing, '_retry_at', 0), patch.object(httpx.AsyncClient, 'get', side_effect=httpx.ConnectError('offline')):
            result = await pricing.classify([{'id': 'gemini-old', 'name': 'Old'}])
            self.assertEqual(result[0]['tier'], 'unknown')
            self.assertEqual(result[0]['pricing_checked_at'], '2020-01-01T00:00:00+00:00')

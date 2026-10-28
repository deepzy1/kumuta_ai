import test from 'node:test';
import assert from 'node:assert/strict';
import { reportQuery, metric, hours } from './analyticsData.js';
test('Reporting filters encode zones, omit empty scopes, and preserve custom calendar dates', () => {
  const query = new URLSearchParams(reportQuery({ preset: 'custom', start: '2026-03-08', end: '2026-03-09', timezone: 'America/New_York', projectId: 7, courseId: 8, offset: 50 }));
  assert.equal(query.get('tz'), 'America/New_York');
  assert.equal(query.get('start'), '2026-03-08');
  assert.equal(query.get('end'), '2026-03-09');
  assert.equal(query.get('project_id'), '7');
  assert.equal(query.get('course_id'), '8');
  assert.equal(query.get('workspace_id'), null);
  assert.equal(query.get('offset'), '50');
  const preset = new URLSearchParams(reportQuery({ preset: 'today', start: 'old', end: 'old', timezone: 'UTC' }));
  assert.equal(preset.has('start'), false);
});
test('Known zero values are distinct from unavailable measurements', () => {
  assert.equal(metric(null, '%'), 'Unavailable'); assert.equal(metric(0, '%'), '0%');
  assert.equal(hours(undefined), 'Unavailable'); assert.equal(hours(0), '0.00 h'); assert.equal(hours(5400), '1.50 h');
});

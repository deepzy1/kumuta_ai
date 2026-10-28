export function reportQuery({ preset, start, end, timezone, workspaceId, projectId, courseId, offset = 0 }) {
  const query = new URLSearchParams({ preset, tz: timezone, limit: '50', offset: String(offset) });
  for (const [key, value] of [['workspace_id', workspaceId], ['project_id', projectId], ['course_id', courseId]]) {
    if (value) query.set(key, String(value));
  }
  if (preset === 'custom') { query.set('start', start); query.set('end', end); }
  return query.toString();
}
export const metric = (value, suffix = '') => value == null ? 'Unavailable' : `${value}${suffix}`;
export function hours(seconds) { return seconds == null ? 'Unavailable' : `${(seconds / 3600).toFixed(2)} h`; }

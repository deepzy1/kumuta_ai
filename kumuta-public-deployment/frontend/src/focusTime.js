// Derive display from a server snapshot and monotonic browser elapsed time.
export function timerSnapshot(session, receivedAt = performance.now()) {
  return { session, receivedAt };
}
export function timerSeconds(snapshot, current = performance.now()) {
  if (!snapshot?.session) return 0;
  const s = snapshot.session;
  const elapsed = s.elapsed_seconds + (s.status === 'running' ? Math.max(0, current - snapshot.receivedAt) / 1000 : 0);
  return s.planned_seconds == null ? Math.max(0, elapsed) : Math.max(0, s.planned_seconds - elapsed);
}
export function durationText(value) {
  const seconds = Math.max(0, Math.ceil(value));
  const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60), rest = seconds % 60;
  return `${hours ? `${hours}:` : ''}${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}

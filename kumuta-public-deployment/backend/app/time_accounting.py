"""Shared allocation of ledger segments across UTC calendar boundaries."""
import json
from datetime import datetime, timezone

UTC = timezone.utc


def allocate(entry, boundaries):
    """Clip recorded running segments at UTC instants, including DST boundaries."""
    segments = json.loads(entry.segments)
    estimated = entry.allocation_estimated or not segments
    if estimated:
        segments = [[entry.started_at, entry.ended_at]]
    span = sum(max(0, (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()) for a, b in segments)
    ratio = min(1, entry.duration_seconds / span) if estimated and span else 1
    totals = [0.0] * (len(boundaries) - 1)
    for a, b in segments:
        a, b = datetime.fromisoformat(a).astimezone(UTC), datetime.fromisoformat(b).astimezone(UTC)
        for i, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
            totals[i] += max(0, (min(b, end) - max(a, start)).total_seconds()) * ratio
    return totals, estimated


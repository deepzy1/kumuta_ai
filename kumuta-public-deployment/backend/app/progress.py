"""Shared local progress definitions; no provider or persistence dependencies."""
def percentage(completed, total, empty=0):
    return round(100 * completed / total) if total else empty


def mean_progress(values, empty=0):
    return round(sum(values) / len(values)) if values else empty


def goal_progress(milestones, tasks, status):
    return percentage(sum(x['completed'] for x in milestones) + sum(tasks),
                      len(milestones) + len(tasks), 100 if status == 'completed' else 0)

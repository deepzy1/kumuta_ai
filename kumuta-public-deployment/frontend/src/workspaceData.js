// Collections are paginated: never render a silently truncated board or sidebar.
export async function allPages(api, path, options = {}) {
  const items = [];
  const seen = new Set();
  for (let offset = 0; ; ) {
    const page = await api(`${path}${path.includes('?') ? '&' : '?'}limit=100&offset=${offset}`, options);
    for (const item of page.items) {
      if (!seen.has(item.id)) { seen.add(item.id); items.push(item); }
    }
    if (!page.has_more) return items;
    if (!page.items.length) throw new Error('The collection changed while loading. Refresh and try again.');
    offset += page.items.length;
  }
}

export async function loadBoard(api, pid) {
  // A mutation during pagination invalidates the snapshot; retry once, then ask
  // the user to refresh instead of sending a move with mismatched positions.
  for (let attempt = 0; attempt < 2; attempt++) {
    const columns = await api(`/projects/${pid}/columns`);
    const tasks = [];
    let consistent = true;
    for (let offset = 0; ; ) {
      const page = await api(`/projects/${pid}/tasks?limit=200&offset=${offset}`);
      if (page.board_revision !== columns.board_revision) { consistent = false; break; }
      tasks.push(...page.items);
      if (!page.has_more) break;
      if (!page.items.length) { consistent = false; break; }
      offset += page.items.length;
    }
    if (consistent) return { columns: columns.items, tasks, revision: columns.board_revision };
  }
  throw new Error('This board is changing on another device. Refresh and try again.');
}

const priorities = { urgent: 0, high: 1, medium: 2, low: 3, none: 4 };
export function visibleTasks(tasks, { search = '', priority = '', status = '', sort = 'position' } = {}) {
  const query = search.trim().toLocaleLowerCase();
  return tasks.filter(task => !task.parent_id &&
    (!query || `${task.title} ${task.description}`.toLocaleLowerCase().includes(query)) &&
    (!priority || task.priority === priority) && (!status || task.column_id === Number(status)))
    .sort((a, b) => (sort === 'title' ? a.title.localeCompare(b.title) :
      sort === 'due' ? (a.due_date || '9999').localeCompare(b.due_date || '9999') :
      sort === 'priority' ? priorities[a.priority] - priorities[b.priority] :
      sort === 'updated' ? b.updated_at.localeCompare(a.updated_at) : a.position - b.position) || a.id - b.id);
}

export function taskMove(tasks, task, columnId, direction) {
  const siblings = tasks.filter(t => t.column_id === columnId && (t.parent_id || null) === (task.parent_id || null)).sort((a, b) => a.position - b.position || a.id - b.id);
  const index = siblings.findIndex(t => t.id === task.id);
  if (direction === 'up') return index > 0 ? siblings[index - 1].id : undefined;
  if (direction === 'down') return index >= 0 && index < siblings.length - 1 ? siblings[index + 2]?.id ?? null : undefined;
  return null;
}

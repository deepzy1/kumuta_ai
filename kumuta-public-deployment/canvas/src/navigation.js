const id = value => /^[1-9]\d*$/.test(value || '') && Number.isSafeInteger(Number(value)) ? Number(value) : null;
export function readRoute(hash) {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?');
  const board = /^board\/(\d+)$/.exec(path), params = new URLSearchParams(query);
  if (board && id(board[1])) return { boardId: id(board[1]) };
  return { workspaceId: id(params.get('workspace')), projectId: id(params.get('project')) };
}
export function routeHash(route) {
  if (route.boardId) return `#/board/${route.boardId}`;
  const p = new URLSearchParams();
  if (route.workspaceId) p.set('workspace', route.workspaceId);
  if (route.projectId) p.set('project', route.projectId);
  return `#/library${p.size ? `?${p}` : ''}`;
}
export function visibleBoards(rows, search, sort) {
  return rows.filter(b => b.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
    .sort((a,b) => (sort === 'name' ? a.title.localeCompare(b.title) : sort === 'created' ? b.created_at.localeCompare(a.created_at) : b.updated_at.localeCompare(a.updated_at)) || b.id-a.id);
}

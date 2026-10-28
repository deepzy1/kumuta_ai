const modules = new Set(['chats', 'overview', 'tasks', 'documents', 'data', 'reports', 'study', 'focus', 'notes', 'settings', 'memory', 'canvas']);
const id = value => /^[1-9]\d*$/.test(String(value)) && Number.isSafeInteger(Number(value)) ? Number(value) : null;
export function readRoute(hash = '') {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?');
  const params = new URLSearchParams(query);
  if (path === 'projects') return { screen: 'projects', ...(id(params.get('workspace')) ? { workspaceId: id(params.get('workspace')) } : {}) };
  const match = /^project\/(\d+)\/([a-z]+)$/.exec(path);
  if (match && id(match[1]) && modules.has(match[2])) return { screen: 'project', projectId: id(match[1]), tab: match[2] === 'memory' ? 'settings' : match[2], ...(match[2] === 'memory' ? { settingsSection: 'memory' } : {}), ...(['tasks','notes'].includes(match[2])&&id(params.get('item'))?{itemId:id(params.get('item'))}:{}) };
  return { screen: 'chat', ...(id(params.get('conversation')) ? { conversationId: id(params.get('conversation')) } : {}), ...(id(params.get('project')) ? { projectId: id(params.get('project')) } : {}) };
}
export function routeHash(view) {
  if (view.screen === 'projects') return `#/projects${view.workspaceId ? `?workspace=${view.workspaceId}` : ''}`;
  if (view.screen === 'project') return `#/project/${view.projectId}/${view.tab || 'chats'}${['tasks','notes'].includes(view.tab)&&id(view.itemId)?`?item=${view.itemId}`:''}`;
  const params = new URLSearchParams();
  if (view.conversationId) params.set('conversation', view.conversationId);
  else if (view.projectId) params.set('project', view.projectId);
  return `#/chat${params.size ? `?${params}` : ''}`;
}

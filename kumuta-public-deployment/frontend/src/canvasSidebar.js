export const SIDEBAR_DEFAULT = 360;
export const SIDEBAR_MIN = 300;
export const SIDEBAR_MAX = 640;
export const sidebarKey = id => Number.isSafeInteger(id) && id > 0 ? `kumuta.canvas.sidebar.v1.user.${id}` : null;
export function sidebarPreference(storage, id) {
  try {
    const key = sidebarKey(id), value = key && JSON.parse(storage.getItem(key));
    return { pinned: value?.pinned === true, width: boundedWidth(value?.width) };
  } catch { return {pinned:false, width:SIDEBAR_DEFAULT}; }
}
export function boundedWidth(value) {
  return Number.isFinite(value) ? Math.round(Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, value))) : SIDEBAR_DEFAULT;
}
export function saveSidebarPreference(storage, id, value) {
  const key = sidebarKey(id);
  if (key) try { storage.setItem(key, JSON.stringify({pinned:value.pinned === true, width:boundedWidth(value.width)})); } catch { /* An in-memory preference still works when storage is disabled. */ }
}

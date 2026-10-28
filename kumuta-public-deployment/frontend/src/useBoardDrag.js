// Original pointer sensor. Drag handles reserve touch gestures; card bodies scroll.
import { useEffect, useRef, useState } from 'react';

function destination(event, type, sourceId) {
  const element = document.elementFromPoint(event.clientX, event.clientY);
  const zone = element?.closest('[data-column-zone]');
  if (!zone) return null;
  if (type === 'column') {
    const rect = zone.getBoundingClientRect();
    const before = event.clientX < rect.left + rect.width / 2 ? Number(zone.dataset.columnZone) :
      Number(zone.nextElementSibling?.dataset.columnZone) || null;
    return before === sourceId ? null : { before_id: before, column_id: Number(zone.dataset.columnZone) };
  }
  const card = element.closest('[data-task-card]');
  let before = null;
  if (card) {
    const rect = card.getBoundingClientRect();
    before = event.clientY < rect.top + rect.height / 2 ? Number(card.dataset.taskCard) :
      Number(card.nextElementSibling?.dataset.taskCard) || null;
  }
  if (before === sourceId) return null;
  return { column_id: Number(zone.dataset.columnZone), before_id: before };
}

export default function useBoardDrag(onDrop, disabled) {
  const [drag, setDrag] = useState(null);
  const current = useRef(null), callback = useRef(onDrop), blocked = useRef(disabled);
  callback.current = onDrop; blocked.current = disabled;
  useEffect(() => {
    const cancel = () => { current.current = null; setDrag(null); };
    function move(event) {
      const item = current.current;
      if (!item || event.pointerId !== item.pointerId) return;
      if (!item.active && Math.hypot(event.clientX - item.x, event.clientY - item.y) < 6) return;
      item.active = true;
      const target = destination(event, item.type, item.id);
      item.target = target;
      setDrag({ ...item, x: event.clientX, y: event.clientY });
      const zone = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-column-zone]');
      const board = zone?.closest('.ws-board');
      if (board) {
        const rect = board.getBoundingClientRect();
        if (event.clientX > rect.right - 35) board.scrollLeft += 18;
        if (event.clientX < rect.left + 35) board.scrollLeft -= 18;
      }
      const list = zone?.querySelector('.ws-column-tasks');
      if (list) {
        const rect = list.getBoundingClientRect();
        if (event.clientY > rect.bottom - 35) list.scrollTop += 15;
        if (event.clientY < rect.top + 35) list.scrollTop -= 15;
      }
    }
    function end(event) {
      const item = current.current;
      if (!item || event.pointerId !== item.pointerId) return;
      const target = destination(event, item.type, item.id);
      cancel();
      if (item.active && target && !blocked.current) callback.current(item.type, item.id, target);
    }
    function keyboard(event) { if (event.key === 'Escape') cancel(); }
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', cancel);
    window.addEventListener('blur', cancel);
    window.addEventListener('keydown', keyboard);
    return () => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', cancel); window.removeEventListener('blur', cancel); window.removeEventListener('keydown', keyboard);
    };
  }, []);
  function start(event, type, row) {
    if (blocked.current || event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    current.current = { pointerId: event.pointerId, type, id: row.id, title: row.title || row.name, x: event.clientX, y: event.clientY, active: false };
  }
  return { drag, start };
}

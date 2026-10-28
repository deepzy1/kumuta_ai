import assert from 'node:assert/strict';
import { test } from 'node:test';
import { allPages, loadBoard, taskMove, visibleTasks } from './workspaceData.js';

test('allPages loads beyond one page, preserves query and rejects stalled pagination', async () => {
  const paths = [];
  const rows = await allPages(async path => { paths.push(path); return paths.length === 1 ? { items: [{ id: 1 }], has_more: true } : { items: [{ id: 1 }, { id: 2 }], has_more: false }; }, '/projects/1/notes?q=hello');
  assert.deepEqual(rows.map(r => r.id), [1, 2]);
  assert.equal(paths[1], '/projects/1/notes?q=hello&limit=100&offset=1');
  await assert.rejects(allPages(async () => ({ items: [], has_more: true }), '/projects'), /collection changed/);
});

test('board loading retries inconsistent revisions and rejects continual changes', async () => {
  let snapshots = 0;
  const board = await loadBoard(async path => {
    if (path.endsWith('/columns')) return { items: [{ id: 1 }], board_revision: ++snapshots };
    return { items: [{ id: 7 }], has_more: false, board_revision: 2 };
  }, 1);
  assert.equal(snapshots, 2); assert.equal(board.revision, 2); assert.equal(board.tasks[0].id, 7);
  await assert.rejects(loadBoard(async path => ({ items: [], has_more: false, board_revision: path.endsWith('/columns') ? 1 : 2 }), 1), /board is changing/);
});

test('board loads all task pages before enabling moves', async () => {
  const board = await loadBoard(async path => path.endsWith('/columns') ? { items: [], board_revision: 4 } :
    path.endsWith('offset=0') ? { items: [{ id: 1 }], has_more: true, board_revision: 4 } : { items: [{ id: 2 }], has_more: false, board_revision: 4 }, 1);
  assert.deepEqual(board.tasks.map(t => t.id), [1, 2]);
});

test('filters exclude subtasks and keyboard moves skip hidden children', () => {
  const tasks = [
    { id: 1, column_id: 10, title: 'First', description: 'Research', priority: 'high', position: 1 },
    { id: 2, column_id: 10, parent_id: 1, title: 'Child', position: 2 },
    { id: 3, column_id: 10, title: 'Last', description: '', priority: 'low', position: 3 },
  ];
  assert.deepEqual(visibleTasks(tasks, { search: 'research', priority: 'high' }).map(t => t.id), [1]);
  assert.equal(taskMove(tasks, tasks[2], 10, 'up'), 1);
  assert.equal(taskMove(tasks, tasks[0], 10, 'down'), null);
  assert.equal(taskMove(tasks, tasks[0], 10, 'up'), undefined);
  assert.deepEqual(tasks.map(t => t.id), [1, 2, 3]);
});

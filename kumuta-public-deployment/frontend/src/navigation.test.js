import assert from 'node:assert/strict';
import { readRoute, routeHash } from './navigation.js';
for (const view of [{ screen: 'chat' }, { screen: 'chat', conversationId: 23 }, { screen: 'chat', projectId: 9 }, { screen: 'project', projectId: 7, tab: 'tasks' }, { screen: 'projects' }, { screen: 'projects', workspaceId: 3 }]) assert.deepEqual(readRoute(routeHash(view)), view);
assert.deepEqual(readRoute('#/project/7/memory'), { screen: 'project', projectId: 7, tab: 'settings', settingsSection: 'memory' });
for (const hash of ['#/project/0/tasks', '#/project/4/execute', '#/chat?conversation=-3', '#/chat?project=9007199254740992', '#/chat?project=1e3']) assert.deepEqual(readRoute(hash), { screen: 'chat' });

for(const tab of ['tasks','notes']){const view={screen:'project',projectId:7,tab,itemId:23};assert.deepEqual(readRoute(routeHash(view)),view);assert.equal(readRoute(`#/project/7/${tab}?item=-4`).itemId,undefined);}

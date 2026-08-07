import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const appSource = await readFile(new URL('../App.jsx', import.meta.url), 'utf8');

test('UI contract includes the primary task heading, action, navigation, and sync control', () => {
  assert.match(appSource, /data-uiux-id=["']task-heading["']/);
  assert.match(appSource, />See what Project Manager can do</);
  assert.match(appSource, /Explore the roadmap/);
  assert.match(appSource, /Refresh from GitHub/);
  for (const label of ['Capabilities', 'With / without', 'Roadmap', 'Docs']) {
    assert.match(appSource, new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});

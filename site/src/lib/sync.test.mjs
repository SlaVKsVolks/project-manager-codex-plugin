import test from 'node:test';
import assert from 'node:assert/strict';

import { refreshDataset } from './sync.js';

const baseline = {
  schemaVersion: 1,
  generatedAt: '2026-08-07T12:00:00Z',
  source: { kind: 'local', repositoryPath: 'project-manager', revision: 'unknown' },
  generated: { documentCount: 0, sourceDigest: 'baseline' },
  documents: [],
  capabilities: [],
  roadmap: [],
  comparison: {},
};

test('remote refresh returns a validated GitHub dataset', async () => {
  const remote = { ...baseline, generatedAt: '2026-08-08T09:00:00Z', source: { ...baseline.source, kind: 'github' } };
  const result = await refreshDataset({
    baseline,
    remoteUrl: 'https://example.test/project-manager.json',
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => remote }),
  });

  assert.equal(result.status, 'github-live');
  assert.equal(result.dataset, remote);
  assert.match(result.message, /GitHub/);
});

test('remote refresh falls back to the local snapshot after a network failure', async () => {
  const result = await refreshDataset({
    baseline,
    remoteUrl: 'https://example.test/project-manager.json',
    fetchImpl: async () => {
      throw new Error('offline');
    },
  });

  assert.equal(result.status, 'fallback');
  assert.equal(result.dataset, baseline);
  assert.match(result.message, /local snapshot/i);
});

test('remote refresh rejects malformed data without replacing the baseline', async () => {
  const result = await refreshDataset({
    baseline,
    remoteUrl: 'https://example.test/project-manager.json',
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ schemaVersion: 2 }) }),
  });

  assert.equal(result.status, 'fallback');
  assert.equal(result.dataset, baseline);
  assert.match(result.message, /local snapshot/i);
});

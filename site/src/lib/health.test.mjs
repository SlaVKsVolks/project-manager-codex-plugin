import test from 'node:test';
import assert from 'node:assert/strict';

import { classifyHealthSnapshot, validateHealthSnapshot } from './health.js';


const generatedAt = '2026-08-07T20:00:00Z';
const now = Date.parse('2026-08-07T20:10:00Z');

function snapshot(overrides = {}) {
  const base = {
    schemaVersion: 1,
    generatedAt,
    maxAgeMinutes: 30,
    contentDigest: 'a'.repeat(64),
    source: { revision: 'b'.repeat(40), dirty: false },
    environment: {
      pluginVersion: '0.4.7+codex.20260807151702',
      overallStatus: 'healthy',
      coordinationGate: 'allow',
      heartbeatReady: true,
      freshThreadCallability: 'callable',
      sameLoadedTurnCallability: 'callable',
      blockingFindingCodes: [],
      advisoryFindingCodes: [],
      nonBlockingFindingCodes: [],
    },
    stability: {
      status: 'healthy',
      safeForManagerAutomation: true,
      invariantCount: 10,
      failedInvariantCount: 0,
      failedInvariantCodes: [],
    },
    evidenceBoundary: "Snapshot evidence is not proof of this viewer's current loaded-turn binding.",
  };

  return {
    ...base,
    ...overrides,
    source: { ...base.source, ...(overrides.source || {}) },
    environment: { ...base.environment, ...(overrides.environment || {}) },
    stability: { ...base.stability, ...(overrides.stability || {}) },
  };
}

test('validates and returns a schema-version-one snapshot', () => {
  const value = snapshot();
  assert.equal(validateHealthSnapshot(value), value);
});

test('classifies healthy, degraded, unhealthy, stale, and unavailable states', () => {
  assert.equal(classifyHealthSnapshot(snapshot(), now).label, 'HEALTHY');
  assert.equal(
    classifyHealthSnapshot(snapshot({ environment: { overallStatus: 'degraded' } }), now).label,
    'DEGRADED',
  );
  assert.equal(
    classifyHealthSnapshot(snapshot({ environment: { overallStatus: 'unhealthy' } }), now).label,
    'UNHEALTHY',
  );
  assert.equal(
    classifyHealthSnapshot(snapshot({ generatedAt: '2026-08-07T18:00:00Z' }), now).label,
    'STALE',
  );
  assert.equal(classifyHealthSnapshot(null, now).label, 'UNAVAILABLE');
});

test('critical coordination fields can never classify as healthy', () => {
  const cases = [
    snapshot({ environment: { coordinationGate: 'block' } }),
    snapshot({ environment: { heartbeatReady: false } }),
    snapshot({ stability: { safeForManagerAutomation: false } }),
    snapshot({ stability: { failedInvariantCount: 1, failedInvariantCodes: ['health_gate'] } }),
  ];

  for (const value of cases) {
    assert.notEqual(classifyHealthSnapshot(value, now).label, 'HEALTHY');
  }
});

test('reports age and freshness ceiling without allowing future clocks to go negative', () => {
  assert.equal(classifyHealthSnapshot(snapshot(), now).ageMinutes, 10);
  assert.equal(classifyHealthSnapshot(snapshot(), now).maxAgeMinutes, 30);
  assert.equal(
    classifyHealthSnapshot(snapshot({ generatedAt: '2026-08-07T20:20:00Z' }), now).ageMinutes,
    0,
  );
});

test('malformed snapshots become unavailable instead of throwing through render', () => {
  const malformed = snapshot({ environment: { heartbeatReady: 'yes' } });
  const result = classifyHealthSnapshot(malformed, now);

  assert.equal(result.label, 'UNAVAILABLE');
  assert.equal(result.stale, false);
  assert.match(result.explanation, /unavailable/i);
});

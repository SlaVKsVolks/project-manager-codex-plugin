const HEALTH_STATUSES = new Set(['healthy', 'degraded', 'unhealthy', 'unknown']);
const COORDINATION_GATES = new Set(['allow', 'block', 'block_host_state', 'unknown']);
const CALLABILITY = new Set(['callable', 'not_callable', 'unknown']);
const CODE_PATTERN = /^[a-z0-9][a-z0-9_.:-]{0,79}$/;
const VERSION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9.+-]{0,95}$/;
const DIGEST_PATTERN = /^[0-9a-f]{64}$/;
const REVISION_PATTERN = /^(?:unknown|[0-9a-f]{40})$/;

function requireObject(value, field) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(`${field} must be an object`);
  }
  return value;
}

function requireBoolean(value, field) {
  if (typeof value !== 'boolean') throw new TypeError(`${field} must be a boolean`);
  return value;
}

function requireInteger(value, field, { positive = false } = {}) {
  if (!Number.isInteger(value) || value < (positive ? 1 : 0)) {
    throw new TypeError(`${field} must be ${positive ? 'a positive' : 'a non-negative'} integer`);
  }
  return value;
}

function requireEnum(value, allowed, field) {
  if (!allowed.has(value)) throw new TypeError(`${field} is invalid`);
  return value;
}

function requirePattern(value, pattern, field) {
  if (typeof value !== 'string' || !pattern.test(value)) throw new TypeError(`${field} is invalid`);
  return value;
}

function requireCodes(value, field) {
  if (!Array.isArray(value) || value.some((code) => typeof code !== 'string' || !CODE_PATTERN.test(code))) {
    throw new TypeError(`${field} must contain safe finding codes`);
  }
  return value;
}

export function validateHealthSnapshot(value) {
  const snapshot = requireObject(value, 'snapshot');
  if (snapshot.schemaVersion !== 1) throw new TypeError('schemaVersion must be 1');
  if (typeof snapshot.generatedAt !== 'string' || !Number.isFinite(Date.parse(snapshot.generatedAt))) {
    throw new TypeError('generatedAt must be a timestamp');
  }
  requireInteger(snapshot.maxAgeMinutes, 'maxAgeMinutes', { positive: true });
  requirePattern(snapshot.contentDigest, DIGEST_PATTERN, 'contentDigest');

  const source = requireObject(snapshot.source, 'source');
  requirePattern(source.revision, REVISION_PATTERN, 'source.revision');
  requireBoolean(source.dirty, 'source.dirty');

  const environment = requireObject(snapshot.environment, 'environment');
  requirePattern(environment.pluginVersion, VERSION_PATTERN, 'environment.pluginVersion');
  requireEnum(environment.overallStatus, HEALTH_STATUSES, 'environment.overallStatus');
  requireEnum(environment.coordinationGate, COORDINATION_GATES, 'environment.coordinationGate');
  requireBoolean(environment.heartbeatReady, 'environment.heartbeatReady');
  requireEnum(environment.freshThreadCallability, CALLABILITY, 'environment.freshThreadCallability');
  requireEnum(environment.sameLoadedTurnCallability, CALLABILITY, 'environment.sameLoadedTurnCallability');
  requireCodes(environment.blockingFindingCodes, 'environment.blockingFindingCodes');
  requireCodes(environment.advisoryFindingCodes, 'environment.advisoryFindingCodes');
  requireCodes(environment.nonBlockingFindingCodes, 'environment.nonBlockingFindingCodes');

  const stability = requireObject(snapshot.stability, 'stability');
  requireEnum(stability.status, HEALTH_STATUSES, 'stability.status');
  requireBoolean(stability.safeForManagerAutomation, 'stability.safeForManagerAutomation');
  requireInteger(stability.invariantCount, 'stability.invariantCount');
  requireInteger(stability.failedInvariantCount, 'stability.failedInvariantCount');
  requireCodes(stability.failedInvariantCodes, 'stability.failedInvariantCodes');
  if (stability.failedInvariantCount !== stability.failedInvariantCodes.length) {
    throw new TypeError('stability failed invariant fields disagree');
  }
  if (typeof snapshot.evidenceBoundary !== 'string' || !snapshot.evidenceBoundary.trim()) {
    throw new TypeError('evidenceBoundary is required');
  }
  return snapshot;
}

const unavailable = (explanation = 'Health snapshot is unavailable or malformed.') => ({
  label: 'UNAVAILABLE',
  tone: 'unavailable',
  stale: false,
  ageMinutes: null,
  maxAgeMinutes: null,
  explanation,
  snapshot: null,
});

export function classifyHealthSnapshot(value, nowMs = Date.now()) {
  let snapshot;
  try {
    snapshot = validateHealthSnapshot(value);
  } catch {
    return unavailable();
  }

  const generatedMs = Date.parse(snapshot.generatedAt);
  const currentMs = Number.isFinite(nowMs) ? nowMs : Date.now();
  const ageMinutes = Math.max(0, Math.floor((currentMs - generatedMs) / 60_000));
  const base = {
    stale: false,
    ageMinutes,
    maxAgeMinutes: snapshot.maxAgeMinutes,
    snapshot,
  };

  if (ageMinutes > snapshot.maxAgeMinutes) {
    return {
      ...base,
      label: 'STALE',
      tone: 'stale',
      stale: true,
      explanation: `Snapshot age exceeds the ${snapshot.maxAgeMinutes}-minute freshness ceiling.`,
    };
  }

  const { environment, stability } = snapshot;
  const isUnhealthy = environment.overallStatus === 'unhealthy'
    || stability.status === 'unhealthy'
    || environment.coordinationGate === 'block'
    || environment.coordinationGate === 'block_host_state'
    || environment.blockingFindingCodes.length > 0;
  if (isUnhealthy) {
    return {
      ...base,
      label: 'UNHEALTHY',
      tone: 'unhealthy',
      explanation: 'A critical health, coordination, or stability gate is blocked.',
    };
  }

  const isHealthy = environment.overallStatus === 'healthy'
    && environment.coordinationGate === 'allow'
    && environment.heartbeatReady === true
    && stability.status === 'healthy'
    && stability.safeForManagerAutomation === true
    && stability.failedInvariantCount === 0;
  if (isHealthy) {
    return {
      ...base,
      label: 'HEALTHY',
      tone: 'healthy',
      explanation: 'Critical environment, heartbeat, coordination, and stability gates agree.',
    };
  }

  return {
    ...base,
    label: 'DEGRADED',
    tone: 'degraded',
    explanation: 'The snapshot is readable, but one or more readiness signals need attention.',
  };
}

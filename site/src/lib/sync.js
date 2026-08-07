const REQUIRED_ARRAYS = ['documents', 'capabilities', 'roadmap'];

export function validateDataset(dataset) {
  if (!dataset || typeof dataset !== 'object' || Array.isArray(dataset)) {
    throw new Error('Roadmap dataset must be an object');
  }
  if (dataset.schemaVersion !== 1) {
    throw new Error('Roadmap dataset schema version is unsupported');
  }
  for (const key of REQUIRED_ARRAYS) {
    if (!Array.isArray(dataset[key])) {
      throw new Error(`Roadmap dataset is missing ${key}`);
    }
  }
  if (!dataset.source || typeof dataset.source !== 'object') {
    throw new Error('Roadmap dataset is missing source metadata');
  }
  return dataset;
}

export async function refreshDataset({
  baseline,
  remoteUrl,
  fetchImpl = globalThis.fetch,
  timeoutMs = 10_000,
}) {
  const fetchedAt = new Date().toISOString();
  validateDataset(baseline);

  if (!remoteUrl || typeof fetchImpl !== 'function') {
    return {
      dataset: baseline,
      status: 'fallback',
      message: 'GitHub refresh is not configured; showing the local snapshot.',
      fetchedAt,
    };
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetchImpl(remoteUrl, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
    if (!response?.ok) {
      throw new Error(`GitHub returned HTTP ${response?.status ?? 'unknown'}`);
    }
    const remoteDataset = await response.json();
    validateDataset(remoteDataset);
    return {
      dataset: remoteDataset,
      status: 'github-live',
      message: `GitHub snapshot refreshed at ${new Date(fetchedAt).toLocaleTimeString()}.`,
      fetchedAt,
    };
  } catch (error) {
    const reason = error?.name === 'AbortError' ? 'timed out' : 'was unavailable';
    return {
      dataset: baseline,
      status: 'fallback',
      message: `GitHub refresh ${reason}; showing the local snapshot.`,
      fetchedAt,
    };
  } finally {
    clearTimeout(timeoutId);
  }
}

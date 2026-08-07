import { useEffect, useMemo, useState } from 'react';

import baselineDataset from './data/project-manager.json';
import healthSnapshot from './data/project-manager-health.json';
import { REMOTE_DATA_URL } from './lib/config.js';
import { classifyHealthSnapshot } from './lib/health.js';
import { renderMarkdown } from './lib/markdown.js';
import { refreshDataset } from './lib/sync.js';

const STATUS_LABELS = {
  'local-snapshot': { label: 'LOCAL SNAPSHOT', tone: 'cyan', description: 'Bundled from the last local sync.' },
  refreshing: { label: 'SYNCING', tone: 'amber', description: 'Checking the configured GitHub snapshot.' },
  'github-live': { label: 'GITHUB LIVE', tone: 'cyan', description: 'Showing the validated remote snapshot.' },
  fallback: { label: 'FALLBACK', tone: 'amber', description: 'Remote refresh failed; local snapshot remains active.' },
};

const NAV_ITEMS = [
  ['health', 'Health'],
  ['capabilities', 'Capabilities'],
  ['comparison', 'With / without'],
  ['roadmap', 'Roadmap'],
  ['docs', 'Docs'],
];

function formatDate(value) {
  if (!value) return 'Open horizon';
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(`${value}T12:00:00Z`));
}

function formatDateTime(value) {
  if (!value) return 'Unknown';
  return new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function formatRevision(value) {
  if (!value || value === 'unknown') return 'unknown';
  return value.slice(0, 8);
}

function formatSignal(value) {
  if (value === true) return 'Ready';
  if (value === false) return 'Blocked';
  if (!value) return 'Unknown';
  return String(value).replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatSnapshotAge(classification) {
  if (classification.ageMinutes === null) return 'No valid snapshot';
  if (classification.ageMinutes === 0) return 'Less than one minute old';
  return `${classification.ageMinutes} min old`;
}

function healthHeadline(classification) {
  return {
    HEALTHY: 'Ready for bounded coordination.',
    DEGRADED: 'Coordination needs attention.',
    UNHEALTHY: 'Coordination is blocked.',
    STALE: 'The health snapshot needs refresh.',
    UNAVAILABLE: 'Health evidence is unavailable.',
  }[classification.label];
}

function Icon({ name, size = 16 }) {
  const paths = {
    arrow: <path d="M4 12 12 4m0 0H6m6 0v6" />,
    chevron: <path d="m6 9 3 3 3-3" />,
    refresh: <path d="M13.5 5.5A5.5 5.5 0 1 0 15 10M13.5 5.5V2.7m0 2.8h-2.8" />,
    search: <><circle cx="7.5" cy="7.5" r="4.5" /><path d="m11 11 3.5 3.5" /></>,
    check: <path d="m4 8.5 2.5 2.5L12.5 5" />,
    dot: <circle cx="8" cy="8" r="3" fill="currentColor" stroke="none" />,
  };
  return (
    <svg aria-hidden="true" className="icon" width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

function StatusMark({ status, compact = false }) {
  const meta = STATUS_LABELS[status] || STATUS_LABELS['local-snapshot'];
  return (
    <span className={`status-mark status-mark--${meta.tone} ${compact ? 'status-mark--compact' : ''}`}>
      <Icon name="dot" size={14} />
      <span>{meta.label}</span>
    </span>
  );
}

function HealthStatusMark({ classification, compact = false }) {
  return (
    <span className={`health-status health-status--${classification.tone} ${compact ? 'health-status--compact' : ''}`}>
      <Icon name="dot" size={14} />
      <span>{classification.label}</span>
    </span>
  );
}

function FindingCodes({ codes = [], emptyLabel }) {
  if (!codes.length) return <span className="finding-empty">{emptyLabel}</span>;
  return <ul className="finding-codes">{codes.map((code) => <li key={code}><code>{code}</code></li>)}</ul>;
}

function SourceLinks({ ids = [], documentById, onSelect }) {
  const links = ids.map((id) => documentById.get(id)).filter(Boolean);
  if (!links.length) return <span className="muted-copy">No linked document yet</span>;
  return (
    <div className="source-links" aria-label="Source documents">
      {links.slice(0, 3).map((document) => (
        <button key={document.id} className="source-link" type="button" onClick={() => onSelect(document.id)}>
          {document.title}
          <Icon name="arrow" size={13} />
        </button>
      ))}
      {links.length > 3 && <span className="source-overflow">+{links.length - 3} more</span>}
    </div>
  );
}

function App() {
  const [dataset, setDataset] = useState(baselineDataset);
  const [syncState, setSyncState] = useState({
    status: 'local-snapshot',
    message: 'Bundled from the last local sync.',
    fetchedAt: null,
  });
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [query, setQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [evidenceFilter, setEvidenceFilter] = useState('all');
  const [selectedDocumentId, setSelectedDocumentId] = useState(baselineDataset.documents[0]?.id ?? null);
  const [healthClock, setHealthClock] = useState(() => Date.now());

  const documentById = useMemo(
    () => new Map(dataset.documents.map((document) => [document.id, document])),
    [dataset.documents],
  );

  const categories = useMemo(
    () => [...new Set(dataset.documents.map((document) => document.category))].sort(),
    [dataset.documents],
  );

  const filteredDocuments = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return dataset.documents.filter((document) => {
      const matchesQuery = !normalizedQuery || [document.title, document.sourcePath, document.body].some((value) => value.toLowerCase().includes(normalizedQuery));
      const matchesCategory = categoryFilter === 'all' || document.category === categoryFilter;
      const matchesEvidence = evidenceFilter === 'all' || (document.evidence || 'repository') === evidenceFilter;
      return matchesQuery && matchesCategory && matchesEvidence;
    });
  }, [categoryFilter, dataset.documents, evidenceFilter, query]);

  const selectedDocument = documentById.get(selectedDocumentId) || filteredDocuments[0] || dataset.documents[0];
  const statusMeta = STATUS_LABELS[syncState.status] || STATUS_LABELS['local-snapshot'];
  const healthState = useMemo(
    () => classifyHealthSnapshot(healthSnapshot, healthClock),
    [healthClock],
  );
  const health = healthState.snapshot;

  useEffect(() => {
    let cancelled = false;
    setSyncState((current) => ({ ...current, status: 'refreshing', message: 'Checking the configured GitHub snapshot.' }));
    refreshDataset({ baseline: baselineDataset, remoteUrl: REMOTE_DATA_URL }).then((result) => {
      if (cancelled) return;
      setDataset(result.dataset);
      setSyncState(result);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setHealthClock(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!selectedDocument || !filteredDocuments.length) return;
    if (!filteredDocuments.some((document) => document.id === selectedDocument.id)) {
      setSelectedDocumentId(filteredDocuments[0].id);
    }
  }, [filteredDocuments, selectedDocument]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setSyncState((current) => ({ ...current, status: 'refreshing', message: 'Checking the configured GitHub snapshot.' }));
    const result = await refreshDataset({ baseline: baselineDataset, remoteUrl: REMOTE_DATA_URL });
    setDataset(result.dataset);
    setSyncState(result);
    setIsRefreshing(false);
  };

  const jumpTo = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const selectDocument = (id) => {
    setSelectedDocumentId(id);
    window.history.replaceState(null, '', '#docs');
    jumpTo('docs');
  };

  return (
    <div className="site-shell">
      <header className="topbar">
        <a className="brand" href="#overview" aria-label="Project Manager overview">
          <span className="brand-mark">PM</span>
          <span className="brand-copy"><strong>Project Manager</strong><small>Codex plugin</small></span>
        </a>
        <nav className="main-nav" aria-label="Primary navigation">
          {NAV_ITEMS.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
        </nav>
        <button className="sync-control" type="button" onClick={handleRefresh} disabled={isRefreshing}>
          <StatusMark status={isRefreshing ? 'refreshing' : syncState.status} compact />
          <span className="sync-control-label">{isRefreshing ? 'Refreshing' : 'Refresh'}</span>
          <Icon name="refresh" size={15} />
        </button>
      </header>

      <main>
        <section className="hero-section section-anchor" id="overview">
          <div className="hero-copy">
            <h1 data-uiux-id="task-heading">Review Project Manager health</h1>
            <p className="hero-kicker">See what Project Manager can do</p>
            <p className="hero-lede">Health, coordination, heartbeat, and stability evidence must agree before Codex work is treated as safe. This view shows what blocks the next move when they do not.</p>
            <div className="hero-actions">
              <a className="primary-action" data-uiux-id="primary-action" data-uiux-action-entry="direct-action" href="#health">Review environment health <Icon name="arrow" size={16} /></a>
              <a className="secondary-action" href="#roadmap">Explore the roadmap <Icon name="arrow" size={16} /></a>
            </div>
            <div className="hero-facts" aria-label="Snapshot facts">
              <div><strong>{healthState.label}</strong><span>environment</span></div>
              <div><strong>{health?.stability.invariantCount ?? '—'}</strong><span>stability checks</span></div>
              <div><strong>{formatSnapshotAge(healthState)}</strong><span>snapshot age</span></div>
            </div>
          </div>
          <div className="hero-console" aria-label="Project Manager operating picture">
            <div className="console-topline"><span>PROJECT MANAGER / HEALTH VIEW</span><HealthStatusMark classification={healthState} compact /></div>
            <div className="console-title">{healthHeadline(healthState)}</div>
            <div className="console-flow">
              <div className="console-step"><span className="console-step-index">01</span><span>Gate · {formatSignal(health?.environment.coordinationGate)}</span></div>
              <div className="console-step"><span className="console-step-index">02</span><span>Heartbeat · {formatSignal(health?.environment.heartbeatReady)}</span></div>
              <div className="console-step"><span className="console-step-index">03</span><span>Stability · {formatSignal(health?.stability.status)}</span></div>
              <div className="console-step"><span className="console-step-index">04</span><span>Loaded turn · {formatSignal(health?.environment.sameLoadedTurnCallability)}</span></div>
            </div>
            <div className="console-note"><span className="signal-line" /><span>{health?.evidenceBoundary || 'No valid health evidence is available.'}</span></div>
            <div className="console-footer"><span>PLUGIN</span><strong>{health?.environment.pluginVersion || 'unknown'}</strong><span>CAPTURED</span><strong>{formatDateTime(health?.generatedAt)}</strong></div>
          </div>
        </section>

        <section className={`content-section health-section health-section--${healthState.tone} section-anchor`} id="health" data-uiux-id="environment-health" aria-labelledby="environment-health-heading">
          <div className="health-layout">
            <div className="health-primary">
              <p className="section-index">01 / ENVIRONMENT HEALTH</p>
              <div className="health-title-row">
                <div>
                  <h2 id="environment-health-heading">Can Codex coordinate safely?</h2>
                  <p>{healthState.explanation}</p>
                </div>
                <div className="health-state-summary" role="status" aria-live="polite">
                  <HealthStatusMark classification={healthState} />
                  {health?.generatedAt
                    ? <time dateTime={health.generatedAt}>{formatSnapshotAge(healthState)} · ceiling {healthState.maxAgeMinutes} min</time>
                    : <span>No valid capture time</span>}
                </div>
              </div>

              {health ? <>
                <dl className="health-evidence-grid" data-uiux-id="health-evidence-grid">
                  <div><dt>Environment</dt><dd>{formatSignal(health.environment.overallStatus)}</dd></div>
                  <div><dt>Coordination gate</dt><dd>{formatSignal(health.environment.coordinationGate)}</dd></div>
                  <div><dt>Heartbeat</dt><dd>{formatSignal(health.environment.heartbeatReady)}</dd></div>
                  <div><dt>Automation safety</dt><dd>{formatSignal(health.stability.safeForManagerAutomation)}</dd></div>
                  <div><dt>Fresh thread</dt><dd>{formatSignal(health.environment.freshThreadCallability)}</dd></div>
                  <div><dt>Current loaded turn</dt><dd>{formatSignal(health.environment.sameLoadedTurnCallability)}</dd></div>
                  <div><dt>Stability invariants</dt><dd>{health.stability.invariantCount - health.stability.failedInvariantCount} / {health.stability.invariantCount} passing</dd></div>
                  <div><dt>Source revision</dt><dd>{formatRevision(health.source.revision)}{health.source.dirty ? ' · local changes' : ' · clean'}</dd></div>
                </dl>

                <div className="health-findings">
                  <div><span className="signal-kicker">BLOCKING FINDINGS</span><FindingCodes codes={health.environment.blockingFindingCodes} emptyLabel="None reported" /></div>
                  <div><span className="signal-kicker">ADVISORIES</span><FindingCodes codes={[...health.environment.advisoryFindingCodes, ...health.environment.nonBlockingFindingCodes]} emptyLabel="None reported" /></div>
                  <div><span className="signal-kicker">FAILED INVARIANTS</span><FindingCodes codes={health.stability.failedInvariantCodes} emptyLabel="None reported" /></div>
                </div>
              </> : <div className="health-unavailable"><strong>Health evidence unavailable.</strong><span>Regenerate and publish a validated local snapshot; the documentation view remains available.</span></div>}
            </div>

            <aside className="health-boundary" aria-label="Health evidence boundary">
              <span className="signal-kicker">EVIDENCE BOUNDARY</span>
              <p>{health?.evidenceBoundary || 'The current page has no valid environment-health snapshot.'}</p>
              <dl>
                <div><dt>Snapshot digest</dt><dd>{health?.contentDigest.slice(0, 12) || 'unavailable'}</dd></div>
                <div><dt>Documentation</dt><dd>{statusMeta.description}</dd></div>
              </dl>
            </aside>
          </div>
        </section>

        <section className="content-section section-anchor" id="capabilities" data-uiux-id="capabilities">
          <div className="section-heading-row">
            <div><p className="section-index">02 / CAPABILITY MAP</p><h2>Make the work legible.</h2></div>
            <p className="section-summary">The plugin turns operational uncertainty into named gates, bounded actions, and source-linked evidence. Each family is useful on its own; together they keep a manager thread honest.</p>
          </div>
          <div className="capability-list">
            {dataset.capabilities.map((capability, index) => (
              <article className="capability-row" key={capability.id}>
                <div className="capability-number">{String(index + 1).padStart(2, '0')}</div>
                <div className="capability-main"><h3>{capability.label}</h3><p>{capability.summary}</p><SourceLinks ids={capability.sourceIds} documentById={documentById} onSelect={selectDocument} /></div>
                <div className="capability-signal"><span className="signal-kicker">OPERATING SIGNAL</span><p>{capability.signal}</p><span className="evidence-limit">Evidence ceiling: {capability.evidenceCeiling}</span></div>
              </article>
            ))}
          </div>
        </section>

        <section className="content-section comparison-section section-anchor" id="comparison">
          <div className="section-heading-row">
            <div><p className="section-index">03 / WORKFLOW DIFFERENCE</p><h2>With a trail. Or without one.</h2></div>
            <p className="section-summary">This is a workflow comparison, not an uptime promise. Project Manager helps the work remain inspectable when the environment is degraded, stale, or mid-recovery.</p>
          </div>
          <div className="comparison-grid">
            {[['withPlugin', 'with-plugin'], ['withoutPlugin', 'without-plugin']].map(([key, tone]) => {
              const workflow = dataset.comparison[key];
              return <article className={`workflow-panel workflow-panel--${tone}`} key={key}>
                <div className="workflow-heading"><span className="workflow-marker" /><div><h3>{workflow.label}</h3><p>{workflow.summary}</p></div></div>
                <ol className="workflow-steps">
                  {workflow.steps.map((step, index) => <li key={step}><span>{String(index + 1).padStart(2, '0')}</span><strong>{step}</strong></li>)}
                </ol>
              </article>;
            })}
          </div>
          <div className="limitation-strip"><span className="signal-kicker">KEEP THE CLAIMS CLEAN</span>{dataset.comparison.limitations?.map((limitation) => <p key={limitation}><Icon name="dot" size={13} />{limitation}</p>)}</div>
        </section>

        <section className="content-section roadmap-section section-anchor" id="roadmap">
          <div className="section-heading-row">
            <div><p className="section-index">04 / DEVELOPMENT ROADMAP</p><h2>Progress with receipts.</h2></div>
            <p className="section-summary">Roadmap phases are tied to dated decisions, bugs, migrations, plans, and specifications. “Complete” means the repository records the work—not that every runtime or production claim is proven.</p>
          </div>
          <ol className="roadmap-timeline">
            {dataset.roadmap.map((item, index) => (
              <li className={`roadmap-item roadmap-item--${item.status}`} key={item.id}>
                <div className="roadmap-marker"><span>{String(index + 1).padStart(2, '0')}</span></div>
                <div className="roadmap-card">
                  <div className="roadmap-meta"><span className={`roadmap-status roadmap-status--${item.status}`}>{item.status.replace('-', ' ')}</span><span>{item.phase}</span><span>{formatDate(item.dateFrom)}{item.dateTo ? ` — ${formatDate(item.dateTo)}` : ' — forward'}</span></div>
                  <h3>{item.title}</h3><p>{item.outcome}</p>
                  <div className="criteria-row"><div><span className="signal-kicker">ACCEPTANCE THREAD</span><ul>{item.criteria.map((criterion) => <li key={criterion}><Icon name="check" size={14} />{criterion}</li>)}</ul></div><div className="roadmap-evidence"><span className="signal-kicker">EVIDENCE CEILING</span><p>{item.evidenceCeiling}</p><SourceLinks ids={item.sourceIds} documentById={documentById} onSelect={selectDocument} /></div></div>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="content-section docs-section section-anchor" id="docs">
          <div className="section-heading-row">
            <div><p className="section-index">05 / DOCUMENTATION EXPLORER</p><h2>Every decision, in context.</h2></div>
            <p className="section-summary">Search the local snapshot by title, path, or body. Select a record to read the Markdown in full, with provenance kept beside the content.</p>
          </div>
          <div className="docs-layout">
            <aside className="docs-index-panel" aria-label="Documentation index">
              <div className="docs-controls">
                <label className="search-field"><span className="sr-only">Search documentation</span><Icon name="search" size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${dataset.documents.length} documents`} /></label>
                <div className="filter-row"><label><span className="sr-only">Filter by category</span><select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}><option value="all">All categories</option>{categories.map((category) => <option key={category} value={category}>{category}</option>)}</select></label><label><span className="sr-only">Filter by evidence</span><select value={evidenceFilter} onChange={(event) => setEvidenceFilter(event.target.value)}><option value="all">All evidence</option><option value="repository">Repository</option><option value="generated">Generated</option></select></label></div>
                <p className="results-count" aria-live="polite">{filteredDocuments.length} of {dataset.documents.length} documents</p>
              </div>
              <div className="document-list" role="listbox" aria-label="Documents">
                {filteredDocuments.map((document) => <button key={document.id} className={`document-row ${selectedDocument?.id === document.id ? 'document-row--selected' : ''}`} type="button" role="option" aria-selected={selectedDocument?.id === document.id} onClick={() => setSelectedDocumentId(document.id)}><span className="document-row-title">{document.title}</span><span className="document-row-meta">{document.category} · {document.date || 'undated'}</span></button>)}
                {!filteredDocuments.length && <div className="empty-state"><strong>No documents match.</strong><span>Try a broader search or clear a filter.</span></div>}
              </div>
            </aside>
            <article className="document-detail" aria-live="polite">
              {selectedDocument ? <>
                <div className="document-detail-top"><div><span className="document-category">{selectedDocument.category} / {selectedDocument.evidence || 'repository'}</span><h3>{selectedDocument.title}</h3><p className="document-path">{selectedDocument.sourcePath}</p></div><span className="document-word-count">{selectedDocument.wordCount} words</span></div>
                <div className="document-body" dangerouslySetInnerHTML={{ __html: renderMarkdown(selectedDocument.body) }} />
              </> : <div className="empty-state"><strong>Select a document.</strong><span>The local snapshot is ready.</span></div>}
            </article>
          </div>
        </section>

        <section className="content-section sync-section section-anchor" id="sync">
          <div className="sync-panel">
            <div className="sync-panel-copy"><p className="section-index">06 / SYNC CENTER</p><h2>Local truth, remote reach.</h2><p>The hosted page cannot watch your Windows disk. Run the local sync command when docs change; the next published snapshot carries the revision here. GitHub refresh is optional and always falls back safely.</p><button className="primary-action" type="button" onClick={handleRefresh} disabled={isRefreshing}><Icon name="refresh" size={16} />{isRefreshing ? 'Refreshing…' : 'Refresh from GitHub'}</button></div>
            <div className="sync-panel-data"><div className="sync-state-header"><StatusMark status={syncState.status} /><span className="sync-message" aria-live="polite">{syncState.message}</span></div><dl className="sync-facts"><div><dt>LOCAL SNAPSHOT</dt><dd>{formatDateTime(dataset.generatedAt)}</dd></div><div><dt>REVISION</dt><dd>{formatRevision(dataset.source.revision)}</dd></div><div><dt>DOCUMENTS</dt><dd>{dataset.generated.documentCount}</dd></div><div><dt>REMOTE CHECK</dt><dd>{syncState.fetchedAt ? formatDateTime(syncState.fetchedAt) : 'Not yet checked'}</dd></div></dl><div className="sync-command"><span className="signal-kicker">RUN LOCALLY</span><code>pwsh -NoProfile -File .\scripts\Sync-ProjectManagerRoadmapSite.ps1</code></div></div>
          </div>
        </section>
      </main>

      <footer className="site-footer"><span>Project Manager / source-backed roadmap</span><span>Local snapshot: {dataset.generated.documentCount} documents · {formatRevision(dataset.source.revision)}</span><a href="#overview">Back to top <Icon name="arrow" size={13} /></a></footer>
    </div>
  );
}

export default App;

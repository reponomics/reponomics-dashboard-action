export function installTrustPlaybook(context) {
  const document = context.document;
  const currentPayload = (...args) => context.currentPayload(...args);
  const escapeHtml = (...args) => context.escapeHtml(...args);
  const formatNumber = (...args) => context.formatNumber(...args);
  const getSelectedWindow = (...args) => context.getSelectedWindow(...args);
  const getShortName = (...args) => context.getShortName(...args);
  const getVisibleRepos = (...args) => context.getVisibleRepos(...args);

  const TRUST_LINKS = {
    scorecard: 'https://github.com/ossf/scorecard',
    scorecardChecks: 'https://github.com/ossf/scorecard/blob/main/docs/checks.md',
    osv: 'https://google.github.io/osv-scanner/',
    zizmor: 'https://docs.zizmor.sh/',
    actionsSecurity: 'https://docs.github.com/en/actions/reference/security/secure-use',
    slsa: 'https://slsa.dev/spec/v1.2/levels',
    attestations: 'https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations',
    soc: 'https://www.aicpa-cima.com/resources/landing/system-and-organization-controls-soc-suite-of-services',
    dependabot: 'https://docs.github.com/en/code-security/dependabot/dependabot-alerts/configuring-dependabot-alerts',
    codeql: 'https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning-with-codeql',
    secretScanning: 'https://docs.github.com/en/code-security/secret-scanning/about-secret-scanning',
  };

  const READINESS_KEYS = [
    'has_readme',
    'has_license',
    'has_contributing',
    'has_issue_template',
    'has_pull_request_template',
    'has_code_of_conduct',
  ];

  function asBool(value) {
    if (value === true || value === false) return value;
    const normalized = String(value ?? '').trim().toLowerCase();
    if (!normalized) return null;
    if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
    if (['false', '0', 'no', 'off'].includes(normalized)) return false;
    return null;
  }

  function missingReadinessCount(repo) {
    const community = repo?.community || {};
    return READINESS_KEYS.filter((key) => asBool(community[key]) === false).length;
  }

  function downstreamDelta(repo) {
    return Number(repo?.stars_delta || 0) + Number(repo?.subscribers_delta || 0) + Number(repo?.forks_delta || 0);
  }

  function repoTrustPriority(repo) {
    const health = Number(repo?.community?.health_percentage);
    const healthGap = Number.isFinite(health) ? Math.max(0, 100 - health) : 12;
    return (
      Number(repo?.clones || 0) * 2
      + Number(repo?.clone_uniques || 0) * 3
      + Math.max(0, downstreamDelta(repo)) * 18
      + missingReadinessCount(repo) * 16
      + healthGap * 0.35
    );
  }

  function pickFocusRepo(repos) {
    return (repos || [])
      .slice()
      .sort((a, b) => repoTrustPriority(b) - repoTrustPriority(a) || String(a.name || '').localeCompare(String(b.name || '')))[0] || null;
  }

  function githubRepoUrl(repo) {
    return repo?.name ? `github.com/${repo.name}` : 'github.com/OWNER/REPO';
  }

  function focusCue(repo) {
    if (!repo?.name) return 'Try on the repo clone';
    const shortName = getShortName(repo.name);
    const missing = missingReadinessCount(repo);
    const downstream = downstreamDelta(repo);
    if (downstream > 0) return `${shortName} has new downstream interest`;
    if (Number(repo.clones || 0) > 0) return `${shortName} has clone activity`;
    if (missing > 0) return `${shortName} has visible setup gaps`;
    return `Start with ${shortName}`;
  }

  function visibleWindowLabel() {
    const selected = getSelectedWindow();
    return selected === 'all' ? 'all retained data' : `the ${selected}d window`;
  }

  function buildTrustPlaybookItems(repos, payload) {
    const focusRepo = pickFocusRepo(repos);
    const repoUrl = githubRepoUrl(focusRepo);
    const profileLabel = payload?.portfolio_profile?.label || 'published repo set';
    return [
      {
        key: 'polish',
        level: 'Level 1',
        label: 'Professional surface',
        title: 'Make the repo easy to trust at first glance',
        summary: `${focusCue(focusRepo)}. Before deeper security work, make the public surface legible: clear install path, license, security contact, useful issue intake, and visible release notes.`,
        command: '',
        links: [
          ['Dependabot', TRUST_LINKS.dependabot],
          ['Secret scanning', TRUST_LINKS.secretScanning],
        ],
      },
      {
        key: 'scorecard',
        level: 'Level 2',
        label: 'Security baseline',
        title: 'Run a Scorecard baseline',
        summary: `Scorecard is the broad first pass: token permissions, pinned dependencies, branch protection, dependency updates, security policy, CI tests, and other project-hygiene checks.`,
        command: `scorecard --repo=${repoUrl} --show-details`,
        links: [
          ['Scorecard', TRUST_LINKS.scorecard],
          ['Checks', TRUST_LINKS.scorecardChecks],
        ],
      },
      {
        key: 'osv',
        level: 'Level 3',
        label: 'Local diagnostics',
        title: 'Scan dependencies and workflow risk locally',
        summary: 'From a fresh clone, combine dependency scanning with workflow review. This catches known vulnerable packages and risky Actions patterns without enrolling in a hosted service.',
        command: 'osv-scanner scan -r .\nzizmor .',
        links: [
          ['OSV-Scanner', TRUST_LINKS.osv],
          ['zizmor', TRUST_LINKS.zizmor],
          ['Actions security', TRUST_LINKS.actionsSecurity],
        ],
      },
      {
        key: 'slsa',
        level: 'Level 4',
        label: 'Supply-chain trajectory',
        title: 'Learn release provenance and SLSA',
        summary: 'When people depend on builds or packages, move from "repo looks healthy" to "artifact can be traced back to source and build process." Start with SLSA levels and GitHub artifact attestations.',
        command: '',
        links: [
          ['SLSA levels', TRUST_LINKS.slsa],
          ['Artifact attestations', TRUST_LINKS.attestations],
        ],
      },
      {
        key: 'github-native',
        level: 'Track',
        label: 'Buyer trust',
        title: 'Know what serious customers may ask for',
        summary: `${profileLabel}: if a repo becomes part of a product buyers rely on, learn the language around CodeQL, security alerts, release provenance, and SOC reports before a sales or procurement conversation forces it.`,
        command: '',
        links: [
          ['CodeQL', TRUST_LINKS.codeql],
          ['SOC overview', TRUST_LINKS.soc],
        ],
      },
    ];
  }

  function renderLinks(item) {
    return (item.links || []).map(([label, href]) => (
      `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`
    )).join('');
  }

  function renderTrustItem(item) {
    return `
      <article class="trust-item trust-item-${escapeHtml(item.key)}">
        <div class="trust-item-head">
          <span class="trust-item-level">${escapeHtml(item.level || '')}</span>
        </div>
        <span class="trust-item-label">${escapeHtml(item.label)}</span>
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.summary)}</p>
        ${item.command ? `<code>${escapeHtml(item.command)}</code>` : ''}
        <div class="trust-links">${renderLinks(item)}</div>
      </article>`;
  }

  function renderTrustPlaybook() {
    const container = document.getElementById('trust-playbook');
    if (!container) return;
    const repos = getVisibleRepos();
    const payload = currentPayload() || {};
    const items = buildTrustPlaybookItems(repos, payload);
    container.innerHTML = `
      <div class="trust-playbook-head">
        <div>
          <div class="section-kicker">Workbench</div>
          <h2>Raise the bar</h2>
          <p>Learning tracks for maintainers who want to move from public polish to security baselines, supply-chain provenance, and customer trust.</p>
        </div>
        <span class="trust-playbook-pill">${formatNumber(repos.length)} selected - ${escapeHtml(visibleWindowLabel())}</span>
      </div>
      <div class="trust-playbook-grid">
        ${items.map(renderTrustItem).join('')}
      </div>`;
  }

  return { TRUST_LINKS, asBool, missingReadinessCount, downstreamDelta, repoTrustPriority, pickFocusRepo, buildTrustPlaybookItems, renderTrustPlaybook };
}

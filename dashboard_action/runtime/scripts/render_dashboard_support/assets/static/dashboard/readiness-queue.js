export function installReadinessQueue(context) {
  const document = context.document;
  const activateRepo = (...args) => context.activateRepo(...args);
  const escapeHtml = (...args) => context.escapeHtml(...args);
  const formatNumber = (...args) => context.formatNumber(...args);
  const getShortName = (...args) => context.getShortName(...args);
  const getVisibleRepos = (...args) => context.getVisibleRepos(...args);

  const READINESS_SIGNALS = [
    {
      key: 'has_readme',
      label: 'README',
      filename: 'README.md',
      action: 'Make the first visit explain the value, setup path, and next step.',
      href: 'https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes',
      guide: 'README guide'
    },
    {
      key: 'has_license',
      label: 'License',
      filename: 'LICENSE',
      action: 'Make adoption terms explicit before interested users evaluate the project.',
      href: 'https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository',
      guide: 'License guide'
    },
    {
      key: 'has_contributing',
      label: 'Contributing',
      filename: 'CONTRIBUTING.md',
      action: 'Give interested visitors a clear route from curiosity to useful contribution.',
      href: 'https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors',
      guide: 'Contributor guide'
    },
    {
      key: 'has_issue_template',
      label: 'Issue template',
      filename: '.github/ISSUE_TEMPLATE',
      action: 'Shape new attention into reports that maintainers can act on.',
      href: 'https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository',
      guide: 'Issue template guide'
    },
    {
      key: 'has_pull_request_template',
      label: 'PR template',
      filename: '.github/pull_request_template.md',
      action: 'Make incoming changes arrive with review context.',
      href: 'https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository',
      guide: 'PR template guide'
    },
    {
      key: 'has_code_of_conduct',
      label: 'Code of conduct',
      filename: 'CODE_OF_CONDUCT.md',
      action: 'Set participation expectations while the project is still small enough to steer.',
      href: 'https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/adding-a-code-of-conduct-to-your-project',
      guide: 'Conduct guide'
    }
  ];

  function asBool(value) {
    if (value === true || value === false) return value;
    const normalized = String(value ?? '').trim().toLowerCase();
    if (!normalized) return null;
    if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
    if (['false', '0', 'no', 'off'].includes(normalized)) return false;
    return null;
  }

  function asNumber(value) {
    const normalized = String(value ?? '').trim();
    if (!normalized) return null;
    const number = Number(normalized);
    return Number.isFinite(number) ? number : null;
  }

  function buildReadinessRows(repos) {
    return (repos || []).map((repo) => {
      const community = repo.community || {};
      const known = READINESS_SIGNALS.filter((signal) => asBool(community[signal.key]) !== null);
      const present = known.filter((signal) => asBool(community[signal.key]) === true);
      const missing = known.filter((signal) => asBool(community[signal.key]) === false);
      const health = asNumber(community.health_percentage);
      const activity = Number(repo.activity || 0);
      return {
        repo,
        missing,
        knownCount: known.length,
        presentCount: present.length,
        activity,
        health,
        priority: missing.length * 1000 + activity + Math.max(0, 100 - (health === null ? 100 : health))
      };
    });
  }

  function readinessSummary(rows) {
    const known = rows.reduce((total, row) => total + row.knownCount, 0);
    const present = rows.reduce((total, row) => total + row.presentCount, 0);
    const missingRepos = rows.filter((row) => row.missing.length).length;
    const healthValues = rows.map((row) => row.health).filter((value) => value !== null);
    const avgHealth = healthValues.length
      ? Math.round(healthValues.reduce((total, value) => total + value, 0) / healthValues.length)
      : null;
    return { known, present, missingRepos, avgHealth };
  }

  function readinessCoverageRows(rows) {
    return READINESS_SIGNALS.map((signal) => {
      const known = rows.filter((row) => asBool(row.repo.community?.[signal.key]) !== null);
      const present = known.filter((row) => asBool(row.repo.community?.[signal.key]) === true);
      return {
        key: signal.key,
        label: signal.label,
        present: present.length,
        known: known.length,
        pct: known.length ? (present.length / known.length) * 100 : 0
      };
    });
  }

  function renderReadinessSummary(rows) {
    const container = document.getElementById('readiness-summary');
    if (!container) return;
    if (!rows.length) {
      container.innerHTML = '<p class="empty-msg">No visible published repos in this window.</p>';
      return;
    }
    const summary = readinessSummary(rows);
    const coverage = readinessCoverageRows(rows);
    container.innerHTML = `
        <div class="readiness-score">
          <span class="readiness-score-value">${summary.avgHealth === null ? '-' : formatNumber(summary.avgHealth) + '%'}</span>
          <span class="readiness-score-meta">${formatNumber(summary.present)} of ${formatNumber(summary.known)} known public-readiness checks present</span>
          <span class="readiness-score-meta">${formatNumber(summary.missingRepos)} published repo${summary.missingRepos === 1 ? '' : 's'} with a visible setup gap</span>
        </div>
        <div class="readiness-bars">
          ${coverage.map((row) => `
            <div class="readiness-row">
              <span>${escapeHtml(row.label)}</span>
              <div class="readiness-track" aria-hidden="true"><span data-pct="${Math.max(0, Math.min(100, row.pct)).toFixed(1)}"></span></div>
              <span class="mono">${formatNumber(row.present)}/${formatNumber(row.known)}</span>
            </div>`).join('')}
        </div>`;
    container.querySelectorAll('.readiness-track span').forEach((bar) => {
      bar.style.setProperty('--readiness-pct', (bar.dataset.pct || '0') + '%');
    });
  }

  function renderReadinessList(rows) {
    const container = document.getElementById('readiness-list');
    if (!container) return;
    const missingRows = rows
      .filter((row) => row.missing.length)
      .sort((a, b) => b.priority - a.priority)
      .slice(0, 4);
    if (!missingRows.length) {
      container.innerHTML = '<p class="empty-msg">Every visible published repo has the known community-health files.</p>';
      return;
    }
    container.innerHTML = missingRows.map((row) => {
      const primary = row.missing[0];
      const extra = row.missing.length - 1;
      return `
          <div class="readiness-fix" role="button" tabindex="0" data-repo="${escapeHtml(row.repo.name)}">
            <span class="readiness-fix-head">
              <span class="readiness-repo">${escapeHtml(getShortName(row.repo.name))}</span>
              <span class="readiness-meta">${formatNumber(row.activity)} views + clones</span>
            </span>
            <span class="readiness-file">${escapeHtml(primary.filename || primary.label)}${extra > 0 ? ' +' + formatNumber(extra) : ''}</span>
            <span class="readiness-action">${escapeHtml(primary.action)}</span>
            <span class="readiness-learn"><a href="${escapeHtml(primary.href || '#')}" target="_blank" rel="noopener noreferrer">${escapeHtml(primary.guide || 'Guide')}</a></span>
          </div>`;
    }).join('');
    container.querySelectorAll('.readiness-fix').forEach((card) => {
      const focusRepo = function(event) {
        if (event?.target?.closest && event.target.closest('a')) return;
        activateRepo(card.dataset.repo, !!(event && (event.metaKey || event.ctrlKey || event.shiftKey)));
      };
      card.addEventListener('click', focusRepo);
      card.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          focusRepo(event);
        }
      });
    });
  }

  function renderReadinessQueue() {
    const card = document.getElementById('readiness-card');
    if (!card) return;
    const section = card.closest ? card.closest('.readiness-section') : null;
    const rows = buildReadinessRows(getVisibleRepos());
    const hasKnownData = rows.some((row) => row.knownCount > 0);
    if (!hasKnownData) {
      if (section) section.style.display = 'none';
      card.style.display = 'none';
      return;
    }
    if (section) section.style.display = 'grid';
    card.style.display = 'block';
    renderReadinessSummary(rows);
    renderReadinessList(rows);
  }

  return { READINESS_SIGNALS, asBool, asNumber, buildReadinessRows, readinessSummary, readinessCoverageRows, renderReadinessQueue };
}

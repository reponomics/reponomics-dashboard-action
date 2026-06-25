export function installTables(context) {
  const document = context.document;
  const window = context.window;
  const buildSparklinePath = (...args) => context.buildSparklinePath(...args);
  const currentPayload = (...args) => context.currentPayload(...args);
  const escapeHtml = (...args) => context.escapeHtml(...args);
  const formatNumber = (...args) => context.formatNumber(...args);
  const formatSigned = (...args) => context.formatSigned(...args);
  const getShortName = (...args) => context.getShortName(...args);
  const renderRepoTable = (...args) => context.renderRepoTable(...args);
  const selectRepo = (...args) => context.selectRepo(...args);
  const state = context.state;
  const updateDashboard = (...args) => context.updateDashboard(...args);

    function sortRows(rows, key, dir, labelKey) {
      const factor = dir === 'asc' ? 1 : -1;
      const numeric = key === 'count' || key === 'uniques' || key === 'share';
      return rows.slice().sort((a, b) => {
        const av = numeric ? Number(a[key] || 0) : String(a[labelKey] || '').toLowerCase();
        const bv = numeric ? Number(b[key] || 0) : String(b[labelKey] || '').toLowerCase();
        if (av < bv) return -1 * factor;
        if (av > bv) return 1 * factor;
        return 0;
      });
    }

    function renderSnapshotTable(elId, rows, options) {
      const el = document.getElementById(elId);
      if (!rows.length) {
        el.innerHTML = '<p class="empty-msg">' + escapeHtml(options.emptyMsg) + '</p>';
        return;
      }
      const labelKey = options.labelKey;
      const labelHeader = options.labelHeader;
      const sortKey = options.sortKey || 'count';
      const sortDir = options.sortDir || 'desc';

      const total = rows.reduce((acc, r) => acc + Number(r.count || 0), 0);
      const sorted = sortRows(rows, sortKey, sortDir, labelKey);
      const arrow = (k) => sortKey === k ? (sortDir === 'asc' ? '↑' : '↓') : '↕';
      const head = (k, label, num) => {
        const cls = ['sortable', sortKey === k ? 'active' : '', num ? 'num' : ''].filter(Boolean).join(' ');
        return `<th class="${cls}" data-sort="${k}"><span>${label}</span><span class="arrow">${arrow(k)}</span></th>`;
      };
      let html = '<div class="table-wrap"><table><thead><tr>' +
        head('label', labelHeader) +
        head('count', 'Views', true) +
        head('uniques', 'Uniques', true) +
        head('share', 'Share', true) +
        '</tr></thead><tbody>';

      sorted.forEach((row) => {
        const label = (options.formatLabel ? options.formatLabel(row) : row[labelKey]) || '';
        const sharePct = total > 0 ? (Number(row.count || 0) / total) * 100 : 0;
        html += '<tr>' +
          '<td title="' + escapeHtml(label) + '">' + escapeHtml(label) + '</td>' +
          '<td class="num mono">' + formatNumber(row.count) + '</td>' +
          '<td class="num mono">' + formatNumber(row.uniques) + '</td>' +
          '<td class="num mono">' + sharePct.toFixed(1) + '%</td>' +
          '</tr>';
      });
      html += '</tbody></table></div>';
      el.innerHTML = html;

      el.querySelectorAll('th.sortable').forEach((th) => {
        th.addEventListener('click', function() {
          const key = th.dataset.sort === 'label' ? 'label' : th.dataset.sort;
          options.onSort(key);
        });
      });
    }

    function renderReferrerTable(rows) {
      renderSnapshotTable('referrer-table', rows, {
        labelKey: 'referrer',
        labelHeader: 'Referrer',
        sortKey: state.referrerSortKey || 'count',
        sortDir: state.referrerSortDir || 'desc',
        emptyMsg: 'No referrer data yet — referrers appear after a few collection runs.',
        onSort: function(key) {
          if (state.referrerSortKey === key) {
            state.referrerSortDir = state.referrerSortDir === 'desc' ? 'asc' : 'desc';
          } else {
            state.referrerSortKey = key;
            state.referrerSortDir = key === 'label' ? 'asc' : 'desc';
          }
          updateDashboard();
        }
      });
    }

    function renderPathsTable(rows) {
      const el = document.getElementById('paths-table');
      if (!rows.length) {
        el.innerHTML = '<p class="empty-msg">No path data yet — popular pages appear after a few collection runs.</p>';
        return;
      }
      const sortKey = state.pathSortKey || 'count';
      const sortDir = state.pathSortDir || 'desc';
      const factor = sortDir === 'asc' ? 1 : -1;
      const total = rows.reduce((acc, r) => acc + Number(r.count || 0), 0);
      const sorted = rows.slice().sort((a, b) => {
        const numeric = sortKey === 'count' || sortKey === 'uniques' || sortKey === 'share';
        const av = numeric ? Number(a[sortKey] || 0) : String(a[sortKey] || '').toLowerCase();
        const bv = numeric ? Number(b[sortKey] || 0) : String(b[sortKey] || '').toLowerCase();
        if (av < bv) return -1 * factor;
        if (av > bv) return 1 * factor;
        return 0;
      });
      const arrow = (k) => sortKey === k ? (sortDir === 'asc' ? '↑' : '↓') : '↕';
      const head = (k, label, num) => {
        const cls = ['sortable', sortKey === k ? 'active' : '', num ? 'num' : ''].filter(Boolean).join(' ');
        return `<th class="${cls}" data-sort="${k}"><span>${label}</span><span class="arrow">${arrow(k)}</span></th>`;
      };
      let html = '<div class="table-wrap"><table><thead><tr>' +
        head('repo', 'Repository') +
        head('content', 'Content') +
        head('count', 'Views', true) +
        head('uniques', 'Uniques', true) +
        head('share', 'Share', true) +
        '</tr></thead><tbody>';
      sorted.forEach((row) => {
        const repo = row.repo || '';
        const content = row.content || row.title || row.path || '';
        const sharePct = total > 0 ? (Number(row.count || 0) / total) * 100 : 0;
        html += '<tr>' +
          '<td title="' + escapeHtml(repo) + '">' + escapeHtml(getShortName(repo)) + '</td>' +
          '<td title="' + escapeHtml(row.path || content) + '">' + escapeHtml(content) + '</td>' +
          '<td class="num mono">' + formatNumber(row.count) + '</td>' +
          '<td class="num mono">' + formatNumber(row.uniques) + '</td>' +
          '<td class="num mono">' + sharePct.toFixed(1) + '%</td>' +
          '</tr>';
      });
      html += '</tbody></table></div>';
      el.innerHTML = html;
      el.querySelectorAll('th.sortable').forEach((th) => {
        th.addEventListener('click', function() {
          const key = th.dataset.sort;
          if (state.pathSortKey === key) {
            state.pathSortDir = state.pathSortDir === 'desc' ? 'asc' : 'desc';
          } else {
            state.pathSortKey = key;
            state.pathSortDir = key === 'repo' || key === 'content' ? 'asc' : 'desc';
          }
          updateDashboard();
        });
      });
    }

    function classifyInsight(item) {
      if (item.kind === 'narrative') {
        if (item.tone === 'risk' || item.tone === 'data_quality') return 'down';
        if (item.tone === 'opportunity') return 'up';
        return 'neutral';
      }
      if (item.kind === 'spike') {
        return item.direction === 'spiked' ? 'up' : 'down';
      }
      if (item.kind === 'trend') {
        if (item.pct === null || item.pct === undefined) return 'up';
        if (item.pct > 2) return 'up';
        if (item.pct < -2) return 'down';
        return 'neutral';
      }
      if (item.kind === 'growth') {
        return item.subtype === 'high_attention_low_interest' || item.subtype === 'traffic_without_downstream_growth'
          ? 'neutral'
          : 'up';
      }
      return 'neutral';
    }

    function renderInsights() {
      const container = document.getElementById('insights-list');
      if (!container) return;

      const payload = currentPayload();
      const structured = (payload && payload.insights_v2) || [];
      const fallback = (payload && payload.insights) || [];

      if (!structured.length && !fallback.length) {
        container.innerHTML = '<p class="empty-msg">Needs more data to surface a signal yet — check back after a few more collection runs.</p>';
        return;
      }

      const items = structured.length ? structured : fallback.map((text) => ({ kind: 'legacy', text }));
      const ul = document.createElement('ul');
      ul.className = 'insights-list';

      items.forEach((item) => {
        const li = document.createElement('li');
        const tone = classifyInsight(item);
        li.className = 'insight-item ' + tone;
        li.tabIndex = 0;

        const repo = item.repo || '';
        const shortRepo = getShortName(repo);
        const icon = tone === 'up' ? '▲' : tone === 'down' ? '▼' : '•';

        let headline = '';
        let meta = '';
        let pctLabel = '';

        if (item.kind === 'narrative') {
          headline = escapeHtml(item.headline || item.text || '');
          const evidence = Array.isArray(item.evidence) ? item.evidence.slice(0, 4) : [];
          const evidenceText = evidence
            .map((fact) => {
              const label = String(fact && fact.label ? fact.label : '').trim();
              const value = String(fact && fact.value ? fact.value : '').trim();
              if (!label && !value) return '';
              return label && value ? `${label}: ${value}` : (label || value);
            })
            .filter(Boolean)
            .join(' · ');
          meta = [item.body || '', evidenceText ? `Evidence: ${evidenceText}` : '']
            .filter(Boolean)
            .join(' ');
          pctLabel = item.confidence ? String(item.confidence) : (item.tone || 'story');
        } else if (item.kind === 'trend') {
          const verb = (item.pct === null || item.pct === undefined)
            ? 'started getting'
            : (item.pct > 0 ? 'is up on' : 'is down on');
          headline = `<span class="repo">${escapeHtml(shortRepo)}</span> ${verb} ${item.metric}`;
          const window = item.window_days || 7;
          meta = `${formatNumber(item.prior)} → ${formatNumber(item.current)} over ${window}d (${item.delta >= 0 ? '+' : ''}${formatNumber(item.delta)})`;
          if (item.pct === null || item.pct === undefined) {
            pctLabel = 'new';
          } else {
            const sign = item.pct >= 0 ? '+' : '';
            pctLabel = `${sign}${Math.round(item.pct)}%`;
          }
        } else if (item.kind === 'spike') {
          headline = `<span class="repo">${escapeHtml(shortRepo)}</span> ${item.metric} ${item.direction} versus baseline`;
          meta = `latest ${formatNumber(item.current)} vs trailing median ${formatNumber(Math.round(item.baseline))}`;
          pctLabel = item.direction === 'spiked' ? '↑ spike' : '↓ drop';
        } else if (item.kind === 'growth') {
          const growthText = escapeHtml(item.text || '').replace(/^`[^`]+`\s*/, '');
          headline = '<span class="repo">' + escapeHtml(shortRepo) + '</span> ' + growthText;
          const parts = [];
          if (item.traffic !== undefined) parts.push(`${formatNumber(item.traffic)} views`);
          if (item.visitors !== undefined) parts.push(`${formatNumber(item.visitors)} visitors`);
          if (item.clones !== undefined) parts.push(`${formatNumber(item.clones)} clones`);
          if (item.downstream_delta !== undefined) parts.push(`${formatSigned(item.downstream_delta)} downstream`);
          if (item.delta !== undefined) parts.push(`${formatSigned(item.delta)} ${item.metric}`);
          meta = parts.join(' · ');
          pctLabel = item.subtype ? 'growth' : '';
        } else {
          headline = escapeHtml(item.text || '');
          meta = '';
          pctLabel = '';
        }

        li.innerHTML =
          `<div class="insight-icon" aria-hidden="true">${icon}</div>` +
          `<div class="insight-body"><div class="insight-headline">${headline}</div>` +
          (meta ? `<div class="insight-meta mono">${escapeHtml(meta)}</div>` : '') +
          `</div>` +
          (pctLabel ? `<div class="insight-pct">${escapeHtml(pctLabel)}</div>` : '');

        if (repo) {
          li.setAttribute('role', 'button');
          li.setAttribute('aria-label', `Focus on ${shortRepo}`);
          const focus = function() { selectRepo(repo); window.scrollTo({ top: 0, behavior: 'smooth' }); };
          li.addEventListener('click', focus);
          li.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); focus(); }
          });
        } else {
          li.style.cursor = 'default';
        }

        ul.appendChild(li);
      });

      container.innerHTML = '';
      container.appendChild(ul);
    }

    function asBool(value) {
      if (value === true || value === false) return value;
      const normalized = String(value || '').trim().toLowerCase();
      if (!normalized) return null;
      if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
      if (['false', '0', 'no', 'off'].includes(normalized)) return false;
      return null;
    }

    function renderCommunityCell(repo) {
      const community = repo.community || {};
      const health = Number(community.health_percentage);
      const hasHealth = Number.isFinite(health);
      const signals = [
        asBool(community.has_code_of_conduct),
        asBool(community.has_contributing),
        asBool(community.has_issue_template),
        asBool(community.has_pull_request_template),
        asBool(community.has_readme),
        asBool(community.has_license)
      ];
      const knownSignals = signals.filter((value) => value !== null);
      const presentSignals = knownSignals.filter(Boolean).length;
      const statusClass = hasHealth
        ? (health >= 85 ? 'excellent' : health >= 60 ? 'moderate' : 'needs-work')
        : 'unknown';
      const signalText = knownSignals.length
        ? `${presentSignals}/${knownSignals.length} files`
        : 'No file signal';
      const docs = String(community.documentation || '').trim();
      const docLabel = docs ? 'Docs linked' : 'No docs URL';
      return `
        <span class="community-cell ${statusClass}">
          <span class="community-health">${hasHealth ? formatNumber(health) + '%' : '—'}</span>
          <span class="community-meta">${escapeHtml(signalText)} · ${escapeHtml(docLabel)}</span>
        </span>
      `;
    }

    function buildRepoSparkSVG(values, color) {
      if (!values || values.length < 2) return '';
      const { line, area } = buildSparklinePath(values, 92, 26);
      return `<svg class="repo-spark" viewBox="0 0 92 26" preserveAspectRatio="none" aria-hidden="true">` +
        `<path class="area" d="${area}" fill="${color}"></path>` +
        `<path class="line" d="${line}" stroke="${color}"></path></svg>`;
    }

    function getRepoSortKey(repo, key) {
      if (key === 'name') return repo.name.toLowerCase();
      if (key === 'growth') return Number(repo.stars_delta || 0) + Number(repo.subscribers_delta || 0) + Number(repo.forks_delta || 0);
      if (key === 'community') {
        const health = Number(repo.community?.health_percentage);
        return Number.isFinite(health) ? health : -1;
      }
      return Number(repo[key] || 0);
    }

    function sortRepos(repos, key, dir) {
      const factor = dir === 'asc' ? 1 : -1;
      const out = repos.slice();
      out.sort((a, b) => {
        const av = getRepoSortKey(a, key);
        const bv = getRepoSortKey(b, key);
        if (av < bv) return -1 * factor;
        if (av > bv) return 1 * factor;
        return a.name.localeCompare(b.name);
      });
      return out;
    }

    function setRepoSort(key) {
      if (state.repoSortKey === key) {
        state.repoSortDir = state.repoSortDir === 'desc' ? 'asc' : 'desc';
      } else {
        state.repoSortKey = key;
        state.repoSortDir = key === 'name' ? 'asc' : 'desc';
      }
      renderRepoTable();
    }

  return { sortRows, renderSnapshotTable, renderReferrerTable, renderPathsTable, classifyInsight, renderInsights, asBool, renderCommunityCell, buildRepoSparkSVG, getRepoSortKey, sortRepos, setRepoSort };
}

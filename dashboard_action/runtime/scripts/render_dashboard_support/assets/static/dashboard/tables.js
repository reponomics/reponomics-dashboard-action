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
        if (item.tone === 'opportunity') return 'up';
        if (item.tone === 'risk') return 'down';
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

    function narrativeToneLabel(tone) {
      if (tone === 'opportunity') return 'signal';
      if (tone === 'risk') return 'watch';
      if (tone === 'watch') return 'watch';
      if (tone === 'explain') return 'context';
      return 'note';
    }

    function safeInsightUrl(value) {
      const raw = String(value || '').trim();
      if (!raw) return '';
      try {
        const base = (window.location && window.location.href) || 'https://github.com/';
        const url = new URL(raw, base);
        return url.hostname === 'github.com' ? url.href : '';
      } catch (_e) {
        return '';
      }
    }

    function renderNarrativeEvidence(evidence) {
      const rows = Array.isArray(evidence) ? evidence.filter(Boolean).slice(0, 4) : [];
      if (!rows.length) return '';
      return '<div class="insight-evidence">' + rows.map((row) => {
        const label = escapeHtml(row.label || '');
        const value = escapeHtml(row.value || '');
        const detail = escapeHtml(row.detail || '');
        return '<span class="evidence-chip">' +
          (label ? '<span class="evidence-label">' + label + '</span>' : '') +
          (value ? '<span class="evidence-value">' + value + '</span>' : '') +
          (detail ? '<span class="evidence-detail">' + detail + '</span>' : '') +
          '</span>';
      }).join('') + '</div>';
    }

    function renderNearbyContext(contextRows) {
      const rows = Array.isArray(contextRows) ? contextRows.filter(Boolean).slice(0, 3) : [];
      if (!rows.length) return '';
      return '<div class="insight-context">' + rows.map((row) => {
        const label = escapeHtml(row.label || 'Context');
        const detail = escapeHtml(row.detail || '');
        const date = escapeHtml(row.date || '');
        const url = safeInsightUrl(row.url || '');
        const labelHtml = url
          ? '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' + label + '</a>'
          : '<span>' + label + '</span>';
        return '<div class="context-row">' +
          '<span class="context-date mono">' + (date || 'context') + '</span>' +
          '<span class="context-label">' + labelHtml + (detail ? '<span class="context-detail">' + detail + '</span>' : '') + '</span>' +
          '</div>';
      }).join('') + '</div>';
    }

    function currentInsightItems() {
      const payload = currentPayload();
      const structured = (payload && payload.insights_v2) || [];
      const fallback = (payload && payload.insights) || [];
      return structured.length ? structured : fallback.map((text) => ({ kind: 'legacy', text }));
    }

    function insightKindLabel(item, tone) {
      if (item.kind === 'narrative') return narrativeToneLabel(item.tone);
      if (item.kind === 'growth') return 'growth';
      if (item.kind === 'trend') return item.pct === null || item.pct === undefined ? 'new' : (tone === 'down' ? 'dip' : 'trend');
      if (item.kind === 'spike') return item.direction === 'spiked' ? 'spike' : 'drop';
      return 'note';
    }

    function insightActionText(item, tone) {
      if (item.action) return item.action;
      if (item.kind === 'growth') {
        if (item.subtype === 'high_attention_low_interest' || item.subtype === 'traffic_without_downstream_growth') {
          return 'Tighten the README, examples, and release notes so visitors can quickly see why to try it now.';
        }
        if (item.subtype === 'clone_heavy_star_light') {
          return 'Make the install path and next step after cloning obvious while adoption interest is visible.';
        }
        return 'Compare this repo against the rest of the selected set and decide whether the public-facing path needs a small follow-up.';
      }
      if (item.kind === 'trend') {
        return tone === 'down'
          ? 'Check whether this is normal window noise or whether the repo needs a fresh public-facing reason to return.'
          : 'Look for matching code, docs, release, path, or referrer movement before the signal gets stale.';
      }
      if (item.kind === 'spike') {
        return item.direction === 'spiked'
          ? 'Inspect nearby commits, releases, paths, and referrers to see what may be worth repeating.'
          : 'Check whether the drop follows a quiet release window, stale docs, or a missing next step.';
      }
      return 'Use the detail sections below to decide whether there is a low-friction follow-up worth making.';
    }

    function buildInsightModel(item, index) {
        const tone = classifyInsight(item);
        const repo = item.repo || '';
        const shortRepo = getShortName(repo);
        const icon = tone === 'up' ? '▲' : tone === 'down' ? '▼' : '•';

        let headline = '';
        let titleText = '';
        let meta = '';
        let pctLabel = '';
        let detailHtml = '';
        let leadDetailHtml = '';

        if (item.kind === 'narrative') {
          titleText = item.title || 'Signal worth a look';
          headline = '<span class="repo">' + escapeHtml(shortRepo) + '</span> ' + escapeHtml(titleText);
          meta = item.summary || '';
          pctLabel = narrativeToneLabel(item.tone);
          leadDetailHtml =
            renderNarrativeEvidence(item.evidence) +
            renderNearbyContext(item.nearby_context);
          detailHtml =
            leadDetailHtml +
            (item.action ? '<div class="insight-action"><span>Try next</span>' + escapeHtml(item.action) + '</div>' : '');
        } else if (item.kind === 'trend') {
          const verb = (item.pct === null || item.pct === undefined)
            ? 'started getting'
            : (item.pct > 0 ? 'is up on' : 'is down on');
          titleText = `${shortRepo} ${verb} ${item.metric}`;
          headline = `<span class="repo">${escapeHtml(shortRepo)}</span> ${escapeHtml(verb)} ${escapeHtml(item.metric || '')}`;
          const window = item.window_days || 7;
          meta = `${formatNumber(item.prior)} → ${formatNumber(item.current)} over ${window}d (${item.delta >= 0 ? '+' : ''}${formatNumber(item.delta)})`;
          if (item.pct === null || item.pct === undefined) {
            pctLabel = 'new';
          } else {
            const sign = item.pct >= 0 ? '+' : '';
            pctLabel = `${sign}${Math.round(item.pct)}%`;
          }
        } else if (item.kind === 'spike') {
          titleText = `${shortRepo} ${item.metric} ${item.direction} versus baseline`;
          headline = `<span class="repo">${escapeHtml(shortRepo)}</span> ${escapeHtml(item.metric || '')} ${escapeHtml(item.direction || '')} versus baseline`;
          meta = `latest ${formatNumber(item.current)} vs trailing median ${formatNumber(Math.round(item.baseline))}`;
          pctLabel = item.direction === 'spiked' ? '↑ spike' : '↓ drop';
        } else if (item.kind === 'growth') {
          const growthText = escapeHtml(item.text || '').replace(/^`[^`]+`\s*/, '');
          titleText = `${shortRepo} ${String(item.text || '').replace(/^`[^`]+`\s*/, '')}`.trim();
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
          titleText = item.text || 'Signal worth a look';
          headline = escapeHtml(item.text || '');
          meta = '';
          pctLabel = '';
        }

        return {
          item,
          index,
          tone,
          repo,
          shortRepo,
          icon,
          headline,
          titleText,
          meta,
          pctLabel,
          detailHtml,
          leadDetailHtml,
          tag: insightKindLabel(item, tone),
          actionText: insightActionText(item, tone),
          narrative: item.kind === 'narrative',
        };
    }

    function renderLeadStory(models) {
      const carousel = document.getElementById('leadStoryCarousel');
      const controls = document.getElementById('storyControls');
      const prev = document.getElementById('storyPrevBtn');
      const next = document.getElementById('storyNextBtn');
      if (!carousel) return;

      if (!models.length) {
        carousel.innerHTML = '<p class="empty-msg">Needs more data to surface a signal yet - check back after a few more collection runs.</p>';
        if (controls) controls.innerHTML = '';
        if (prev) prev.disabled = true;
        if (next) next.disabled = true;
        return;
      }

      const activeIndex = Math.min(Math.max(Number(state.storyIndex || 0), 0), models.length - 1);
      state.storyIndex = activeIndex;
      const model = models[activeIndex];
      const repoMeta = model.repo
        ? '<span class="lead-story-repo mono">' + escapeHtml(model.shortRepo) + '</span>'
        : '';
      const actionHtml = model.actionText
        ? '<div class="lead-story-action"><span>Try next</span>' + escapeHtml(model.actionText) + '</div>'
        : '';
      const focusHtml = model.repo
        ? '<button class="toolbar-button lead-story-focus" type="button" data-repo="' + escapeHtml(model.repo) + '">Focus repo</button>'
        : '';

      carousel.innerHTML =
        '<article class="lead-story-slide ' + model.tone + '">' +
          '<div class="lead-story-meta">' +
            '<span class="lead-story-tag">' + escapeHtml(model.tag) + '</span>' +
            repoMeta +
            (model.pctLabel ? '<span class="lead-story-score mono">' + escapeHtml(model.pctLabel) + '</span>' : '') +
          '</div>' +
          '<h3>' + model.headline + '</h3>' +
          (model.meta ? '<p class="lead-story-summary">' + escapeHtml(model.meta) + '</p>' : '') +
          (model.leadDetailHtml || model.detailHtml) +
          actionHtml +
          (focusHtml ? '<div class="lead-story-footer">' + focusHtml + '</div>' : '') +
        '</article>';

      const focusButton = carousel.querySelector('.lead-story-focus');
      if (focusButton) {
        focusButton.addEventListener('click', function() {
          selectRepo(focusButton.dataset.repo);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        });
      }

      if (controls) {
        controls.innerHTML = models.map((card, idx) => {
          const label = card.repo ? card.shortRepo : card.tag;
          return '<button class="story-tab' + (idx === activeIndex ? ' is-active' : '') + '" type="button" data-story-index="' + idx + '" aria-pressed="' + (idx === activeIndex ? 'true' : 'false') + '">' +
            '<span>' + escapeHtml(card.tag) + '</span>' +
            '<strong>' + escapeHtml(label || ('Story ' + (idx + 1))) + '</strong>' +
          '</button>';
        }).join('');
        controls.querySelectorAll('[data-story-index]').forEach((button) => {
          button.addEventListener('click', function() {
            state.storyIndex = Number(button.dataset.storyIndex || 0);
            renderInsights();
          });
        });
      }

      const move = function(delta) {
        state.storyIndex = (activeIndex + delta + models.length) % models.length;
        renderInsights();
      };
      if (prev) {
        prev.disabled = models.length < 2;
        prev.onclick = function() { move(-1); };
      }
      if (next) {
        next.disabled = models.length < 2;
        next.onclick = function() { move(1); };
      }
    }

    function renderInsights() {
      const container = document.getElementById('insights-list');
      const models = currentInsightItems().map(buildInsightModel);
      renderLeadStory(models);
      if (!container) return;

      if (!models.length) {
        container.innerHTML = '<p class="empty-msg">Needs more data to surface a signal yet - check back after a few more collection runs.</p>';
        return;
      }

      const ul = document.createElement('ul');
      ul.className = 'insights-list';

      models.forEach((model) => {
        const li = document.createElement('li');
        li.className = 'insight-item ' + model.tone + (model.narrative ? ' narrative' : '') + (model.index === state.storyIndex ? ' active-story' : '');
        li.tabIndex = 0;
        li.dataset.storyIndex = String(model.index);

        li.innerHTML =
          `<div class="insight-icon" aria-hidden="true">${model.icon}</div>` +
          `<div class="insight-body"><div class="insight-headline">${model.headline}</div>` +
          (model.meta ? `<div class="insight-meta mono">${escapeHtml(model.meta)}</div>` : '') +
          model.detailHtml +
          `</div>` +
          (model.pctLabel ? `<div class="insight-pct">${escapeHtml(model.pctLabel)}</div>` : '');

        if (model.repo) {
          li.setAttribute('role', 'button');
          li.setAttribute('aria-label', `Focus on ${model.shortRepo}`);
          const focus = function() { selectRepo(model.repo); };
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

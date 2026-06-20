export function installController(context) {
  const document = context.document;
  const window = context.window;
  const navigator = context.navigator;
  const localStorage = context.localStorage;
  const history = context.history;
  const DEFAULT_WINDOW = context.DEFAULT_WINDOW;
  const MAX_COMPARE_REPOS = context.MAX_COMPARE_REPOS;
  const METRICS = context.METRICS;
  const THEME_KEY = context.THEME_KEY;
  const activateRepo = (...args) => context.activateRepo(...args);
  const applyTheme = (...args) => context.applyTheme(...args);
  const buildRepoSparkSVG = (...args) => context.buildRepoSparkSVG(...args);
  const buildUpdatedText = (...args) => context.buildUpdatedText(...args);
  const chunkDiagnosticsText = (...args) => context.chunkDiagnosticsText(...args);
  const clearChunkLoadErrors = (...args) => context.clearChunkLoadErrors(...args);
  const clearSelection = (...args) => context.clearSelection(...args);
  const createDashboardDataProvider = (...args) => context.createDashboardDataProvider(...args);
  const currentChunkLoadErrors = (...args) => context.currentChunkLoadErrors(...args);
  const currentPayload = (...args) => context.currentPayload(...args);
  const dashboardData = (...args) => context.dashboardData(...args);
  const ensureCharts = (...args) => context.ensureCharts(...args);
  const escapeHtml = (...args) => context.escapeHtml(...args);
  const formatNumber = (...args) => context.formatNumber(...args);
  const formatSigned = (...args) => context.formatSigned(...args);
  const getCurrentPathRows = (...args) => context.getCurrentPathRows(...args);
  const getCurrentReferrerRows = (...args) => context.getCurrentReferrerRows(...args);
  const getDefaultWindow = (...args) => context.getDefaultWindow(...args);
  const getRepoColor = (...args) => context.getRepoColor(...args);
  const getSelectedWindow = (...args) => context.getSelectedWindow(...args);
  const getShortName = (...args) => context.getShortName(...args);
  const getVisibleRepos = (...args) => context.getVisibleRepos(...args);
  const hasChunkLoadError = (...args) => context.hasChunkLoadError(...args);
  const hexAlpha = (...args) => context.hexAlpha(...args);
  const isComparing = (...args) => context.isComparing(...args);
  const metricInfo = (...args) => context.metricInfo(...args);
  const normalizeChunkLoadError = (...args) => context.normalizeChunkLoadError(...args);
  const normalizeWindow = (...args) => context.normalizeWindow(...args);
  const preferredTheme = (...args) => context.preferredTheme(...args);
  const recordChunkLoadErrors = (...args) => context.recordChunkLoadErrors(...args);
  const renderCollectionCalendar = (...args) => context.renderCollectionCalendar(...args);
  const renderCommunityCell = (...args) => context.renderCommunityCell(...args);
  const renderDashboardNotice = (...args) => context.renderDashboardNotice(...args);
  const renderInsights = (...args) => context.renderInsights(...args);
  const renderMomentum = (...args) => context.renderMomentum(...args);
  const renderPathsTable = (...args) => context.renderPathsTable(...args);
  const renderReferrerTable = (...args) => context.renderReferrerTable(...args);
  const sanitizeSelection = (...args) => context.sanitizeSelection(...args);
  const setMetric = (...args) => context.setMetric(...args);
  const setRepoSort = (...args) => context.setRepoSort(...args);
  const setText = (...args) => context.setText(...args);
  const setThreshold = (...args) => context.setThreshold(...args);
  const setWindow = (...args) => context.setWindow(...args);
  const shiftCalendarMonth = (...args) => context.shiftCalendarMonth(...args);
  const sortRepos = (...args) => context.sortRepos(...args);
  const state = context.state;
  const toggleRepoCompare = (...args) => context.toggleRepoCompare(...args);
  const toggleTheme = (...args) => context.toggleTheme(...args);
  const updateControls = (...args) => context.updateControls(...args);
  const updateDailyChart = (...args) => context.updateDailyChart(...args);
  const updateMetricTabs = (...args) => context.updateMetricTabs(...args);
  const updateStackedChart = (...args) => context.updateStackedChart(...args);
  const updateStats = (...args) => context.updateStats(...args);
  const updateToolbar = (...args) => context.updateToolbar(...args);
  const updateWeekdayChart = (...args) => context.updateWeekdayChart(...args);

    function renderRepoStrip() {
      const strip = document.getElementById('repo-strip');
      const card = document.getElementById('repo-strip-card');
      const hint = document.getElementById('repo-strip-hint');
      if (!strip || !card) return;

      const visible = getVisibleRepos();
      if (visible.length <= 1) {
        card.style.display = 'none';
        return;
      }
      card.style.display = 'grid';

      const maxDays = Math.max(...visible.map((r) => Number(r.days || 0)), 1);
      strip.innerHTML = '';

      visible.forEach((repo) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        const isSelected = state.selectedRepo === repo.name;
        const isCompared = state.compareRepos.includes(repo.name);
        chip.className = 'repo-chip' + (isSelected ? ' selected' : '') + (isCompared ? ' compared' : '');
        const color = getRepoColor(repo.name);
        chip.style.setProperty('--chip-color', color);
        chip.dataset.repo = repo.name;
        chip.setAttribute('aria-pressed', (isSelected || isCompared) ? 'true' : 'false');
        const showDays = Number(repo.days || 0) > 0 && Number(repo.days || 0) < maxDays;
        const meta = showDays ? `<span class="chip-meta">${repo.days}d</span>` : '';
        const mark = isCompared ? '✓' : (isSelected ? '◉' : '');
        chip.innerHTML =
          `<span class="chip-dot" aria-hidden="true"></span>` +
          `<span>${escapeHtml(getShortName(repo.name))}</span>` +
          meta +
          (mark ? `<span class="chip-mark" aria-hidden="true">${mark}</span>` : '');

        const onSelect = function(event) {
          const modifier = !!(event && (event.metaKey || event.ctrlKey || event.shiftKey));
          activateRepo(repo.name, modifier);
        };
        chip.addEventListener('click', onSelect);
        chip.addEventListener('keydown', function(e) {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            activateRepo(repo.name, !!(e.metaKey || e.ctrlKey || e.shiftKey));
          }
        });
        strip.appendChild(chip);
      });

      if (hint) {
        if (isComparing()) hint.textContent = `Comparing ${state.compareRepos.length} · ⌘/Ctrl-click to add or remove`;
        else if (state.selectedRepo) hint.textContent = `Focused on ${getShortName(state.selectedRepo)} · click again to clear`;
        else hint.textContent = 'Click to focus · ⌘/Ctrl-click to compare';
      }
    }

    function renderRepoTable() {
      const container = document.getElementById('repo-table');
      const visible = getVisibleRepos();
      const section = document.getElementById('repo-section');
      if (!visible.length) {
        section.style.display = 'none';
        container.innerHTML = '<p class="empty-msg">No repository totals yet.</p>';
        return;
      }
      if (visible.length <= 1) {
        section.style.display = 'block';
      } else {
        section.style.display = 'block';
      }

      const metric = metricInfo(state.metric);
      const sortKey = state.repoSortKey || metric.key;
      const sortDir = state.repoSortDir || 'desc';
      const repos = sortRepos(visible, sortKey, sortDir);

      const totalForMetric = visible.reduce((acc, r) => acc + Number(r[metric.key] || 0), 0);
      const maxForMetric = Math.max(...visible.map((r) => Number(r[metric.key] || 0)), 1);
      const maxDays = Math.max(...visible.map((r) => Number(r.days || 0)), 1);

      const arrow = (key) => sortKey === key ? (sortDir === 'asc' ? '↑' : '↓') : '↕';
      const headCell = (key, label, numeric) => {
        const cls = ['sortable', sortKey === key ? 'active' : '', numeric ? 'num' : ''].filter(Boolean).join(' ');
        return `<th class="${cls}" data-sort="${key}"><span>${label}</span><span class="arrow">${arrow(key)}</span></th>`;
      };

      let html = '<div class="repo-table-wrap"><table><thead><tr>' +
        '<th class="checkbox-col"></th>' +
        headCell('name', 'Repository') +
        headCell('views', 'Views', true) +
        headCell('uniques', 'Visitors', true) +
        headCell('clones', 'Clones', true) +
        headCell('growth', 'Growth', true) +
        headCell('community', 'Community', true) +
        '<th>Trend</th>' +
        `<th>Share of ${escapeHtml(metric.label.toLowerCase())}</th>` +
        '</tr></thead><tbody>';

      repos.forEach((repo) => {
        const isSelected = state.selectedRepo === repo.name;
        const isCompared = state.compareRepos.includes(repo.name);
        const dimmed = state.selectedRepo && !isSelected;
        const rowClass = [
          'repo-row',
          isSelected ? 'selected' : '',
          isCompared ? 'compared' : '',
          dimmed ? 'dimmed' : ''
        ].filter(Boolean).join(' ');
        const checked = isCompared ? ' checked' : '';
        const value = Number(repo[metric.key] || 0);
        const sharePct = totalForMetric > 0 ? (value / totalForMetric) * 100 : 0;
        const barPct = Math.max(2, (value / maxForMetric) * 100);
        const sparkValues = (repo.series && repo.series[metric.key]) || [];
        const sparkSVG = buildRepoSparkSVG(sparkValues, metric.color);

        const showDaysMeta = Number(repo.days || 0) > 0 && Number(repo.days || 0) < maxDays;
        const daysMeta = showDaysMeta ? `<span class="repo-name-meta">tracked ${repo.days}d of ${maxDays}d</span>` : '';
        html += `
          <tr class="${rowClass}" data-repo="${repo.name}" tabindex="0" role="button" aria-pressed="${isSelected}" aria-label="Focus on ${escapeHtml(getShortName(repo.name))}">
            <td class="checkbox-col"><input type="checkbox" data-repo="${repo.name}"${checked} aria-label="Compare ${escapeHtml(getShortName(repo.name))}"></td>
            <td class="repo-name">
              <span class="repo-name-wrap">
                <span class="repo-color-dot"></span>
                <span>${escapeHtml(repo.name)}${daysMeta}</span>
              </span>
            </td>
            <td class="num mono">${formatNumber(repo.views)}</td>
            <td class="num mono">${formatNumber(repo.uniques)}</td>
            <td class="num mono">${formatNumber(repo.clones)}</td>
            <td class="num mono">
              <span class="growth-cell">
                <span class="growth-row"><strong>${formatSigned(repo.stars_delta)}</strong><span class="growth-label">stars</span><span class="growth-total">(${formatNumber(repo.stars)})</span></span>
                <span class="growth-row"><strong>${formatSigned(repo.subscribers_delta)}</strong><span class="growth-label">watchers</span><span class="growth-total">(${formatNumber(repo.subscribers)})</span></span>
                <span class="growth-row"><strong>${formatSigned(repo.forks_delta)}</strong><span class="growth-label">forks</span><span class="growth-total">(${formatNumber(repo.forks)})</span></span>
              </span>
            </td>
            <td>${renderCommunityCell(repo)}</td>
            <td>${sparkSVG}</td>
            <td>
              <div class="repo-share">
                <div class="repo-bar-track" aria-hidden="true">
                  <div class="repo-bar" data-bar-pct="${barPct.toFixed(1)}"></div>
                </div>
                <span class="repo-share-pct">${sharePct.toFixed(1)}%</span>
              </div>
            </td>
          </tr>`;
      });
      html += '</tbody></table></div>';
      container.innerHTML = html;

      container.querySelectorAll('tr[data-repo]').forEach((row) => {
        row.style.setProperty('--repo-color', getRepoColor(row.dataset.repo));
        const select = function(event) {
          if (event && event.target && event.target.closest('input[type="checkbox"]')) return;
          const modifier = !!(event && (event.metaKey || event.ctrlKey || event.shiftKey));
          activateRepo(row.dataset.repo, modifier);
        };
        row.addEventListener('click', select);
        row.addEventListener('keydown', function(e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(e); }
        });
      });
      container.querySelectorAll('input[type="checkbox"]').forEach((input) => {
        input.addEventListener('click', function(event) { event.stopPropagation(); });
        input.addEventListener('change', function() { toggleRepoCompare(input.dataset.repo, input.checked); });
      });
      container.querySelectorAll('th.sortable').forEach((th) => {
        th.addEventListener('click', function() { setRepoSort(th.dataset.sort); });
      });
      container.querySelectorAll('.repo-bar').forEach((bar) => {
        const pct = Math.max(0, Math.min(100, Number(bar.dataset.barPct || 0)));
        bar.style.width = pct.toFixed(1) + '%';
        bar.style.setProperty(
          '--bar-color',
          `linear-gradient(90deg, ${metric.color}, ${hexAlpha(metric.color, 0.6)})`
        );
      });
    }

    function syncUrlHash() {
      try {
        const params = new URLSearchParams();
        if (state.metric && state.metric !== 'views') params.set('metric', state.metric);
        if (getSelectedWindow() !== getDefaultWindow()) params.set('window', getSelectedWindow());
        if (state.minActivity && state.minActivity !== (dashboardData()?.getMeta()?.default_min_activity || 1)) params.set('min', String(state.minActivity));
        if (state.selectedRepo) params.set('focus', getShortName(state.selectedRepo));
        if (state.compareRepos.length >= 2) params.set('compare', state.compareRepos.map(getShortName).join(','));
        const hash = params.toString();
        const next = hash ? '#' + hash : '';
        if (window.location.hash !== next) {
          history.replaceState(null, '', window.location.pathname + window.location.search + next);
        }
      } catch (_e) { /* ignore */ }
    }

    function applyUrlHash() {
      if (!currentPayload()) return;
      try {
        const raw = (window.location.hash || '').replace(/^#/, '');
        if (!raw) return;
        const params = new URLSearchParams(raw);
        const metric = params.get('metric');
        if (metric && METRICS[metric]) state.metric = metric;
        const windowParam = normalizeWindow(params.get('window'));
        if (windowParam) state.window = windowParam;
        const range = params.get('range');
        if (!windowParam && range === 'recent') state.window = DEFAULT_WINDOW;
        if (!windowParam && range === 'all') state.window = 'all';
        const min = Number(params.get('min'));
        if (Number.isFinite(min) && min >= 0) state.minActivity = Math.floor(min);

        const repoNames = (dashboardData()?.getRepos() || []).map((r) => r.name);
        const matchByShort = (short) => repoNames.find((n) => getShortName(n) === short) || null;

        const focus = params.get('focus');
        if (focus) {
          const m = matchByShort(focus);
          if (m) state.selectedRepo = m;
        }
        const compare = params.get('compare');
        if (compare) {
          const tokens = compare.split(',').map((s) => s.trim()).filter(Boolean);
          const matched = tokens.map(matchByShort).filter(Boolean);
          if (matched.length >= 2) {
            state.compareRepos = matched.slice(0, MAX_COMPARE_REPOS);
            state.selectedRepo = null;
          }
        }
      } catch (_e) { /* ignore */ }
    }

    function repoNamesRequiredForCurrentView() {
      let repoNames;
      if (isComparing()) {
        repoNames = state.compareRepos.slice();
      } else if (state.selectedRepo) {
        repoNames = [state.selectedRepo];
      } else {
        repoNames = getVisibleRepos().map((repo) => repo.name);
      }
      return repoNames.filter((repoName) => !hasChunkLoadError(repoName));
    }

    function loadRepoChunks(repoNames) {
      const data = dashboardData();
      if (!data || !data.isLazy()) {
        return Promise.resolve([]);
      }
      const uniqueRepoNames = [...new Set(repoNames || [])]
        .filter((repoName) => repoName && !data.isRepoLoaded(repoName));
      if (!uniqueRepoNames.length) {
        return Promise.resolve([]);
      }
      return Promise.all(uniqueRepoNames.map((repoName) => {
        return data.loadRepo(repoName).then(() => {
          return { repoName, ok: true };
        }).catch((error) => {
          return {
            repoName,
            ok: false,
            diagnostic: normalizeChunkLoadError(repoName, error)
          };
        });
      }));
    }

    function ensureCurrentRepoChunksLoaded() {
      const data = dashboardData();
      if (!data || !data.isLazy()) {
        return null;
      }
      const missing = repoNamesRequiredForCurrentView();
      if (!missing.some((repoName) => !data.isRepoLoaded(repoName))) {
        return null;
      }
      return loadRepoChunks(missing);
    }

    function handleChunkLoadResults(results) {
      const loaded = results.filter((result) => result.ok).map((result) => result.repoName);
      const failed = results.filter((result) => !result.ok).map((result) => result.diagnostic);
      if (loaded.length) {
        clearChunkLoadErrors(loaded);
      }
      if (failed.length) {
        recordChunkLoadErrors(failed);
      }
      return { loaded, failed };
    }

    function retryFailedChunks() {
      const failedRepos = currentChunkLoadErrors().map((error) => error.repoName);
      if (!failedRepos.length) {
        return;
      }
      loadRepoChunks(failedRepos).then((results) => {
        handleChunkLoadResults(results);
        updateDashboard();
      }).catch((error) => {
        console.error('Unexpected dashboard chunk retry failure', error);
      });
    }

    function copyChunkDiagnostics() {
      if (!navigator.clipboard || !navigator.clipboard.writeText) {
        return;
      }
      navigator.clipboard.writeText(chunkDiagnosticsText(currentChunkLoadErrors())).catch((error) => {
        console.error('Failed to copy dashboard chunk diagnostics', error);
      });
    }

    function handleNoticeAction(event) {
      const button = event.target.closest('[data-notice-action]');
      if (!button) {
        return;
      }
      if (button.dataset.noticeAction === 'retry-chunks') {
        retryFailedChunks();
      } else if (button.dataset.noticeAction === 'copy-diagnostics') {
        copyChunkDiagnostics();
        button.textContent = 'Copied';
        setTimeout(() => { button.textContent = 'Copy details'; }, 1200);
      }
    }

    function updateDashboard() {
      const payload = currentPayload();
      if (!payload) {
        return;
      }
      const pendingChunks = ensureCurrentRepoChunksLoaded();
      if (pendingChunks) {
        pendingChunks.then(function(results) {
          handleChunkLoadResults(results);
          updateDashboard();
        }).catch(function(error) {
          console.error('Unexpected dashboard chunk load failure', error);
        });
        return;
      }
      sanitizeSelection();
      syncUrlHash();
      const dashboardApp = document.getElementById('dashboard-app');
      dashboardApp.classList.remove('dashboard-hidden');
      ensureCharts();
      updateControls();
      updateMetricTabs();
      setText('updated-text', buildUpdatedText(payload));
      updateToolbar();
      renderDashboardNotice();
      renderCollectionCalendar();
      updateStats();
      updateDailyChart();
      updateWeekdayChart();
      updateStackedChart();
      renderReferrerTable(getCurrentReferrerRows());
      renderPathsTable(getCurrentPathRows());
      renderMomentum();
      renderInsights();
      renderRepoStrip();
      renderRepoTable();
    }

    function renderDashboard(payload) {
      state.dashboardData = createDashboardDataProvider(payload);
      const meta = dashboardData()?.getMeta() || {};
      state.window = getDefaultWindow();
      state.minActivity = meta.default_min_activity || 1;
      state.selectedRepo = null;
      state.compareRepos = [];
      state.chunkLoadErrors = {};
      state.calendarMonth = null;
      const thresholdInput = document.getElementById('thresholdInput');
      if (thresholdInput) {
        thresholdInput.addEventListener('change', function() {
          setThreshold(thresholdInput.value);
        });
        thresholdInput.addEventListener('input', function() {
          document.getElementById('thresholdValue').textContent = formatNumber(Math.max(0, Math.floor(Number(thresholdInput.value || 0))));
        });
      }
      document.querySelectorAll('[data-window]').forEach((btn) => {
        btn.addEventListener('click', function() { setWindow(btn.dataset.window); });
      });
      document.querySelectorAll('.metric-tab').forEach((btn) => {
        btn.addEventListener('click', function() { setMetric(btn.dataset.metric); });
      });
      const calendarPrevBtn = document.getElementById('calendarPrevBtn');
      const calendarNextBtn = document.getElementById('calendarNextBtn');
      if (calendarPrevBtn) calendarPrevBtn.addEventListener('click', function() { shiftCalendarMonth(-1); });
      if (calendarNextBtn) calendarNextBtn.addEventListener('click', function() { shiftCalendarMonth(1); });
      const clearButton = document.getElementById('clearSelectionBtn');
      if (clearButton) clearButton.addEventListener('click', clearSelection);
      const noticeRegion = document.getElementById('dashboard-notice-region');
      if (noticeRegion) noticeRegion.addEventListener('click', handleNoticeAction);
      const themeToggle = document.getElementById('themeToggle');
      if (themeToggle) themeToggle.addEventListener('click', toggleTheme);
      // Sync the toggle button's icon/label with the bootstrap-applied theme.
      applyTheme(preferredTheme(), false);
      try {
        const mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)');
        if (mq && mq.addEventListener) {
          mq.addEventListener('change', function() {
            try {
              const saved = localStorage.getItem(THEME_KEY);
              if (!saved) applyTheme(mq.matches ? 'light' : 'dark', false);
            } catch (_e) { /* ignore */ }
          });
        }
      } catch (_e) { /* ignore */ }
      applyUrlHash();
      window.addEventListener('hashchange', function() {
        applyUrlHash();
        updateDashboard();
      });
      updateDashboard();
    }

  return { renderRepoStrip, renderRepoTable, syncUrlHash, applyUrlHash, repoNamesRequiredForCurrentView, loadRepoChunks, ensureCurrentRepoChunksLoaded, handleChunkLoadResults, retryFailedChunks, copyChunkDiagnostics, handleNoticeAction, updateDashboard, renderDashboard };
}


    // Categorical palette for the per-repo lines. Drawn from the
    // Okabe-Ito + Paul Tol palettes, designed to remain
    // distinguishable under protanopia / deuteranopia / tritanopia
    // and on both light and dark backgrounds. The first six entries
    // are the ones typical demos and small portfolios will hit; they
    // were ordered for maximum mutual contrast at the small-N
    // (≤ 6 repos) case.
    const palette = [
      '#56B4E9',  // sky blue
      '#E69F00',  // orange
      '#009E73',  // bluish green
      '#CC79A7',  // pink
      '#0072B2',  // dark blue
      '#D55E00',  // vermillion
      '#F0E442',  // yellow
      '#44AA99',  // teal
      '#AA4499',  // purple
      '#882255',  // mulberry
    ];
    // Dash patterns rotate alongside the palette so repos differ by
    // both hue *and* line texture — important when adjacent palette
    // entries (e.g. yellow-ochre vs red) are confusable for users
    // with red-green color deficiency.
    const DASH_PATTERNS = [
      [],            // solid
      [6, 4],        // long dash
      [2, 3],        // dotted
      [8, 3, 2, 3],  // dash-dot
      [4, 2],        // medium dash
    ];
    function dashForRepoIndex(idx) {
      return DASH_PATTERNS[idx % DASH_PATTERNS.length];
    }
    function getRepoDash(repoName) {
      const repos = dashboardData()?.getRepos() || [];
      const idx = repos.findIndex((repo) => repo.name === repoName);
      return dashForRepoIndex(idx >= 0 ? idx : 0);
    }
    const METRICS = {
      views:    { key: 'views',         label: 'Views',         color: '#58a6ff' },
      uniques:  { key: 'uniques',       label: 'Visitors',      color: '#3fb950' },
      clones:   { key: 'clones',        label: 'Clones',        color: '#CC79A7' },
      cloners:  { key: 'clone_uniques', label: 'Unique Clones', color: '#ffa657' },
      stars:    { key: 'stars_delta',   label: 'Star Growth',   color: '#bf6a02', growth: true },
      subscribers: { key: 'subscribers_delta', label: 'Watcher Growth', color: '#1f6feb', growth: true },
      forks:    { key: 'forks_delta',   label: 'Fork Growth',   color: '#3fb950', growth: true }
    };
    const WINDOW_PRESETS = ['7', '14', '30', '90', 'all'];
    const DEFAULT_WINDOW = '14';
    const MAX_DISPLAY_REPOS = 20;
    const state = {
      dashboardData: null,
      window: DEFAULT_WINDOW,
      minActivity: 1,
      selectedRepo: null,
      compareRepos: [],
      metric: 'views',
      repoSortKey: null,
      repoSortDir: null,
      calendarMonth: null
    };
    function createDashboardDataProvider(input) {
      const isLazy = !!(input && input.summary && (input.loadRepoChunk || input.chunks));
      const source = isLazy ? input.summary : (input || {});
      const loadedChunks = {};
      const pendingChunks = {};
      function chunkFor(repoName) {
        return loadedChunks[repoName] || null;
      }
      function chunkIdFor(repoName) {
        return source.repo_chunks?.[repoName] || null;
      }
      function parsePlainChunk(repoName) {
        const chunkId = chunkIdFor(repoName);
        const rawChunk = chunkId ? input.chunks?.[chunkId] : null;
        if (!rawChunk) {
          throw new Error('Missing dashboard chunk for ' + repoName);
        }
        const chunk = typeof rawChunk === 'string' ? JSON.parse(rawChunk) : rawChunk;
        if (!chunk || chunk.repo !== repoName) {
          throw new Error('Dashboard chunk did not match requested repo');
        }
        return chunk;
      }
      function loadChunk(repoName) {
        if (input.loadRepoChunk) {
          return input.loadRepoChunk(repoName);
        }
        return Promise.resolve(parsePlainChunk(repoName));
      }
      return {
        getPayload: function() { return source; },
        isLazy: function() { return isLazy; },
        getMeta: function() { return source.meta || {}; },
        getRepos: function() { return source.repos || []; },
        getRepoSummary: function(repoName) {
          return (source.repos || []).find((repo) => repo.name === repoName) || {};
        },
        getRepoSeries: function(repoName) {
          return chunkFor(repoName)?.repo_series || source.repo_series?.[repoName] || {};
        },
        getRepoWeekday: function(repoName) {
          return chunkFor(repoName)?.repo_weekday || source.repo_weekday?.[repoName] || {};
        },
        getRepoGrowth: function(repoName) {
          return chunkFor(repoName)?.growth?.per_repo || source.growth?.per_repo?.[repoName] || {};
        },
        getRepoReferrers: function(repoName) {
          return chunkFor(repoName)?.repo_referrers || source.repo_referrers?.[repoName] || [];
        },
        getRepoPaths: function(repoName) {
          return chunkFor(repoName)?.repo_paths || source.repo_paths?.[repoName] || [];
        },
        getReferrersByRepo: function() {
          if (!isLazy) return source.repo_referrers || {};
          return Object.fromEntries(
            Object.keys(loadedChunks).map((repoName) => [
              repoName,
              loadedChunks[repoName].repo_referrers || []
            ])
          );
        },
        getPathsByRepo: function() {
          if (!isLazy) return source.repo_paths || {};
          return Object.fromEntries(
            Object.keys(loadedChunks).map((repoName) => [
              repoName,
              loadedChunks[repoName].repo_paths || []
            ])
          );
        },
        isRepoLoaded: function(repoName) {
          return !isLazy || !!loadedChunks[repoName];
        },
        loadRepo: function(repoName) {
          if (!isLazy || !repoName || loadedChunks[repoName]) {
            return Promise.resolve(loadedChunks[repoName] || null);
          }
          if (!pendingChunks[repoName]) {
            pendingChunks[repoName] = loadChunk(repoName).then((chunk) => {
              loadedChunks[repoName] = chunk;
              delete pendingChunks[repoName];
              return chunk;
            }).catch((error) => {
              delete pendingChunks[repoName];
              throw error;
            });
          }
          return pendingChunks[repoName];
        }
      };
    }
    function dashboardData() {
      return state.dashboardData;
    }
    function currentPayload() {
      return dashboardData()?.getPayload() || null;
    }
    function metricInfo(key) {
      const info = METRICS[key] || METRICS.views;
      return Object.assign({}, info, { color: themeMetricColor(info.key) || info.color });
    }
    function hexAlpha(hex, alpha) {
      const a = Math.round(Math.max(0, Math.min(1, alpha)) * 255).toString(16).padStart(2, '0');
      return hex + a;
    }
    function getThemeColor(varName, fallback) {
      try {
        const v = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
        return v || fallback || '';
      } catch (_e) { return fallback || ''; }
    }
    function themeMetricColor(seriesKey) {
      const map = { views: '--c-views', uniques: '--c-uniques', clones: '--c-clones', clone_uniques: '--c-cloners', stars_delta: '--accent-2', subscribers_delta: '--accent', forks_delta: '--c-uniques' };
      return getThemeColor(map[seriesKey], '');
    }
    const THEME_KEY = 'reponomics-theme';
    function preferredTheme() {
      try {
        const saved = localStorage.getItem(THEME_KEY);
        if (saved === 'light' || saved === 'dark') return saved;
      } catch (_e) { /* ignore */ }
      try {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) return 'light';
      } catch (_e) { /* ignore */ }
      return 'dark';
    }
    function applyTheme(theme, persist) {
      const root = document.documentElement;
      if (theme === 'light') root.setAttribute('data-theme', 'light');
      else root.removeAttribute('data-theme');
      if (persist) {
        try { localStorage.setItem(THEME_KEY, theme); } catch (_e) { /* ignore */ }
      }
      document.querySelectorAll('.theme-toggle').forEach((toggle) => {
        const icon = toggle.querySelector('.theme-icon');
        const label = toggle.querySelector('.theme-label');
        if (icon) icon.textContent = theme === 'light' ? '☀' : '☾';
        if (label) label.textContent = theme === 'light' ? 'Light' : 'Dark';
        toggle.setAttribute('aria-pressed', theme === 'light' ? 'true' : 'false');
      });
      refreshCharts();
    }
    function toggleTheme() {
      const next = (document.documentElement.getAttribute('data-theme') === 'light') ? 'dark' : 'light';
      applyTheme(next, true);
    }
    function refreshCharts() {
      // Skip work entirely until charts exist; the first updateDashboard()
      // will pick up theme colors from CSS vars on its own.
      if (!dailyChart && !weekdayChart && !stackedChart) return;
      const newOpts = chartOptions(false);
      if (dailyChart) {
        Object.assign(dailyChart.options, newOpts);
        dailyChart.update('none');
      }
      if (weekdayChart) {
        // weekday uses its own option block — patch the text/grid colors
        const tickColor = getThemeColor('--text-muted', '#8b949e');
        const gridColor = getThemeColor('--chart-grid', 'rgba(38, 45, 56, 0.4)');
        const axisColor = getThemeColor('--chart-axis', 'rgba(38, 45, 56, 0.7)');
        weekdayChart.options.scales.x.ticks.color = tickColor;
        weekdayChart.options.scales.y.ticks.color = tickColor;
        weekdayChart.options.scales.y.grid.color = gridColor;
        if (weekdayChart.options.scales.x.border) weekdayChart.options.scales.x.border.color = axisColor;
        if (weekdayChart.options.plugins?.tooltip) {
          weekdayChart.options.plugins.tooltip.backgroundColor = getThemeColor('--chart-tooltip-bg', 'rgba(17, 22, 29, 0.96)');
          weekdayChart.options.plugins.tooltip.borderColor = getThemeColor('--chart-tooltip-border', '#262d38');
          weekdayChart.options.plugins.tooltip.titleColor = getThemeColor('--text', '#e6edf3');
          weekdayChart.options.plugins.tooltip.bodyColor = getThemeColor('--text', '#e6edf3');
        }
        weekdayChart.update('none');
      }
      if (stackedChart) {
        const stackedOpts = chartOptions(true);
        // Preserve stack flag set elsewhere
        const wasStacked = stackedChart.options.scales?.y?.stacked;
        Object.assign(stackedChart.options, stackedOpts);
        if (stackedChart.options.scales && stackedChart.options.scales.y) {
          stackedChart.options.scales.y.stacked = !!wasStacked;
        }
        stackedChart.update('none');
      }
      if (currentPayload()) updateDashboard();
    }
    let dailyChart = null;
    let weekdayChart = null;
    let stackedChart = null;

    function formatNumber(value) {
      return Number(value || 0).toLocaleString();
    }

    function compactNumber(value) {
      const n = Number(value || 0);
      const abs = Math.abs(n);
      if (abs >= 1_000_000) return (n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1) + 'M';
      if (abs >= 1_000) return (n / 1_000).toFixed(n >= 10_000 ? 0 : 1) + 'k';
      return String(Math.round(n));
    }

    function formatSigned(value) {
      const n = Number(value || 0);
      return (n >= 0 ? '+' : '') + formatNumber(n);
    }

    function sumArray(values) {
      return (values || []).reduce((total, value) => total + Number(value || 0), 0);
    }

    function buildSparklinePath(values, width, height) {
      const n = (values || []).length;
      if (!n) { return { line: '', area: '' }; }
      if (n === 1) {
        const y = height / 2;
        return { line: `M0 ${y.toFixed(2)} L${width} ${y.toFixed(2)}`, area: '' };
      }
      const max = Math.max(...values);
      const min = Math.min(...values);
      const range = max - min || 1;
      const pad = 2;
      const innerH = height - pad * 2;
      const pts = values.map((v, i) => {
        const x = (i / (n - 1)) * width;
        const y = pad + (1 - (Number(v || 0) - min) / range) * innerH;
        return [x, y];
      });
      const line = pts.map(([x, y], i) => (i === 0 ? 'M' : 'L') + x.toFixed(2) + ' ' + y.toFixed(2)).join(' ');
      const area = line + ` L${width} ${height} L0 ${height} Z`;
      return { line, area };
    }

    function renderSparkline(id, values, color) {
      const el = document.getElementById(id);
      if (!el) return;
      if (!values || values.length < 2) {
        el.innerHTML = '';
        return;
      }
      const { line, area } = buildSparklinePath(values, 100, 34);
      // pathLength="1" normalizes the path's apparent stroke length to 1
      // unit so the CSS draw-in animation (stroke-dasharray: 1) always
      // covers the entire line regardless of how spiky the underlying
      // data is. Without this, jagged metrics (Views, Visitors) had path
      // lengths that exceeded the dash and clipped the tail.
      el.innerHTML =
        `<path class="area" d="${area}" fill="${color}"></path>` +
        `<path class="line" d="${line}" stroke="${color}" pathLength="1"></path>`;
    }

    function splitWindow(series) {
      const dates = (series && series.dates) || [];
      if (dates.length < 2) return null;
      const mid = Math.ceil(dates.length / 2);
      const slice = (arr) => ({
        first: (arr || []).slice(0, mid),
        second: (arr || []).slice(mid)
      });
      return {
        views: slice(series.views),
        uniques: slice(series.uniques),
        clones: slice(series.clones),
        clone_uniques: slice(series.clone_uniques),
        firstDays: mid,
        secondDays: dates.length - mid
      };
    }

    function computeDelta(split, field) {
      if (!split) return null;
      const f = split[field];
      if (!f) return null;
      const prior = sumArray(f.first);
      const current = sumArray(f.second);
      if (prior === 0 && current === 0) return null;
      // Prior window had no data (brand-new repo, or first collection
      // window). Percentage is undefined; omit the pill rather than
      // pretending we know the delta.
      if (prior === 0) return null;
      const pct = ((current - prior) / prior) * 100;
      let direction = 'flat';
      if (pct > 2) direction = 'up';
      else if (pct < -2) direction = 'down';
      return { pct, direction, current, prior };
    }

    function renderDelta(id, delta) {
      const el = document.getElementById(id);
      if (!el) return;
      if (!delta) {
        el.className = 'stat-delta hidden';
        el.textContent = '';
        return;
      }
      let label;
      if (delta.pct === null) {
        label = delta.label || 'new';
      } else {
        const sign = delta.pct >= 0 ? '+' : '';
        const arrow = delta.direction === 'up' ? '▲' : delta.direction === 'down' ? '▼' : '•';
        const rounded = Math.abs(delta.pct) >= 100 ? Math.round(delta.pct) : delta.pct.toFixed(1);
        label = `${arrow} ${sign}${rounded}%`;
      }
      el.className = 'stat-delta ' + (delta.direction || 'flat');
      el.textContent = label;
    }

    function escapeHtml(text) {
      const d = document.createElement('div');
      d.appendChild(document.createTextNode(text == null ? '' : String(text)));
      return d.innerHTML;
    }

    function setText(id, value) {
      const el = document.getElementById(id);
      if (el) {
        el.textContent = value;
      }
    }

    function getShortName(repoName) {
      if (!repoName) {
        return '';
      }
      const parts = String(repoName).split('/');
      return parts[parts.length - 1] || repoName;
    }

    function getRepoByName(repoName) {
      if (!repoName || !dashboardData()?.getRepoSummary(repoName)?.name) {
        return null;
      }
      const repo = buildRepoMetrics(repoName);
      return repo.activity >= state.minActivity ? repo : null;
    }

    function getRepoColor(repoName) {
      const repos = dashboardData()?.getRepos() || [];
      const idx = repos.findIndex((repo) => repo.name === repoName);
      return palette[(idx >= 0 ? idx : 0) % palette.length];
    }

    function isComparing() {
      return state.compareRepos.length >= 2;
    }

    function normalizeWindow(value) {
      const raw = String(value || '').trim().toLowerCase();
      if (raw === 'recent') return DEFAULT_WINDOW;
      if (WINDOW_PRESETS.includes(raw)) return raw;
      return null;
    }

    function getDefaultWindow() {
      return (
        normalizeWindow(dashboardData()?.getMeta()?.default_window) ||
        normalizeWindow(dashboardData()?.getMeta()?.default_range) ||
        DEFAULT_WINDOW
      );
    }

    function getSelectedWindow() {
      return normalizeWindow(state.window) || getDefaultWindow();
    }

    function getWindowDays() {
      const selected = getSelectedWindow();
      return selected === 'all' ? null : Number(selected);
    }

    function getRangeLabel() {
      const days = getWindowDays();
      return days === null ? 'All retained data' : 'Last ' + days + ' collected days';
    }

    function parseIsoDate(value) {
      if (!value) {
        return null;
      }
      const parts = String(value).split('-').map(Number);
      if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) {
        return null;
      }
      return new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
    }

    function formatIsoDate(date) {
      return date.toISOString().slice(0, 10);
    }

    function getWindowCutoffDate() {
      const days = getWindowDays();
      if (days === null) {
        return null;
      }
      const dates = currentPayload()?.daily?.dates || [];
      if (!dates.length) {
        return null;
      }
      const latest = parseIsoDate(dates[dates.length - 1]);
      if (!latest) {
        return null;
      }
      const cutoff = new Date(latest.getTime());
      cutoff.setUTCDate(cutoff.getUTCDate() - (days - 1));
      return formatIsoDate(cutoff);
    }

    function qualityDaysForSelectedWindow() {
      const allDays = applyVisibilityThresholdToQualityDays(
        (currentPayload()?.data_quality?.days || []).slice()
      );
      if (!allDays.length) return [];
      if (getSelectedWindow() === 'all') return allDays;
      const cutoff = getWindowCutoffDate();
      if (!cutoff) return allDays;
      return allDays.filter((day) => String(day.date || '') >= cutoff);
    }

    function summarizeQualityDayStatuses(day, repos) {
      const counts = {
        ok_with_data: 0,
        ok_zero_data: 0,
        skipped_unavailable: 0,
        error: 0,
        error_secondary_rate_limit: 0,
      };
      (repos || []).forEach((row) => {
        const status = String(row?.status || '');
        if (status in counts) counts[status] += 1;
      });
      const trackedRepos = (repos || []).length;
      const withDataRepos = counts.ok_with_data;
      const zeroTrafficRepos = counts.ok_zero_data;
      const skippedRepos = counts.skipped_unavailable;
      const errorRepos = counts.error + counts.error_secondary_rate_limit;
      const observedRepos = withDataRepos + zeroTrafficRepos;
      const hasCollectionGaps = skippedRepos > 0 || errorRepos > 0;
      let status = 'healthy';
      if (hasCollectionGaps) status = 'gaps_detected';
      else if (trackedRepos > 0 && zeroTrafficRepos === trackedRepos) status = 'all_zero';
      return {
        ...day,
        status,
        has_collection_gaps: hasCollectionGaps,
        tracked_repos: trackedRepos,
        with_data_repos: withDataRepos,
        zero_traffic_repos: zeroTrafficRepos,
        skipped_repos: skippedRepos,
        error_repos: errorRepos,
        coverage_ratio: trackedRepos ? Math.round((observedRepos / trackedRepos) * 10000) / 10000 : 1,
        repos: repos || [],
      };
    }

    function applyVisibilityThresholdToQualityDays(days) {
      const hasRepoBreakdown = (days || []).some((day) => Array.isArray(day?.repos));
      if (!hasRepoBreakdown) return days;
      const visibleRepoNames = new Set(getVisibleRepos().map((repo) => repo.name));
      if (!visibleRepoNames.size) return [];
      return (days || [])
        .map((day) => {
          const dayRepos = Array.isArray(day?.repos) ? day.repos : [];
          const filtered = dayRepos.filter((row) => visibleRepoNames.has(String(row?.repo || '')));
          return summarizeQualityDayStatuses(day, filtered);
        })
        .filter((day) => Number(day?.tracked_repos || 0) > 0);
    }

    function monthKeyFromIsoDate(value) {
      const raw = String(value || '');
      return raw.length >= 7 ? raw.slice(0, 7) : '';
    }

    function parseMonthKey(key) {
      if (!/^\d{4}-\d{2}$/.test(String(key || ''))) return null;
      const year = Number(key.slice(0, 4));
      const month = Number(key.slice(5, 7));
      if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) return null;
      return { year, month };
    }

    function monthLabelFromKey(key) {
      const parsed = parseMonthKey(key);
      if (!parsed) return 'No data';
      const date = new Date(Date.UTC(parsed.year, parsed.month - 1, 1));
      return date.toLocaleString(undefined, { month: 'long', year: 'numeric', timeZone: 'UTC' });
    }

    function latestMonthKeyFallback() {
      const qualityDays = currentPayload()?.data_quality?.days || [];
      if (qualityDays.length) {
        return monthKeyFromIsoDate(qualityDays[qualityDays.length - 1].date);
      }
      const dates = currentPayload()?.daily?.dates || [];
      if (dates.length) {
        return monthKeyFromIsoDate(dates[dates.length - 1]);
      }
      return '';
    }

    function calendarMonthKeys(days) {
      const keys = Array.from(new Set((days || []).map((day) => monthKeyFromIsoDate(day.date)).filter(Boolean))).sort();
      if (keys.length) return keys;
      const fallback = latestMonthKeyFallback();
      return fallback ? [fallback] : [];
    }

    function resolveCalendarMonth(days, monthKeys) {
      if (!monthKeys.length) {
        state.calendarMonth = null;
        return null;
      }
      if (!state.calendarMonth || !monthKeys.includes(state.calendarMonth)) {
        state.calendarMonth = monthKeys[monthKeys.length - 1];
      }
      return state.calendarMonth;
    }

    function daysInMonth(year, month) {
      return new Date(Date.UTC(year, month, 0)).getUTCDate();
    }

    function calendarStatusLabel(day) {
      if (!day) return 'no-run';
      if (day.has_collection_gaps) return 'gap';
      if (String(day.status || '') === 'all_zero') return 'all-zero';
      return 'healthy';
    }

    function formatCalendarDayTooltip(day) {
      const statusLabel = calendarStatusLabel(day);
      const parts = [
        `${day.date} · status: ${statusLabel}`,
        `tracked ${formatNumber(day.tracked_repos || 0)}`,
        `with data ${formatNumber(day.with_data_repos || 0)}`,
        `zero ${formatNumber(day.zero_traffic_repos || 0)}`,
        `skipped ${formatNumber(day.skipped_repos || 0)}`,
        `errors ${formatNumber(day.error_repos || 0)}`
      ];
      if (Number(day.run_count || 0) > 1) {
        parts.push(`${formatNumber(day.run_count)} runs`);
      }
      return parts.join(' · ');
    }

    function renderCollectionCalendar() {
      const panel = document.getElementById('calendar-panel');
      const monthLabel = document.getElementById('calendarMonthLabel');
      const grid = document.getElementById('calendarGrid');
      const hint = document.getElementById('calendarHint');
      const dayDetail = document.getElementById('calendarDayDetail');
      const prevBtn = document.getElementById('calendarPrevBtn');
      const nextBtn = document.getElementById('calendarNextBtn');
      if (!panel || !monthLabel || !grid || !hint || !dayDetail || !prevBtn || !nextBtn) return;

      const days = qualityDaysForSelectedWindow();
      const monthKeys = calendarMonthKeys(days);
      const activeMonth = resolveCalendarMonth(days, monthKeys);
      const monthIndex = activeMonth ? monthKeys.indexOf(activeMonth) : -1;
      prevBtn.disabled = monthIndex <= 0;
      nextBtn.disabled = monthIndex < 0 || monthIndex >= monthKeys.length - 1;

      if (!activeMonth) {
        panel.style.display = 'none';
        dayDetail.textContent = '';
        return;
      }

      panel.style.display = '';
      monthLabel.textContent = monthLabelFromKey(activeMonth);

      const parsed = parseMonthKey(activeMonth);
      if (!parsed) {
        grid.innerHTML = '';
        hint.textContent = 'Collection status per day in the selected window.';
        dayDetail.textContent = 'Hover or focus a day to inspect collection details.';
        return;
      }

      const byDate = new Map((days || []).map((day) => [String(day.date || ''), day]));
      const firstDay = new Date(Date.UTC(parsed.year, parsed.month - 1, 1));
      const leading = (firstDay.getUTCDay() + 6) % 7;
      const count = daysInMonth(parsed.year, parsed.month);

      const cells = [];
      for (let i = 0; i < leading; i += 1) {
        cells.push('<span class="calendar-day blank" aria-hidden="true"></span>');
      }
      for (let dayNum = 1; dayNum <= count; dayNum += 1) {
        const iso = `${parsed.year}-${String(parsed.month).padStart(2, '0')}-${String(dayNum).padStart(2, '0')}`;
        const day = byDate.get(iso);
        let cls = 'calendar-day no-run';
        let detail = `${iso} · status: no-run · no collection run`;
        let title = detail;
        if (day) {
          if (day.has_collection_gaps) cls = 'calendar-day gap';
          else if (day.status === 'all_zero') cls = 'calendar-day zero';
          else cls = 'calendar-day ok';
          detail = formatCalendarDayTooltip(day);
          title = detail;
        }
        cells.push(
          `<span class="${cls}" title="${escapeHtml(title)}" data-detail="${escapeHtml(detail)}" tabindex="0">${dayNum}</span>`
        );
      }
      const trailing = (7 - (cells.length % 7)) % 7;
      for (let i = 0; i < trailing; i += 1) {
        cells.push('<span class="calendar-day blank" aria-hidden="true"></span>');
      }
      grid.innerHTML = cells.join('');
      const defaultDayDetail = 'Hover or focus a day to inspect collection details.';
      dayDetail.textContent = defaultDayDetail;
      grid.querySelectorAll('.calendar-day:not(.blank)').forEach((cell) => {
        const showDetail = function() {
          const detail = cell.getAttribute('data-detail') || '';
          dayDetail.textContent = detail || defaultDayDetail;
        };
        const resetDetail = function() {
          dayDetail.textContent = defaultDayDetail;
        };
        cell.addEventListener('mouseenter', showDetail);
        cell.addEventListener('focus', showDetail);
        cell.addEventListener('click', showDetail);
        cell.addEventListener('mouseleave', resetDetail);
        cell.addEventListener('blur', resetDetail);
      });

      const gapDays = days.filter((day) => day.has_collection_gaps).length;
      const zeroDays = days.filter((day) => day.status === 'all_zero').length;
      const noRunStats = computeNoRunStats(days);
      const streakText = noRunStats.longestNoRunStreak > 0
        ? ` (longest streak ${formatNumber(noRunStats.longestNoRunStreak)})`
        : '';
      hint.textContent = (
        `${formatNumber(noRunStats.collectedDays)} collected day(s), `
        + `${formatNumber(noRunStats.noRunDays)} no-run day(s)${streakText}, `
        + `${formatNumber(gapDays)} gap day(s), `
        + `${formatNumber(zeroDays)} all-zero day(s).`
      );
    }

    function shiftCalendarMonth(delta) {
      const days = qualityDaysForSelectedWindow();
      const monthKeys = calendarMonthKeys(days);
      if (!monthKeys.length) return;
      const activeMonth = resolveCalendarMonth(days, monthKeys);
      const index = Math.max(0, monthKeys.indexOf(activeMonth));
      const nextIndex = Math.min(monthKeys.length - 1, Math.max(0, index + delta));
      state.calendarMonth = monthKeys[nextIndex];
      renderCollectionCalendar();
    }

    function computeNoRunStats(days) {
      const collectedDates = Array.from(
        new Set((days || []).map((day) => String(day.date || '')).filter(Boolean))
      ).sort();
      if (!collectedDates.length) {
        return {
          collectedDays: 0,
          noRunDays: 0,
          longestNoRunStreak: 0
        };
      }

      const start = parseIsoDate(collectedDates[0]);
      const end = parseIsoDate(collectedDates[collectedDates.length - 1]);
      if (!start || !end) {
        return {
          collectedDays: collectedDates.length,
          noRunDays: 0,
          longestNoRunStreak: 0
        };
      }

      const collectedSet = new Set(collectedDates);
      const cursor = new Date(start.getTime());
      let noRunDays = 0;
      let streak = 0;
      let longestNoRunStreak = 0;

      while (cursor.getTime() <= end.getTime()) {
        const iso = formatIsoDate(cursor);
        if (collectedSet.has(iso)) {
          streak = 0;
        } else {
          noRunDays += 1;
          streak += 1;
          if (streak > longestNoRunStreak) longestNoRunStreak = streak;
        }
        cursor.setUTCDate(cursor.getUTCDate() + 1);
      }

      return {
        collectedDays: collectedDates.length,
        noRunDays,
        longestNoRunStreak
      };
    }

    function seriesForRange(series) {
      if (!series) {
        return {
          dates: [],
          views: [],
          uniques: [],
          clones: [],
          clone_uniques: [],
          stars_delta: [],
          subscribers_delta: [],
          forks_delta: []
        };
      }
      if (getSelectedWindow() === 'all') {
        return series;
      }

      const cutoff = getWindowCutoffDate();
      if (!cutoff) {
        return series;
      }

      const windowed = {};
      Object.keys(series).forEach((key) => {
        windowed[key] = Array.isArray(series[key]) ? [] : series[key];
      });
      (series.dates || []).forEach((date, idx) => {
        if (date >= cutoff) {
          Object.keys(windowed).forEach((key) => {
            if (!Array.isArray(windowed[key])) return;
            windowed[key].push(key === 'dates' ? date : (series[key] || [])[idx] || 0);
          });
        }
      });
      if ('samples' in windowed) {
        windowed.samples = (windowed.dates || []).length;
      }
      return windowed;
    }

    function latestSeriesValue(series, key, fallback) {
      const values = (series && series[key]) || [];
      if (!values.length) return Number(fallback || 0);
      return Number(values[values.length - 1] || 0);
    }

    function seriesDelta(series, key, fallback) {
      const values = (series && series[key]) || [];
      if (values.length < 2) {
        return values.length === 1 ? 0 : Number(fallback || 0);
      }
      return Number(values[values.length - 1] || 0) - Number(values[0] || 0);
    }

    function buildRepoMetrics(repoName) {
      const data = dashboardData();
      const baseRepo = data?.getRepoSummary(repoName) || {};
      const series = seriesForRange(data?.getRepoSeries(repoName));
      const growthRow = data?.getRepoGrowth(repoName) || {};
      const deltas = growthRow.deltas || {};
      const growthSeries = seriesForRange(growthRow.series || {});
      const sum = (values) => (values || []).reduce((total, value) => total + Number(value || 0), 0);
      const hasSeries = (series.dates || []).length > 0;
      const starsDelta = seriesDelta(growthSeries, 'stargazers', deltas.stars_delta || deltas.stargazers_delta);
      const subscribersDelta = seriesDelta(growthSeries, 'subscribers', deltas.subscribers_delta);
      const forksDelta = seriesDelta(growthSeries, 'forks', deltas.forks_delta);
      const community = baseRepo.community || {};
      const communityHealth = Number(community.health_percentage);
      return {
        name: repoName,
        views: hasSeries ? sum(series.views) : Number(baseRepo.views || 0),
        uniques: hasSeries ? sum(series.uniques) : Number(baseRepo.uniques || 0),
        clones: hasSeries ? sum(series.clones) : Number(baseRepo.clones || 0),
        clone_uniques: hasSeries ? sum(series.clone_uniques) : Number(baseRepo.clone_uniques || 0),
        stars_delta: starsDelta,
        subscribers_delta: subscribersDelta,
        forks_delta: forksDelta,
        stars: latestSeriesValue(growthSeries, 'stargazers', deltas.current_stars || deltas.current_stargazers),
        subscribers: latestSeriesValue(growthSeries, 'subscribers', deltas.current_subscribers),
        forks: latestSeriesValue(growthSeries, 'forks', deltas.current_forks),
        days: hasSeries ? (series.dates || []).length : Number(baseRepo.days || 0),
        activity: (hasSeries ? sum(series.views) : Number(baseRepo.views || 0))
          + (hasSeries ? sum(series.clones) : Number(baseRepo.clones || 0)),
        community: {
          available: !!community.available,
          health_percentage: Number.isFinite(communityHealth) ? communityHealth : null,
          documentation: String(community.documentation || ''),
          updated_at: String(community.updated_at || ''),
          content_reports_enabled: community.content_reports_enabled,
          has_code_of_conduct: community.has_code_of_conduct,
          has_contributing: community.has_contributing,
          has_issue_template: community.has_issue_template,
          has_pull_request_template: community.has_pull_request_template,
          has_readme: community.has_readme,
          has_license: community.has_license
        },
        series
      };
    }

    function getAllRepoMetrics() {
      return (dashboardData()?.getRepos() || [])
        .map((repo) => buildRepoMetrics(repo.name))
        .sort((a, b) => (b.views - a.views) || (b.clones - a.clones) || a.name.localeCompare(b.name));
    }

    function getSelectableRepos() {
      return getAllRepoMetrics().filter((repo) => repo.activity >= state.minActivity);
    }

    function getVisibleRepos() {
      const selectable = getSelectableRepos();
      const byName = new Map(selectable.map((repo) => [repo.name, repo]));
      const prioritized = [];
      const add = function(repoName) {
        const repo = byName.get(repoName);
        if (repo && !prioritized.some((item) => item.name === repo.name)) {
          prioritized.push(repo);
        }
      };
      if (state.selectedRepo) {
        add(state.selectedRepo);
      }
      state.compareRepos.forEach(add);
      selectable.forEach((repo) => {
        if (prioritized.length < MAX_DISPLAY_REPOS) {
          add(repo.name);
        }
      });
      return prioritized.slice(0, MAX_DISPLAY_REPOS);
    }

    function buildAggregateSeries(repos) {
      const byDate = new Map();
      repos.forEach((repo) => {
        const series = repo.series || {};
        (series.dates || []).forEach((date, idx) => {
          const current = byDate.get(date) || {
            views: 0,
            uniques: 0,
            clones: 0,
            clone_uniques: 0
          };
          current.views += Number(series.views[idx] || 0);
          current.uniques += Number(series.uniques[idx] || 0);
          current.clones += Number(series.clones[idx] || 0);
          current.clone_uniques += Number(series.clone_uniques[idx] || 0);
          byDate.set(date, current);
        });
      });
      const dates = [...byDate.keys()].sort();
      return {
        dates,
        views: dates.map((date) => byDate.get(date).views),
        uniques: dates.map((date) => byDate.get(date).uniques),
        clones: dates.map((date) => byDate.get(date).clones),
        clone_uniques: dates.map((date) => byDate.get(date).clone_uniques)
      };
    }

    function buildWeekdaySummaryFromSeries(seriesMap) {
      const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      const totals = labels.map(() => ({ views: 0, uniques: 0, clones: 0, clone_uniques: 0, samples: 0 }));
      Object.values(seriesMap || {}).forEach((series) => {
        (series.dates || []).forEach((date, idx) => {
          const parsed = parseIsoDate(date);
          if (!parsed) return;
          const weekday = (parsed.getUTCDay() + 6) % 7;
          totals[weekday].views += Number(series.views[idx] || 0);
          totals[weekday].uniques += Number((series.uniques || [])[idx] || 0);
          totals[weekday].clones += Number(series.clones[idx] || 0);
          totals[weekday].clone_uniques += Number((series.clone_uniques || [])[idx] || 0);
          totals[weekday].samples += 1;
        });
      });
      const avg = (field) => totals.map((b) => b.samples ? Math.round((b[field] / b.samples) * 10) / 10 : 0);
      return {
        labels,
        views: avg('views'),
        uniques: avg('uniques'),
        clones: avg('clones'),
        clone_uniques: avg('clone_uniques')
      };
    }

    function getCurrentWindowData() {
      const repos = getVisibleRepos();
      const aggregate = buildAggregateSeries(repos);
      const totals = repos.reduce((acc, repo) => {
        acc.repo_count += 1;
        acc.total_views += repo.views;
        acc.total_uniques += repo.uniques;
        acc.total_clones += repo.clones;
        acc.total_clone_uniques += repo.clone_uniques;
        acc.total_stars_delta += repo.stars_delta;
        acc.total_subscribers_delta += repo.subscribers_delta;
        acc.total_forks_delta += repo.forks_delta;
        acc.total_stars += repo.stars;
        acc.total_subscribers += repo.subscribers;
        acc.total_forks += repo.forks;
        return acc;
      }, {
        repo_count: 0,
        total_views: 0,
        total_uniques: 0,
        total_clones: 0,
        total_clone_uniques: 0,
        total_stars_delta: 0,
        total_subscribers_delta: 0,
        total_forks_delta: 0,
        total_stars: 0,
        total_subscribers: 0,
        total_forks: 0
      });
      return {
        repos,
        totals,
        daily: aggregate,
        weekday: buildWeekdaySummaryFromSeries(
          Object.fromEntries(repos.map((repo) => [repo.name, repo.series]))
        )
      };
    }

    function aggregateSnapshotRows(rowsByRepo, selectedRepos, keyField) {
      const totals = new Map();
      selectedRepos.forEach((repoName) => {
        (rowsByRepo?.[repoName] || []).forEach((row) => {
          const key = row[keyField] || '';
          const current = totals.get(key) || { ...row, count: 0, uniques: 0 };
          current.count += Number(row.count || 0);
          current.uniques += Number(row.uniques || 0);
          totals.set(key, current);
        });
      });
      return [...totals.values()].sort((a, b) => (b.count - a.count) || String(a[keyField]).localeCompare(String(b[keyField])));
    }

    function getCurrentSnapshotRepoNames() {
      if (isComparing()) {
        return state.compareRepos;
      }
      if (state.selectedRepo) {
        return [state.selectedRepo];
      }
      return getVisibleRepos().map((repo) => repo.name);
    }

    function getCurrentReferrerRows() {
      if (!isComparing() && !state.selectedRepo) {
        return currentPayload()?.referrers || [];
      }
      return aggregateSnapshotRows(
        dashboardData()?.getReferrersByRepo(),
        getCurrentSnapshotRepoNames(),
        'referrer'
      );
    }

    function getCurrentPathRows() {
      if (!isComparing() && !state.selectedRepo) {
        return currentPayload()?.paths || [];
      }
      return aggregateSnapshotRows(
        dashboardData()?.getPathsByRepo(),
        getCurrentSnapshotRepoNames(),
        'path'
      );
    }

    function sanitizeSelection() {
      const selectableRepoNames = new Set(getSelectableRepos().map((repo) => repo.name));
      if (state.selectedRepo && !selectableRepoNames.has(state.selectedRepo)) {
        state.selectedRepo = null;
      }
      state.compareRepos = state.compareRepos
        .filter((repoName) => selectableRepoNames.has(repoName))
        .slice(0, MAX_DISPLAY_REPOS);
    }

    function buildUpdatedText(payload) {
      const windowData = getCurrentWindowData();
      const base = 'Last updated: ' + (payload.generated_at || 'unknown');
      const rangeText = 'Window: ' + getRangeLabel();
      const repoText = 'Showing ' + formatNumber(windowData.totals.repo_count || 0) + ' repositories';
      const daysText = 'Tracking span: ' + formatNumber(payload.totals.days_tracked || 0) + ' collected days total';
      return [base, rangeText, repoText, daysText].join(' | ');
    }

    function formatTooltipDate(label) {
      try {
        const d = parseIsoDate(label);
        if (!d) return label;
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
      } catch (_e) {
        return label;
      }
    }

    function formatEventDate(iso) {
      const d = parseIsoDate(iso);
      if (!d) return iso;
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
    }

    function daysBetween(a, b) {
      const da = parseIsoDate(a);
      const db = parseIsoDate(b);
      if (!da || !db) return Infinity;
      return Math.round((da.getTime() - db.getTime()) / 86400000);
    }

    function computeMomentum() {
      const visible = getVisibleRepos();
      if (!visible.length) return null;
      const aggregate = buildAggregateSeries(visible);
      const dates = aggregate.dates || [];
      const views = aggregate.views || [];
      if (!dates.length) return null;

      let bestIdx = 0;
      for (let i = 1; i < views.length; i += 1) {
        if (Number(views[i] || 0) > Number(views[bestIdx] || 0)) bestIdx = i;
      }
      const bestDay = { date: dates[bestIdx], views: Number(views[bestIdx] || 0) };

      // Trailing-window median (last up-to-14 days, excluding the latest).
      const tailWindow = 14;
      const start = Math.max(0, views.length - tailWindow - 1);
      const tail = views.slice(start, Math.max(start, views.length - 1));
      let median = 0;
      if (tail.length) {
        const sorted = tail.slice().map(Number).sort((a, b) => a - b);
        median = sorted.length % 2
          ? sorted[(sorted.length - 1) >> 1]
          : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
      }

      // Current streak: consecutive trailing days with views > median.
      let streak = 0;
      for (let i = views.length - 1; i >= 0; i -= 1) {
        if (Number(views[i] || 0) > median) streak += 1;
        else break;
      }

      // Top single-repo single-day in the window.
      let topRepo = null;
      let topDay = -1;
      visible.forEach((repo) => {
        const series = repo.series;
        if (!series) return;
        (series.dates || []).forEach((date, idx) => {
          const v = Number((series.views || [])[idx] || 0);
          if (v > topDay) {
            topDay = v;
            topRepo = { name: repo.name, views: v, date };
          }
        });
      });

      // Days since the most recent peak (peak = best day).
      const latestDate = dates[dates.length - 1];
      const daysSincePeak = bestDay.date ? Math.max(0, daysBetween(latestDate, bestDay.date)) : null;

      return { bestDay, streak: { days: streak, median }, topRepo, daysSincePeak };
    }

    function renderMomentum() {
      const grid = document.getElementById('momentum-grid');
      const section = document.getElementById('momentum-section');
      if (!grid || !section) return;
      const m = computeMomentum();
      if (!m || !m.bestDay || !m.bestDay.date) {
        section.style.display = 'none';
        return;
      }
      section.style.display = 'block';
      const cells = [];

      // Hot streak
      if (m.streak.days >= 1) {
        cells.push(`
          <div class="momentum-cell">
            <span class="momentum-label"><span class="moji">🔥</span>Hot streak</span>
            <span class="momentum-value">${m.streak.days}d</span>
            <span class="momentum-meta">consecutive days above baseline (~${formatNumber(Math.round(m.streak.median))}/d)</span>
          </div>`);
      } else {
        cells.push(`
          <div class="momentum-cell">
            <span class="momentum-label"><span class="moji">🔥</span>Hot streak</span>
            <span class="momentum-value muted">—</span>
            <span class="momentum-meta">no current streak above baseline (~${formatNumber(Math.round(m.streak.median))}/d)</span>
          </div>`);
      }

      // Best day
      const bestDateLabel = formatEventDate(m.bestDay.date);
      const sinceLabel = (m.daysSincePeak !== null && m.daysSincePeak !== undefined)
        ? (m.daysSincePeak === 0 ? 'today' : (m.daysSincePeak === 1 ? 'yesterday' : `${m.daysSincePeak}d ago`))
        : '';
      cells.push(`
        <div class="momentum-cell" title="Highest combined-views day across all visible repos">
          <span class="momentum-label"><span class="moji">⭐</span>Best overall day</span>
          <span class="momentum-value">${formatNumber(m.bestDay.views)} views</span>
          <span class="momentum-meta">${escapeHtml(bestDateLabel)}${sinceLabel ? ' · ' + escapeHtml(sinceLabel) : ''}</span>
        </div>`);

      // Top repo single-day
      if (m.topRepo) {
        cells.push(`
          <div class="momentum-cell" title="The single repo + day with the highest views in the window">
            <span class="momentum-label"><span class="moji">🏆</span>Best single-repo day</span>
            <span class="momentum-value"><span class="repo-tag">${escapeHtml(getShortName(m.topRepo.name))}</span>${formatNumber(m.topRepo.views)}</span>
            <span class="momentum-meta">${escapeHtml(formatEventDate(m.topRepo.date))}</span>
          </div>`);
      }

      grid.innerHTML = cells.join('');
    }

    function chartOptions(stacked) {
      const tick = getThemeColor('--text-muted', '#8b949e');
      const grid = getThemeColor('--chart-grid', 'rgba(38, 45, 56, 0.4)');
      const axis = getThemeColor('--chart-axis', 'rgba(38, 45, 56, 0.7)');
      const tipBg = getThemeColor('--chart-tooltip-bg', 'rgba(17, 22, 29, 0.96)');
      const tipBorder = getThemeColor('--chart-tooltip-border', '#262d38');
      const text = getThemeColor('--text', '#e6edf3');
      return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        animation: { duration: 320 },
        plugins: {
          legend: {
            display: !!stacked,
            position: 'bottom',
            labels: { color: tick, boxWidth: 10, boxHeight: 10, usePointStyle: true, padding: 14 }
          },
          tooltip: {
            backgroundColor: tipBg,
            borderColor: tipBorder,
            borderWidth: 1,
            titleColor: text,
            bodyColor: text,
            padding: 10,
            boxPadding: 4,
            usePointStyle: true,
            callbacks: {
              title: function(items) { return items.length ? formatTooltipDate(items[0].label) : ''; },
              label: function(ctx) {
                const value = ctx.parsed && typeof ctx.parsed.y === 'number' ? ctx.parsed.y : ctx.parsed;
                return ' ' + (ctx.dataset.label || '') + '  ' + Number(value || 0).toLocaleString();
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { color: tick, maxRotation: 0, autoSkipPadding: 18 },
            grid: { color: grid, drawTicks: false },
            border: { color: axis }
          },
          y: {
            beginAtZero: true,
            stacked: !!stacked,
            ticks: {
              color: tick,
              callback: function(value) { return compactNumber(value); }
            },
            grid: { color: grid, drawTicks: false },
            border: { display: false }
          }
        }
      };
    }

    function resetCheckboxes() {
      document.querySelectorAll('#repo-table input[type="checkbox"]').forEach((input) => {
        input.checked = false;
      });
    }

    function updateControls() {
      const thresholdInput = document.getElementById('thresholdInput');
      const thresholdValue = document.getElementById('thresholdValue');
      const rangeHint = document.getElementById('rangeHint');

      document.querySelectorAll('[data-window]').forEach((button) => {
        const isActive = button.dataset.window === getSelectedWindow();
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      });
      thresholdInput.value = String(state.minActivity);
      thresholdValue.textContent = formatNumber(state.minActivity);
      const days = getWindowDays();
      rangeHint.textContent = days === null
        ? 'All shows all data since dashboard collection began.'
        : 'Showing up to the latest ' + days + ' collected days. Switch to All for everything collected so far.';
    }

    function setWindow(nextWindow) {
      const normalized = normalizeWindow(nextWindow);
      if (!normalized || state.window === normalized) {
        return;
      }
      state.window = normalized;
      sanitizeSelection();
      updateDashboard();
    }

    function setMetric(nextMetric) {
      if (!METRICS[nextMetric] || state.metric === nextMetric) return;
      state.metric = nextMetric;
      updateDashboard();
    }

    function updateMetricTabs() {
      document.querySelectorAll('.metric-tab').forEach((btn) => {
        const isActive = btn.dataset.metric === state.metric;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
      });
    }

    function setThreshold(nextValue) {
      const parsed = Number(nextValue);
      const safeValue = Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
      if (safeValue === state.minActivity) {
        return;
      }
      state.minActivity = safeValue;
      sanitizeSelection();
      updateDashboard();
    }

    function clearSelection() {
      state.selectedRepo = null;
      state.compareRepos = [];
      resetCheckboxes();
      updateDashboard();
    }

    function selectRepo(repoName) {
      if (state.selectedRepo === repoName) {
        state.selectedRepo = null;
      } else {
        state.selectedRepo = repoName;
      }
      state.compareRepos = [];
      resetCheckboxes();
      updateDashboard();
    }

    function activateRepo(repoName, modifier) {
      if (!repoName) return;
      if (modifier) {
        // ⌘/Ctrl/Shift-click: enter or extend compare mode.
        // If currently focused on a *different* repo, promote that focus
        // into the compare set so the user picks up where they left off.
        const inCompare = state.compareRepos.includes(repoName);
        if (state.selectedRepo && state.selectedRepo !== repoName) {
          const seed = state.selectedRepo;
          state.selectedRepo = null;
          if (!state.compareRepos.includes(seed)) {
            state.compareRepos = state.compareRepos.concat(seed);
          }
        } else if (state.selectedRepo === repoName) {
          // ⌘-click on the currently focused repo: just clear the focus.
          state.selectedRepo = null;
          resetCheckboxes();
          updateDashboard();
          return;
        }
        state.compareRepos = inCompare
          ? state.compareRepos.filter((n) => n !== repoName)
          : state.compareRepos.concat(repoName);
        state.compareRepos = state.compareRepos.slice(0, MAX_DISPLAY_REPOS);
        // If we end up with only one repo in the compare set, treat it as a focus.
        if (state.compareRepos.length === 1) {
          state.selectedRepo = state.compareRepos[0];
          state.compareRepos = [];
        }
        resetCheckboxes();
        updateDashboard();
        return;
      }
      // Plain click → focus toggle, clear any compare state.
      selectRepo(repoName);
    }

    function toggleRepoCompare(repoName, checked) {
      if (checked) {
        if (!state.compareRepos.includes(repoName) && state.compareRepos.length < MAX_DISPLAY_REPOS) {
          state.compareRepos.push(repoName);
        }
      } else {
        state.compareRepos = state.compareRepos.filter((value) => value !== repoName);
      }
      if (isComparing()) {
        state.selectedRepo = null;
      }
      updateDashboard();
    }

    function updateToolbar() {
      const activeBadge = document.getElementById('activeBadge');
      const compareBadge = document.getElementById('compareBadge');
      const clearButton = document.getElementById('clearSelectionBtn');

      if (isComparing()) {
        activeBadge.classList.remove('visible');
        compareBadge.textContent = 'Comparing ' + state.compareRepos.length + ' repos';
        compareBadge.classList.add('visible');
        clearButton.classList.add('visible');
      } else if (state.selectedRepo) {
        compareBadge.classList.remove('visible');
        activeBadge.textContent = 'Focused: ' + getShortName(state.selectedRepo);
        activeBadge.classList.add('visible');
        clearButton.classList.add('visible');
      } else {
        activeBadge.classList.remove('visible');
        compareBadge.classList.remove('visible');
        clearButton.classList.remove('visible');
      }
    }

    function updateStats() {
      const windowData = getCurrentWindowData();
      const totals = windowData.totals || {};
      const focusedRepo = state.selectedRepo ? getRepoByName(state.selectedRepo) : null;
      const statsGrid = document.getElementById('stats-grid');
      const compareSummary = document.getElementById('compare-summary');

      if (isComparing()) {
        statsGrid.style.display = 'none';
        compareSummary.innerHTML = '';
        const metric = metricInfo(state.metric);
        const primaryKey = metric.key;
        const allRows = [
          { key: 'views', label: 'Views' },
          { key: 'uniques', label: 'Visitors' },
          { key: 'clones', label: 'Clones' },
          { key: 'clone_uniques', label: 'Unique Clones' },
          { key: 'stars_delta', label: 'Star Growth' },
          { key: 'subscribers_delta', label: 'Watcher Growth' },
          { key: 'forks_delta', label: 'Fork Growth' }
        ];
        state.compareRepos.forEach((repoName) => {
          const repo = getRepoByName(repoName);
          if (!repo) return;
          const repoColor = getRepoColor(repo.name);
          const card = document.createElement('div');
          card.className = 'compare-card';
          card.style.setProperty('--repo-color', repoColor);
          let rows = `
            <div class="compare-metric-row primary">
              <span class="compare-metric-label">${escapeHtml(metric.label)}</span>
              <span class="compare-metric-value">${primaryKey.endsWith('_delta') ? formatSigned(repo[primaryKey]) : formatNumber(repo[primaryKey])}</span>
            </div>`;
          allRows.filter((r) => r.key !== primaryKey).forEach((r) => {
            rows += `
              <div class="compare-metric-row">
                <span class="compare-metric-label">${escapeHtml(r.label)}</span>
                <span class="compare-metric-value muted">${r.key.endsWith('_delta') ? formatSigned(repo[r.key]) : formatNumber(repo[r.key])}</span>
              </div>`;
          });
          card.innerHTML = `
            <div class="compare-header">
              <span class="color-dot"></span>
              <span>${escapeHtml(getShortName(repo.name))}</span>
            </div>
            ${rows}
          `;
          compareSummary.appendChild(card);
        });
        compareSummary.classList.add('visible');
        return;
      }

      compareSummary.classList.remove('visible');
      compareSummary.innerHTML = '';
      statsGrid.style.display = 'grid';

      const sparkSource = focusedRepo ? focusedRepo.series : windowData.daily;
      const split = splitWindow(sparkSource);

      if (focusedRepo) {
        setText('statRepos', '1');
        setText('statViews', formatNumber(focusedRepo.views));
        setText('statUniques', formatNumber(focusedRepo.uniques));
        setText('statClones', formatNumber(focusedRepo.clones));
        setText('statCloneUniques', formatNumber(focusedRepo.clone_uniques));
        setText('growthAttentionValue', formatNumber(focusedRepo.views) + ' / ' + formatNumber(focusedRepo.uniques));
        setText('growthAttentionContext', 'views / visitors in the selected window');
        setText('growthInterestValue', formatSigned(focusedRepo.stars_delta) + ' / ' + formatSigned(focusedRepo.subscribers_delta));
        setText('growthInterestContext', 'stars / watchers; now ' + formatNumber(focusedRepo.stars) + ' / ' + formatNumber(focusedRepo.subscribers));
        setText('growthAdoptionValue', formatNumber(focusedRepo.clones) + ' / ' + formatSigned(focusedRepo.forks_delta));
        setText('growthAdoptionContext', 'clones / forks; now ' + formatNumber(focusedRepo.forks) + ' forks');
      } else {
        setText('statRepos', formatNumber(totals.repo_count));
        setText('statViews', formatNumber(totals.total_views));
        setText('statUniques', formatNumber(totals.total_uniques));
        setText('statClones', formatNumber(totals.total_clones));
        setText('statCloneUniques', formatNumber(totals.total_clone_uniques));
        setText('growthAttentionValue', formatNumber(totals.total_views) + ' / ' + formatNumber(totals.total_uniques));
        setText('growthAttentionContext', 'views / visitors across visible repos');
        setText('growthInterestValue', formatSigned(totals.total_stars_delta) + ' / ' + formatSigned(totals.total_subscribers_delta));
        setText('growthInterestContext', 'stars / watchers; now ' + formatNumber(totals.total_stars) + ' / ' + formatNumber(totals.total_subscribers));
        setText('growthAdoptionValue', formatNumber(totals.total_clones) + ' / ' + formatSigned(totals.total_forks_delta));
        setText('growthAdoptionContext', 'clones / forks; now ' + formatNumber(totals.total_forks) + ' forks');
      }

      renderDelta('deltaRepos', null);
      renderDelta('deltaViews', computeDelta(split, 'views'));
      renderDelta('deltaUniques', computeDelta(split, 'uniques'));
      renderDelta('deltaClones', computeDelta(split, 'clones'));
      renderDelta('deltaCloneUniques', computeDelta(split, 'clone_uniques'));

      const src = sparkSource || { views: [], uniques: [], clones: [], clone_uniques: [] };
      renderSparkline('sparkRepos', (windowData.daily && windowData.daily.views) || [], getThemeColor('--accent', '#1f6feb'));
      renderSparkline('sparkViews', src.views || [], getThemeColor('--c-views', '#58a6ff'));
      renderSparkline('sparkUniques', src.uniques || [], getThemeColor('--c-uniques', '#3fb950'));
      renderSparkline('sparkClones', src.clones || [], getThemeColor('--c-clones', '#CC79A7'));
      renderSparkline('sparkCloneUniques', src.clone_uniques || [], getThemeColor('--c-cloners', '#ffa657'));
    }

    function ensureCharts() {
      if (!dailyChart) {
        dailyChart = new Chart(document.getElementById('dailyChart'), {
          type: 'line',
          data: { labels: [], datasets: [] },
          options: chartOptions(false)
        });
      }
      if (!weekdayChart) {
        const tick = getThemeColor('--text-muted', '#8b949e');
        const grid = getThemeColor('--chart-grid', 'rgba(38, 45, 56, 0.4)');
        const axis = getThemeColor('--chart-axis', 'rgba(38, 45, 56, 0.7)');
        const tipBg = getThemeColor('--chart-tooltip-bg', 'rgba(17, 22, 29, 0.96)');
        const tipBorder = getThemeColor('--chart-tooltip-border', '#262d38');
        const text = getThemeColor('--text', '#e6edf3');
        weekdayChart = new Chart(document.getElementById('weekdayChart'), {
          type: 'bar',
          data: { labels: [], datasets: [] },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 320 },
            plugins: {
              legend: { display: false },
              tooltip: {
                backgroundColor: tipBg,
                borderColor: tipBorder,
                borderWidth: 1,
                titleColor: text,
                bodyColor: text,
                padding: 10,
                callbacks: {
                  label: function(ctx) {
                    return ' ' + (ctx.dataset.label || '') + '  ' + Number(ctx.parsed.y || 0).toLocaleString();
                  }
                }
              }
            },
            scales: {
              x: {
                ticks: { color: tick },
                grid: { display: false },
                border: { color: axis }
              },
              y: {
                beginAtZero: true,
                ticks: { color: tick, callback: function(v) { return compactNumber(v); } },
                grid: { color: grid, drawTicks: false },
                border: { display: false }
              }
            }
          }
        });
      }
      if (!stackedChart) {
        const opts = chartOptions(true);
        const repoFromDatasetLabel = function(label) {
          return (dashboardData()?.getRepos() || []).find((r) => getShortName(r.name) === label)?.name || label;
        };
        const modifierFromEvent = function(event) {
          const native = event && (event.native || event);
          return !!(native && (native.metaKey || native.ctrlKey || native.shiftKey));
        };
        opts.onClick = function(event, elements, chart) {
          if (!elements || !elements.length) return;
          const ds = chart.data.datasets[elements[0].datasetIndex];
          if (!ds) return;
          // Match chip strip / table semantics: plain click = focus,
          // ⌘/Ctrl/Shift-click = enter or extend compare.
          activateRepo(repoFromDatasetLabel(ds.label), modifierFromEvent(event));
        };
        opts.onHover = function(event, elements, chart) {
          chart.canvas.style.cursor = (elements && elements.length) ? 'pointer' : 'default';
        };
        if (opts.plugins && opts.plugins.legend) {
          opts.plugins.legend.onClick = function(event, legendItem, legend) {
            const chart = legend.chart;
            const ds = chart.data.datasets[legendItem.datasetIndex];
            if (!ds) return;
            activateRepo(repoFromDatasetLabel(ds.label), modifierFromEvent(event));
          };
        }
        stackedChart = new Chart(document.getElementById('stackedChart'), {
          type: 'line',
          data: { labels: [], datasets: [] },
          options: opts
        });
      }
    }

    function buildAreaGradient(ctx, chartArea, color) {
      if (!chartArea) return hexAlpha(color, 0.15);
      const g = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
      g.addColorStop(0, hexAlpha(color, 0.42));
      g.addColorStop(1, hexAlpha(color, 0.02));
      return g;
    }

    function makeAreaDataset(label, data, color, options) {
      return {
        label,
        data,
        borderColor: color,
        borderWidth: 2.2,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBorderWidth: 2,
        pointHoverBackgroundColor: getThemeColor('--bg', '#0b0e13'),
        pointHoverBorderColor: color,
        tension: 0.32,
        fill: options && options.fill === false ? false : 'origin',
        backgroundColor: function(context) {
          const chart = context.chart;
          const { ctx, chartArea } = chart;
          return buildAreaGradient(ctx, chartArea, color);
        }
      };
    }

    function updateDailyChart() {
      const windowData = getCurrentWindowData();
      const title = document.getElementById('dailyChartTitle');
      const metric = metricInfo(state.metric);
      const datasets = [];

      if (isComparing()) {
        title.textContent = metric.label + ' across compared repos';
        const compareDates = [...new Set(
          state.compareRepos.flatMap((repoName) => (getRepoByName(repoName)?.series?.dates || []))
        )].sort();
        dailyChart.data.labels = compareDates;
        state.compareRepos.forEach((repoName) => {
          const series = getRepoByName(repoName)?.series;
          if (!series) return;
          const dateMap = {};
          const values = series[metric.key] || [];
          (series.dates || []).forEach((date, idx) => { dateMap[date] = values[idx] || 0; });
          const ds = makeAreaDataset(
            getShortName(repoName),
            compareDates.map((date) => dateMap[date] || 0),
            getRepoColor(repoName),
            { fill: false }
          );
          ds.borderDash = getRepoDash(repoName);
          datasets.push(ds);
        });
      } else if (state.selectedRepo) {
        const series = getRepoByName(state.selectedRepo)?.series;
        title.textContent = metric.label + ': ' + getShortName(state.selectedRepo);
        dailyChart.data.labels = series ? series.dates : [];
        datasets.push(makeAreaDataset(
          metric.label,
          series ? (series[metric.key] || []) : [],
          metric.color
        ));
      } else {
        title.textContent = metric.label + ' over time';
        dailyChart.data.labels = windowData.daily.dates || [];
        datasets.push(makeAreaDataset(
          metric.label,
          windowData.daily[metric.key] || [],
          metric.color
        ));
      }

      dailyChart.data.datasets = datasets;
      dailyChart.update();
    }

    function updateWeekdayChart() {
      const windowData = getCurrentWindowData();
      const title = document.getElementById('weekdayChartTitle');
      const metricLabel = document.getElementById('weekdayMetricLabel');
      const metric = metricInfo(state.metric);
      const defaultLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      let labels = defaultLabels;
      let datasets = [];

      if (metricLabel) metricLabel.textContent = metric.label.toLowerCase();

      if (isComparing()) {
        title.textContent = 'Weekday rhythm — ' + metric.label.toLowerCase();
        labels = windowData.weekday?.labels || defaultLabels;
        datasets = state.compareRepos.map((repoName) => ({
          label: getShortName(repoName),
          data: buildWeekdaySummaryFromSeries({
            [repoName]: getRepoByName(repoName)?.series || { dates: [], views: [], uniques: [], clones: [], clone_uniques: [], stars_delta: [], subscribers_delta: [], forks_delta: [] }
          })[metric.key] || labels.map(() => 0),
          backgroundColor: hexAlpha(getRepoColor(repoName), 0.85),
          borderRadius: 6,
          maxBarThickness: 22
        }));
      } else {
        const weekdayData = state.selectedRepo
          ? buildWeekdaySummaryFromSeries({
              [state.selectedRepo]: getRepoByName(state.selectedRepo)?.series || { dates: [], views: [], uniques: [], clones: [], clone_uniques: [], stars_delta: [], subscribers_delta: [], forks_delta: [] }
            })
          : windowData.weekday;
        title.textContent = state.selectedRepo
          ? 'Weekday rhythm: ' + getShortName(state.selectedRepo)
          : 'Weekday rhythm';
        labels = weekdayData?.labels || defaultLabels;
        datasets = [
          {
            label: 'Avg ' + metric.label.toLowerCase(),
            data: weekdayData?.[metric.key] || labels.map(() => 0),
            backgroundColor: hexAlpha(metric.color, 0.78),
            borderRadius: 6,
            maxBarThickness: 28
          }
        ];
      }

      weekdayChart.data.labels = labels;
      weekdayChart.data.datasets = datasets;
      weekdayChart.update();
    }

    function updateStackedChart() {
      const visibleRepos = getVisibleRepos();
      const card = document.getElementById('stacked-card');
      const title = document.getElementById('stackedChartTitle');
      if (!visibleRepos.length || visibleRepos.length <= 1) {
        card.style.display = 'none';
        return;
      }
      card.style.display = 'block';

      const metric = metricInfo(state.metric);
      const repoNames = visibleRepos.map((repo) => repo.name);
      const allDates = [...new Set(
        repoNames.flatMap((repoName) => (getRepoByName(repoName)?.series?.dates || []))
      )].sort();

      if (isComparing()) {
        title.textContent = metric.label + ' across compared repos';
        stackedChart.options.scales.y.stacked = false;
        stackedChart.data.labels = allDates;
        // Render all visible repos; compared ones get bold styling, others
        // are ghosted but still appear in the legend so the user can click
        // to add them to the compare set without leaving the chart.
        stackedChart.data.datasets = repoNames.map((repoName) => {
          const series = getRepoByName(repoName)?.series;
          const dateMap = {};
          const values = series?.[metric.key] || [];
          (series?.dates || []).forEach((date, idx) => { dateMap[date] = values[idx] || 0; });
          const color = getRepoColor(repoName);
          const inSet = state.compareRepos.includes(repoName);
          return {
            label: getShortName(repoName),
            data: allDates.map((date) => dateMap[date] || 0),
            borderColor: inSet ? color : hexAlpha(color, 0.22),
            backgroundColor: 'transparent',
            borderDash: getRepoDash(repoName),
            fill: false,
            tension: 0,
            borderWidth: inSet ? 2 : 1,
            pointRadius: 0,
            pointHoverRadius: inSet ? 4 : 3
          };
        });
      } else if (state.selectedRepo) {
        const focusName = state.selectedRepo;
        title.textContent = metric.label + ' over time: ' + getShortName(focusName);
        stackedChart.options.scales.y.stacked = false;
        stackedChart.data.labels = allDates;
        // Render every visible repo so the legend stays interactive — the
        // focused repo gets full styling, the others fade to ghosts.
        stackedChart.data.datasets = repoNames.map((repoName) => {
          const series = getRepoByName(repoName)?.series;
          const dateMap = {};
          const values = series?.[metric.key] || [];
          (series?.dates || []).forEach((date, idx) => { dateMap[date] = values[idx] || 0; });
          const color = getRepoColor(repoName);
          const isFocus = repoName === focusName;
          return {
            label: getShortName(repoName),
            data: allDates.map((date) => dateMap[date] || 0),
            borderColor: isFocus ? color : hexAlpha(color, 0.28),
            backgroundColor: isFocus ? hexAlpha(color, 0.32) : 'transparent',
            borderDash: getRepoDash(repoName),
            fill: isFocus ? 'origin' : false,
            tension: isFocus ? 0.28 : 0,
            borderWidth: isFocus ? 2.4 : 1,
            pointRadius: 0,
            pointHoverRadius: isFocus ? 4 : 3
          };
        });
      } else {
        title.textContent = metric.label + ' by repository';
        stackedChart.options.scales.y.stacked = true;
        stackedChart.data.labels = allDates;
        stackedChart.data.datasets = repoNames.map((repoName, idx) => {
          const series = getRepoByName(repoName)?.series;
          const dateMap = {};
          const values = series?.[metric.key] || [];
          (series?.dates || []).forEach((date, seriesIdx) => { dateMap[date] = values[seriesIdx] || 0; });
          const color = palette[idx % palette.length];
          return {
            label: getShortName(repoName),
            data: allDates.map((date) => dateMap[date] || 0),
            borderColor: color,
            backgroundColor: hexAlpha(color, 0.55),
            borderDash: getRepoDash(repoName),
            fill: true,
            tension: 0,
            borderWidth: 1,
            pointRadius: 0,
            pointHoverRadius: 4
          };
        });
      }
      stackedChart.update();
    }

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

        if (item.kind === 'trend') {
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
            state.compareRepos = matched;
            state.selectedRepo = null;
          }
        }
      } catch (_e) { /* ignore */ }
    }

    function repoNamesRequiredForCurrentView() {
      if (isComparing()) {
        return state.compareRepos.slice();
      }
      if (state.selectedRepo) {
        return [state.selectedRepo];
      }
      return [];
    }

    function ensureCurrentRepoChunksLoaded() {
      const data = dashboardData();
      if (!data || !data.isLazy()) {
        return null;
      }
      const missing = repoNamesRequiredForCurrentView()
        .filter((repoName) => !data.isRepoLoaded(repoName));
      if (!missing.length) {
        return null;
      }
      return Promise.all(missing.map((repoName) => data.loadRepo(repoName)));
    }

    function updateDashboard() {
      const payload = currentPayload();
      if (!payload) {
        return;
      }
      const pendingChunks = ensureCurrentRepoChunksLoaded();
      if (pendingChunks) {
        pendingChunks.then(function() {
          updateDashboard();
        }).catch(function(error) {
          console.error('Failed to load repository chunk', error);
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

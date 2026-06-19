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

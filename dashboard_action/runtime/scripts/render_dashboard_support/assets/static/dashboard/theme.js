export function installTheme(context) {
  const document = context.document;
  const window = context.window;
  const localStorage = context.localStorage;
  const getComputedStyle = context.getComputedStyle;
  const METRICS = context.METRICS;
  const chartOptions = (...args) => context.chartOptions(...args);
  const currentPayload = (...args) => context.currentPayload(...args);
  const updateDashboard = (...args) => context.updateDashboard(...args);

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
      if (!context.charts.dailyChart && !context.charts.weekdayChart && !context.charts.stackedChart) return;
      const newOpts = chartOptions(false);
      if (context.charts.dailyChart) {
        Object.assign(context.charts.dailyChart.options, newOpts);
        context.charts.dailyChart.update('none');
      }
      if (context.charts.weekdayChart) {
        // weekday uses its own option block — patch the text/grid colors
        const tickColor = getThemeColor('--text-muted', '#8b949e');
        const gridColor = getThemeColor('--chart-grid', 'rgba(38, 45, 56, 0.4)');
        const axisColor = getThemeColor('--chart-axis', 'rgba(38, 45, 56, 0.7)');
        context.charts.weekdayChart.options.scales.x.ticks.color = tickColor;
        context.charts.weekdayChart.options.scales.y.ticks.color = tickColor;
        context.charts.weekdayChart.options.scales.y.grid.color = gridColor;
        if (context.charts.weekdayChart.options.scales.x.border) context.charts.weekdayChart.options.scales.x.border.color = axisColor;
        if (context.charts.weekdayChart.options.plugins?.tooltip) {
          context.charts.weekdayChart.options.plugins.tooltip.backgroundColor = getThemeColor('--chart-tooltip-bg', 'rgba(17, 22, 29, 0.96)');
          context.charts.weekdayChart.options.plugins.tooltip.borderColor = getThemeColor('--chart-tooltip-border', '#262d38');
          context.charts.weekdayChart.options.plugins.tooltip.titleColor = getThemeColor('--text', '#e6edf3');
          context.charts.weekdayChart.options.plugins.tooltip.bodyColor = getThemeColor('--text', '#e6edf3');
        }
        context.charts.weekdayChart.update('none');
      }
      if (context.charts.stackedChart) {
        const stackedOpts = chartOptions(true);
        // Preserve stack flag set elsewhere
        const wasStacked = context.charts.stackedChart.options.scales?.y?.stacked;
        Object.assign(context.charts.stackedChart.options, stackedOpts);
        if (context.charts.stackedChart.options.scales && context.charts.stackedChart.options.scales.y) {
          context.charts.stackedChart.options.scales.y.stacked = !!wasStacked;
        }
        context.charts.stackedChart.update('none');
      }
      if (currentPayload()) updateDashboard();
    }

  return { metricInfo, hexAlpha, getThemeColor, themeMetricColor, THEME_KEY, preferredTheme, applyTheme, toggleTheme, refreshCharts };
}

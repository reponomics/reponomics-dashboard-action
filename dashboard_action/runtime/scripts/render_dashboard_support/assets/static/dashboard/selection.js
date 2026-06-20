export function installSelection(context) {
  const document = context.document;
  const DEFAULT_WINDOW = context.DEFAULT_WINDOW;
  const WINDOW_PRESETS = context.WINDOW_PRESETS;
  const buildRepoMetrics = (...args) => context.buildRepoMetrics(...args);
  const currentPayload = (...args) => context.currentPayload(...args);
  const dashboardData = (...args) => context.dashboardData(...args);
  const palette = context.palette;
  const state = context.state;

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

  return { escapeHtml, setText, getShortName, getRepoByName, getRepoColor, isComparing, normalizeWindow, getDefaultWindow, getSelectedWindow, getWindowDays, getRangeLabel, parseIsoDate, formatIsoDate, getWindowCutoffDate };
}

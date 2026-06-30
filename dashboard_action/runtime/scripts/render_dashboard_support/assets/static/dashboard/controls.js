export function installControls(context) {
  const document = context.document;
  const MAX_COMPARE_REPOS = context.MAX_COMPARE_REPOS;
  const METRICS = context.METRICS;
  const getSelectedWindow = (...args) => context.getSelectedWindow(...args);
  const getShortName = (...args) => context.getShortName(...args);
  const getWindowDays = (...args) => context.getWindowDays(...args);
  const isComparing = (...args) => context.isComparing(...args);
  const normalizeWindow = (...args) => context.normalizeWindow(...args);
  const sanitizeSelection = (...args) => context.sanitizeSelection(...args);
  const state = context.state;
  const updateDashboard = (...args) => context.updateDashboard(...args);

    function resetCheckboxes() {
      document.querySelectorAll('#repo-table input[type="checkbox"]').forEach((input) => {
        input.checked = false;
      });
    }

    function updateControls() {
      const rangeHint = document.getElementById('rangeHint');

      document.querySelectorAll('[data-window]').forEach((button) => {
        const isActive = button.dataset.window === getSelectedWindow();
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      });
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

    function setMetric(nextMetric, modifier) {
      if (!METRICS[nextMetric]) return;
      const current = selectedDailyMetricIds();
      const isSelected = current.includes(nextMetric);

      if (!modifier) {
        state.metric = nextMetric;
        state.dailyMetrics = [nextMetric];
        updateDashboard();
        return;
      }

      let nextDailyMetrics = current;
      if (isSelected && current.length > 1) {
        nextDailyMetrics = current.filter((metric) => metric !== nextMetric);
        if (state.metric === nextMetric) state.metric = nextDailyMetrics[0];
      } else if (!isSelected) {
        nextDailyMetrics = current.concat(nextMetric);
      }
      state.dailyMetrics = nextDailyMetrics;
      updateDashboard();
    }

    function selectedDailyMetricIds() {
      const source = Array.isArray(state.dailyMetrics) && state.dailyMetrics.length
        ? state.dailyMetrics
        : [state.metric || 'views'];
      const seen = new Set();
      const selected = source.filter((metric) => {
        if (!METRICS[metric] || seen.has(metric)) return false;
        seen.add(metric);
        return true;
      });
      if (!selected.length) selected.push('views');
      if (!METRICS[state.metric] || !selected.includes(state.metric)) {
        state.metric = selected[0];
      }
      state.dailyMetrics = selected;
      return selected;
    }

    function updateMetricTabs() {
      const selected = selectedDailyMetricIds();
      document.querySelectorAll('.metric-tab').forEach((btn) => {
        const isSelected = selected.includes(btn.dataset.metric);
        const isPrimary = btn.dataset.metric === state.metric;
        btn.classList.toggle('active', isSelected);
        btn.classList.toggle('primary', isPrimary);
        btn.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
      });
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
        state.compareRepos = state.compareRepos.slice(0, MAX_COMPARE_REPOS);
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
        if (!state.compareRepos.includes(repoName) && state.compareRepos.length < MAX_COMPARE_REPOS) {
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
        compareBadge.textContent = 'Comparing ' + state.compareRepos.length + ' published repos';
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

  return { resetCheckboxes, updateControls, setWindow, setMetric, selectedDailyMetricIds, updateMetricTabs, clearSelection, selectRepo, activateRepo, toggleRepoCompare, updateToolbar };
}

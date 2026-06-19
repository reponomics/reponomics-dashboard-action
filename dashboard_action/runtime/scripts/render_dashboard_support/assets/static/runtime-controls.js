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

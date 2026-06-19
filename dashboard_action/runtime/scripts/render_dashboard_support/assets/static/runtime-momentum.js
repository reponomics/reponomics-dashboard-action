    function sanitizeSelection() {
      const selectableRepoNames = new Set(getSelectableRepos().map((repo) => repo.name));
      if (state.selectedRepo && !selectableRepoNames.has(state.selectedRepo)) {
        state.selectedRepo = null;
      }
      state.compareRepos = state.compareRepos
        .filter((repoName) => selectableRepoNames.has(repoName))
        .slice(0, MAX_COMPARE_REPOS);
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

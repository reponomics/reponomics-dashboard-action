export function installCharts(context) {
  const document = context.document;
  const activateRepo = (...args) => context.activateRepo(...args);
  const buildWeekdaySummaryFromSeries = (...args) => context.buildWeekdaySummaryFromSeries(...args);
  const chartOptions = (...args) => context.chartOptions(...args);
  const compactNumber = (...args) => context.compactNumber(...args);
  const computeDelta = (...args) => context.computeDelta(...args);
  const configureYAxis = (...args) => context.configureYAxis(...args);
  const dashboardData = (...args) => context.dashboardData(...args);
  const escapeHtml = (...args) => context.escapeHtml(...args);
  const formatNumber = (...args) => context.formatNumber(...args);
  const formatSigned = (...args) => context.formatSigned(...args);
  const getCurrentWindowData = (...args) => context.getCurrentWindowData(...args);
  const getRepoByName = (...args) => context.getRepoByName(...args);
  const getRepoColor = (...args) => context.getRepoColor(...args);
  const getRepoDash = (...args) => context.getRepoDash(...args);
  const getShortName = (...args) => context.getShortName(...args);
  const getThemeColor = (...args) => context.getThemeColor(...args);
  const getVisibleRepos = (...args) => context.getVisibleRepos(...args);
  const hexAlpha = (...args) => context.hexAlpha(...args);
  const isComparing = (...args) => context.isComparing(...args);
  const metricInfo = (...args) => context.metricInfo(...args);
  const palette = context.palette;
  const renderDelta = (...args) => context.renderDelta(...args);
  const renderSparkline = (...args) => context.renderSparkline(...args);
  const seriesValueAt = (...args) => context.seriesValueAt(...args);
  const setText = (...args) => context.setText(...args);
  const splitWindow = (...args) => context.splitWindow(...args);
  const state = context.state;

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
      renderSparkline('sparkRepos', (windowData.daily && windowData.daily.views) || [], getThemeColor('--accent', '#6bb8ff'));
      renderSparkline('sparkViews', src.views || [], getThemeColor('--c-views', '#6bb8ff'));
      renderSparkline('sparkUniques', src.uniques || [], getThemeColor('--c-uniques', '#4fc8a5'));
      renderSparkline('sparkClones', src.clones || [], getThemeColor('--c-clones', '#d97eb7'));
      renderSparkline('sparkCloneUniques', src.clone_uniques || [], getThemeColor('--c-cloners', '#f0b75a'));
    }

    function ensureCharts() {
      if (!context.charts.dailyChart) {
        context.charts.dailyChart = context.chartAdapter.createChart(document.getElementById('dailyChart'), {
          type: 'line',
          data: { labels: [], datasets: [] },
          options: chartOptions(false)
        });
      }
      if (!context.charts.weekdayChart) {
        const tick = getThemeColor('--text-muted', '#a4b1c1');
        const grid = getThemeColor('--chart-grid', 'rgba(38, 45, 56, 0.4)');
        const axis = getThemeColor('--chart-axis', 'rgba(38, 45, 56, 0.7)');
        const tipBg = getThemeColor('--chart-tooltip-bg', 'rgba(12, 16, 22, 0.97)');
        const tipBorder = getThemeColor('--chart-tooltip-border', 'rgba(214, 168, 75, 0.30)');
        const text = getThemeColor('--text', '#edf3f8');
        context.charts.weekdayChart = context.chartAdapter.createChart(document.getElementById('weekdayChart'), {
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
                cornerRadius: 8,
                caretSize: 6,
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
      if (!context.charts.stackedChart) {
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
        context.charts.stackedChart = context.chartAdapter.createChart(document.getElementById('stackedChart'), {
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
        context.charts.dailyChart.data.labels = compareDates;
        state.compareRepos.forEach((repoName) => {
          const series = getRepoByName(repoName)?.series;
          if (!series) return;
          const dateMap = {};
          (series.dates || []).forEach((date, idx) => { dateMap[date] = seriesValueAt(series, metric.key, idx); });
          const ds = makeAreaDataset(
            getShortName(repoName),
            compareDates.map((date) => date in dateMap ? dateMap[date] : null),
            getRepoColor(repoName),
            { fill: false }
          );
          ds.borderDash = getRepoDash(repoName);
          datasets.push(ds);
        });
      } else if (state.selectedRepo) {
        const series = getRepoByName(state.selectedRepo)?.series;
        title.textContent = metric.label + ': ' + getShortName(state.selectedRepo);
        context.charts.dailyChart.data.labels = series ? series.dates : [];
        datasets.push(makeAreaDataset(
          metric.label,
          series ? (series[metric.key] || []) : [],
          metric.color
        ));
      } else {
        title.textContent = metric.label + ' over time';
        context.charts.dailyChart.data.labels = windowData.daily.dates || [];
        datasets.push(makeAreaDataset(
          metric.label,
          windowData.daily[metric.key] || [],
          metric.color
        ));
      }

      context.charts.dailyChart.data.datasets = datasets;
      configureYAxis(context.charts.dailyChart, context.charts.dailyChart.data.labels, datasets, false);
      context.charts.dailyChart.update();
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

      context.charts.weekdayChart.data.labels = labels;
      context.charts.weekdayChart.data.datasets = datasets;
      configureYAxis(context.charts.weekdayChart, labels, datasets, false);
      context.charts.weekdayChart.update();
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
        context.charts.stackedChart.options.scales.y.stacked = false;
        context.charts.stackedChart.data.labels = allDates;
        // Render all visible repos; compared ones get bold styling, others
        // are ghosted but still appear in the legend so the user can click
        // to add them to the compare set without leaving the chart.
        context.charts.stackedChart.data.datasets = repoNames.map((repoName) => {
          const series = getRepoByName(repoName)?.series;
          const dateMap = {};
          (series?.dates || []).forEach((date, idx) => { dateMap[date] = seriesValueAt(series, metric.key, idx); });
          const color = getRepoColor(repoName);
          const inSet = state.compareRepos.includes(repoName);
          return {
            label: getShortName(repoName),
            data: allDates.map((date) => date in dateMap ? dateMap[date] : null),
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
        context.charts.stackedChart.options.scales.y.stacked = false;
        context.charts.stackedChart.data.labels = allDates;
        // Render every visible repo so the legend stays interactive — the
        // focused repo gets full styling, the others fade to ghosts.
        context.charts.stackedChart.data.datasets = repoNames.map((repoName) => {
          const series = getRepoByName(repoName)?.series;
          const dateMap = {};
          (series?.dates || []).forEach((date, idx) => { dateMap[date] = seriesValueAt(series, metric.key, idx); });
          const color = getRepoColor(repoName);
          const isFocus = repoName === focusName;
          return {
            label: getShortName(repoName),
            data: allDates.map((date) => date in dateMap ? dateMap[date] : null),
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
        context.charts.stackedChart.options.scales.y.stacked = true;
        context.charts.stackedChart.data.labels = allDates;
        context.charts.stackedChart.data.datasets = repoNames.map((repoName, idx) => {
          const series = getRepoByName(repoName)?.series;
          const dateMap = {};
          (series?.dates || []).forEach((date, seriesIdx) => { dateMap[date] = seriesValueAt(series, metric.key, seriesIdx); });
          const color = palette[idx % palette.length];
          return {
            label: getShortName(repoName),
            data: allDates.map((date) => date in dateMap ? dateMap[date] : null),
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
      configureYAxis(context.charts.stackedChart, context.charts.stackedChart.data.labels, context.charts.stackedChart.data.datasets, !!context.charts.stackedChart.options.scales.y.stacked);
      context.charts.stackedChart.update();
    }

  return { updateStats, ensureCharts, buildAreaGradient, makeAreaDataset, updateDailyChart, updateWeekdayChart, updateStackedChart };
}

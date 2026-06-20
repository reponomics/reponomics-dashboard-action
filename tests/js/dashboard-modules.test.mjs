import assert from 'node:assert/strict';
import test from 'node:test';

import { createDashboardApp } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/app.js';
import { installFormat } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/format.js';
import { installSeries } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/series.js';

function fakeElement() {
  return {
    classList: { add() {}, remove() {}, toggle() {} },
    dataset: {},
    style: { setProperty() {} },
    appendChild() {},
    addEventListener() {},
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    setAttribute() {},
    removeAttribute() {},
    innerHTML: '',
    textContent: '',
  };
}

function fakeDocument() {
  return {
    documentElement: {
      getAttribute() {
        return null;
      },
      setAttribute() {},
      removeAttribute() {},
    },
    addEventListener() {},
    createElement() {
      return fakeElement();
    },
    createTextNode(value) {
      return { textContent: String(value) };
    },
    getElementById() {
      return fakeElement();
    },
    querySelectorAll() {
      return [];
    },
  };
}

function fakeHost() {
  const document = fakeDocument();
  const localStorage = {
    getItem() {
      return null;
    },
    setItem() {},
  };
  return {
    document,
    window: {
      document,
      navigator: {},
      localStorage,
      history: {},
      addEventListener() {},
      matchMedia() {
        return { matches: false };
      },
    },
    navigator: {},
    localStorage,
    history: {},
    getComputedStyle() {
      return {
        getPropertyValue() {
          return '';
        },
      };
    },
    chartAdapter: {
      createChart() {
        return {
          canvas: { style: {} },
          data: { labels: [], datasets: [] },
          options: {
            plugins: { tooltip: {} },
            scales: {
              x: { border: {}, grid: {}, ticks: {} },
              y: { border: {}, grid: {}, ticks: {} },
            },
          },
          update() {},
        };
      },
    },
  };
}

test('dashboard app creates isolated contexts without implicit browser globals', () => {
  const first = createDashboardApp(fakeHost());
  const second = createDashboardApp(fakeHost());

  assert.equal(typeof first.renderDashboard, 'function');
  assert.equal(typeof first.updateDashboard, 'function');
  assert.notStrictEqual(first.context, second.context);
  assert.notStrictEqual(first.context.state, second.context.state);
  assert.equal(first.context.DEFAULT_WINDOW, '14');
  assert.deepEqual(first.context.charts, {
    dailyChart: null,
    weekdayChart: null,
    stackedChart: null,
  });
});

test('format helpers install independently of app lifecycle', () => {
  const helpers = installFormat({ document: fakeDocument(), window: {} });

  assert.equal(helpers.formatNumber(1200), '1,200');
  assert.equal(helpers.compactNumber(1250), '1.3k');
  assert.equal(helpers.axisTickLabel(0.5), '');
  assert.equal(helpers.formatSigned(-3), '-3');
  assert.equal(helpers.sumArray([1, '2', null, undefined, 4]), 7);
  assert.equal(helpers.buildSparklinePath([], 100, 34).line, '');
  assert.match(helpers.buildSparklinePath([3, 7, 5], 100, 34).line, /^M0\.00 /);
});

test('series helpers preserve selected-window and growth aggregation contracts', () => {
  const context = {
    MAX_DISPLAY_REPOS: 20,
    SERIES_METRIC_KEYS: [
      'views',
      'uniques',
      'clones',
      'clone_uniques',
      'stars_delta',
      'subscribers_delta',
      'forks_delta',
    ],
    currentPayload() {
      return {};
    },
    dashboardData() {
      return null;
    },
    getSelectedWindow() {
      return '7';
    },
    getWindowCutoffDate() {
      return '2026-06-03';
    },
    hasChunkLoadError() {
      return false;
    },
    isComparing() {
      return false;
    },
    parseIsoDate(value) {
      return new Date(`${value}T00:00:00Z`);
    },
    state: {
      compareRepos: [],
      minActivity: 1,
      selectedRepo: null,
    },
  };
  const helpers = installSeries(context);

  assert.deepEqual(
    helpers.seriesForRange({
      dates: ['2026-06-01', '2026-06-02', '2026-06-03', '2026-06-04'],
      views: [1, 2, 3, 4],
      uniques: [2, 3, 4, 5],
      clones: [0, 1, 0, 1],
      clone_uniques: [0, 1, 0, 1],
      samples: 4,
    }),
    {
      dates: ['2026-06-03', '2026-06-04'],
      views: [3, 4],
      uniques: [4, 5],
      clones: [0, 1],
      clone_uniques: [0, 1],
      samples: 2,
    },
  );

  assert.deepEqual(
    helpers.buildGrowthDeltaSeries({
      dates: ['2026-06-01', '2026-06-02', '2026-06-03'],
      stargazers: [10, 12, 15],
      subscribers: [4, 4, 6],
      forks: [1, 2, 2],
    }),
    {
      dates: ['2026-06-01', '2026-06-02', '2026-06-03'],
      stars_delta: [0, 2, 3],
      subscribers_delta: [0, 0, 2],
      forks_delta: [0, 1, 0],
    },
  );

  assert.deepEqual(
    helpers.mergeMetricSeries(
      {
        dates: ['2026-06-02'],
        views: [9],
        uniques: [5],
        clones: [2],
        clone_uniques: [1],
      },
      {
        dates: ['2026-06-01', '2026-06-02'],
        stars_delta: [0, 2],
        subscribers_delta: [0, 1],
        forks_delta: [0, 0],
      },
    ),
    {
      dates: ['2026-06-01', '2026-06-02'],
      views: [null, 9],
      uniques: [null, 5],
      clones: [null, 2],
      clone_uniques: [null, 1],
      stars_delta: [0, 2],
      subscribers_delta: [0, 1],
      forks_delta: [0, 0],
    },
  );
});

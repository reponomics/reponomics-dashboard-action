import assert from 'node:assert/strict';
import test from 'node:test';

import { createDashboardApp } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/app.js';
import { installCharts } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/charts.js';
import { installControls } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/controls.js';
import { installDataProvider } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/data-provider.js';
import { installEventGraph } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/event-graph.js';
import { installFormat } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/format.js';
import { installOpportunityMap } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/opportunity-map.js';
import { installPortfolioGuide } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/portfolio-guide.js';
import { installReadinessQueue } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/readiness-queue.js';
import { installSeries } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/series.js';
import { isPathInsideRoot } from '../../scripts/capture_dashboard_guide_assets.mjs';
import { installTrustPlaybook } from '../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/trust-playbook.js';

globalThis.__PBKDF2_ITERATIONS__ = 600000;
const secureCore = await import('../../dashboard_action/runtime/scripts/render_dashboard_support/assets/static/dashboard/secure-core.js');

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

function base64(bytes) {
  return Buffer.from(bytes).toString('base64');
}

function base64url(bytes) {
  return base64(bytes).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function validEncryptedToken() {
  return `${base64url(new Uint8Array(12).fill(2))}.${base64url(new Uint8Array([3, 4, 5]))}`;
}

function validEncryptedData() {
  return {
    version: secureCore.EXPECTED_DASHBOARD_DATA_VERSION,
    cipher: secureCore.EXPECTED_CIPHER,
    kdf: {
      name: secureCore.EXPECTED_KDF_NAME,
      hash: secureCore.EXPECTED_KDF_HASH,
      iterations: secureCore.EXPECTED_KDF_ITERATIONS,
    },
    encoding: 'gzip+json',
    salt: base64(new Uint8Array(16).fill(1)),
    summary: validEncryptedToken(),
    chunks: { c0001: validEncryptedToken() },
    chunk_count: 1,
  };
}

function validExportManifest() {
  return {
    version: 1,
    cipher: secureCore.EXPECTED_CIPHER,
    kdf: {
      name: secureCore.EXPECTED_KDF_NAME,
      hash: secureCore.EXPECTED_KDF_HASH,
      iterations: secureCore.EXPECTED_KDF_ITERATIONS,
    },
    asset: 'assets/export-data-abcdef1234567890.enc',
    filename: 'traffic-export.zip',
    ciphertext_size: 3,
    ciphertext_sha256: 'a'.repeat(64),
    plaintext_sha256: 'b'.repeat(64),
    salt: base64(new Uint8Array(16).fill(1)),
    iv: base64(new Uint8Array(12).fill(2)),
  };
}

function dataProviderContext() {
  const state = {
    dashboardData: null,
    chunkLoadErrors: {},
  };
  const CHUNK_FAILURE_LABELS = {
    missing: 'Missing chunk',
    decrypt: 'Decrypt/integrity failure',
    decompress: 'Decompression failure',
    parse: 'JSON parse failure',
    schema: 'Schema mismatch',
    runtime: 'Runtime failure',
  };
  return {
    document: fakeDocument(),
    navigator: {},
    CHUNK_FAILURE_LABELS,
    formatNumber(value) {
      return String(value);
    },
    state,
    dashboardChunkError(stage, message, details) {
      const error = new Error(message);
      error.dashboardDataStage = stage || 'runtime';
      Object.assign(error, details || {});
      return error;
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

test('metric controls use modifier-click for daily chart overlays', () => {
  const classState = new Map();
  const buttons = ['views', 'clones', 'forks'].map((metric) => ({
    dataset: { metric },
    classList: {
      toggle(name, enabled) {
        const classes = classState.get(metric) || new Set();
        if (enabled) classes.add(name);
        else classes.delete(name);
        classState.set(metric, classes);
      },
    },
    setAttribute(name, value) {
      this[name] = value;
    },
  }));
  let updateCount = 0;
  const helpers = installControls({
    document: {
      querySelectorAll(selector) {
        return selector === '.metric-tab' ? buttons : [];
      },
      getElementById() {
        return fakeElement();
      },
    },
    MAX_COMPARE_REPOS: 8,
    METRICS: {
      views: { key: 'views' },
      clones: { key: 'clones' },
      forks: { key: 'forks_delta' },
    },
    getSelectedWindow() {
      return '14';
    },
    getShortName(name) {
      return name;
    },
    getWindowDays() {
      return 14;
    },
    isComparing() {
      return false;
    },
    normalizeWindow(value) {
      return value;
    },
    sanitizeSelection() {},
    state: {
      metric: 'views',
      dailyMetrics: ['views'],
      compareRepos: [],
      selectedRepo: null,
    },
    updateDashboard() {
      updateCount += 1;
    },
  });

  helpers.setMetric('clones');
  assert.deepEqual(helpers.selectedDailyMetricIds(), ['clones']);
  assert.equal(updateCount, 1);

  helpers.setMetric('forks', true);
  assert.deepEqual(helpers.selectedDailyMetricIds(), ['clones', 'forks']);
  assert.equal(updateCount, 2);

  helpers.setMetric('views');
  assert.deepEqual(helpers.selectedDailyMetricIds(), ['views']);

  helpers.setMetric('clones', true);
  helpers.updateMetricTabs();
  assert.equal(buttons.find((button) => button.dataset.metric === 'views')['aria-pressed'], 'true');
  assert.equal(buttons.find((button) => button.dataset.metric === 'clones')['aria-pressed'], 'true');
  assert.equal(buttons.find((button) => button.dataset.metric === 'forks')['aria-pressed'], 'false');
  assert.equal(classState.get('views').has('active'), true);
  assert.equal(classState.get('clones').has('active'), true);
  assert.equal(classState.get('views').has('primary'), true);
});

test('daily chart overlays selected metrics on a shared date axis', () => {
  const title = fakeElement();
  const chart = {
    data: { labels: [], datasets: [] },
    options: { scales: { y: {} } },
    updateCount: 0,
    update() {
      this.updateCount += 1;
    },
  };
  let yAxisDatasetCount = 0;
  const helpers = installCharts({
    document: {
      getElementById(id) {
        return id === 'dailyChartTitle' ? title : fakeElement();
      },
    },
    activateRepo() {},
    buildWeekdaySummaryFromSeries() {
      return {};
    },
    chartOptions() {
      return {};
    },
    compactNumber(value) {
      return String(value);
    },
    computeDelta() {
      return null;
    },
    configureYAxis(_chart, _labels, datasets) {
      yAxisDatasetCount = datasets.length;
    },
    currentPayload() {
      return {};
    },
    dashboardData() {
      return { getRepos: () => [] };
    },
    escapeHtml(value) {
      return String(value);
    },
    formatNumber(value) {
      return String(value);
    },
    formatSigned(value) {
      return String(value);
    },
    getCurrentWindowData() {
      return {
        daily: {
          dates: ['2026-05-14', '2026-05-15'],
          views: [3, 4],
          clones: [1, 5],
          forks_delta: [0, 2],
        },
        totals: {},
      };
    },
    getRepoByName() {
      return null;
    },
    getRepoColor() {
      return '#56b4e9';
    },
    getRepoDash() {
      return [];
    },
    getShortName(name) {
      return name;
    },
    getThemeColor(_name, fallback) {
      return fallback;
    },
    getVisibleRepos() {
      return [];
    },
    hexAlpha(color) {
      return color;
    },
    isComparing() {
      return false;
    },
    metricInfo(metric) {
      return {
        views: { key: 'views', label: 'Views', color: '#6bb8ff' },
        clones: { key: 'clones', label: 'Clones', color: '#d97eb7' },
        forks: { key: 'forks_delta', label: 'Fork Growth', color: '#4fc8a5' },
      }[metric];
    },
    palette: [],
    renderDelta() {},
    renderSparkline() {},
    selectedDailyMetricIds() {
      return ['views', 'clones', 'forks'];
    },
    seriesValueAt(series, key, idx) {
      return series[key][idx];
    },
    setText() {},
    splitWindow() {
      return {};
    },
    state: {
      metric: 'views',
      dailyMetrics: ['views', 'clones', 'forks'],
      compareRepos: [],
      selectedRepo: null,
    },
    charts: { dailyChart: chart },
  });

  helpers.updateDailyChart();

  assert.equal(title.textContent, 'Metric overlays over time');
  assert.deepEqual(chart.data.labels, ['2026-05-14', '2026-05-15']);
  assert.deepEqual(chart.data.datasets.map((dataset) => dataset.label), ['Views', 'Clones', 'Fork Growth']);
  assert.deepEqual(chart.data.datasets.map((dataset) => dataset.metricKey), ['views', 'clones', 'forks_delta']);
  assert.equal(yAxisDatasetCount, 3);
  assert.equal(chart.updateCount, 1);
});

test('series helpers preserve selected-window and growth aggregation contracts', () => {
  const context = {
    MAX_DISPLAY_REPOS: 8,
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

test('series helpers preserve published repository order by default', () => {
  const repos = [
    { name: 'owner/repo-b', views: 5, uniques: 2, clones: 0, clone_uniques: 0, days: 1, updated_at: '2026-06-01T00:00:00Z' },
    { name: 'owner/repo-a', views: 9, uniques: 4, clones: 1, clone_uniques: 1, days: 1, updated_at: '2026-06-20T00:00:00Z' },
    { name: 'owner/repo-c', views: 3, uniques: 1, clones: 0, clone_uniques: 0, days: 1, updated_at: '2026-05-20T00:00:00Z' },
  ];
  const byName = new Map(repos.map((repo) => [repo.name, repo]));
  const context = {
    MAX_DISPLAY_REPOS: 8,
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
      return {
        getRepos() {
          return repos;
        },
        getRepoSummary(name) {
          return byName.get(name);
        },
        getRepoSeries(name) {
          const repo = byName.get(name);
          return {
            dates: ['2026-06-20'],
            views: [repo.views],
            uniques: [repo.uniques],
            clones: [repo.clones],
            clone_uniques: [repo.clone_uniques],
          };
        },
        getRepoGrowth() {
          return {};
        },
      };
    },
    getSelectedWindow() {
      return 'all';
    },
    getWindowCutoffDate() {
      return '';
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
      selectedRepo: null,
    },
  };
  const helpers = installSeries(context);

  assert.deepEqual(
    helpers.getAllRepoMetrics().map((repo) => repo.name),
    ['owner/repo-b', 'owner/repo-a', 'owner/repo-c'],
  );
  assert.deepEqual(
    helpers.getVisibleRepos().map((repo) => repo.name),
    ['owner/repo-b', 'owner/repo-a', 'owner/repo-c'],
  );
});

test('opportunity map projects repos into attention-growth quadrants', () => {
  const helpers = installOpportunityMap({
    document: fakeDocument(),
    activateRepo() {},
    escapeHtml(value) {
      return String(value);
    },
    formatNumber(value) {
      return String(value);
    },
    formatSigned(value) {
      const number = Number(value || 0);
      return `${number >= 0 ? '+' : ''}${number}`;
    },
    getRepoColor() {
      return '#6bb8ff';
    },
    getShortName(name) {
      return name.split('/').pop();
    },
    getVisibleRepos() {
      return [];
    },
  });
  const points = helpers.buildOpportunityPoints([
    { name: 'owner/high-low', views: 1000, uniques: 500, clones: 12, clone_uniques: 5, stars_delta: 0, subscribers_delta: 0, forks_delta: 0 },
    { name: 'owner/high-high', views: 900, uniques: 400, clones: 10, clone_uniques: 3, stars_delta: 8, subscribers_delta: 3, forks_delta: 2 },
    { name: 'owner/low-high', views: 20, uniques: 10, clones: 1, clone_uniques: 1, stars_delta: 11, subscribers_delta: 2, forks_delta: 0 },
    { name: 'owner/low-low', views: 5, uniques: 2, clones: 0, clone_uniques: 0, stars_delta: 0, subscribers_delta: 0, forks_delta: 0 },
  ]);
  const byRepo = new Map(points.map((point) => [point.repo, helpers.classifyOpportunityPoint(point)]));

  assert.equal(points.length, 4);
  assert.equal(byRepo.get('owner/high-low'), 'clarify next step');
  assert.equal(byRepo.get('owner/high-high'), 'amplify');
  assert.equal(byRepo.get('owner/low-high'), 'protect niche pull');
  assert.equal(byRepo.get('owner/low-low'), 'seed discovery');
});

test('trust playbook exposes higher-bar learning tracks and no-signup diagnostics', () => {
  const helpers = installTrustPlaybook({
    document: fakeDocument(),
    currentPayload() {
      return { portfolio_profile: { label: 'Maintainer portfolio' } };
    },
    escapeHtml(value) {
      return String(value);
    },
    formatNumber(value) {
      return String(value);
    },
    getSelectedWindow() {
      return '14';
    },
    getShortName(name) {
      return name.split('/').pop();
    },
    getVisibleRepos() {
      return [
        {
          name: 'owner/app',
          clones: 8,
          clone_uniques: 4,
          stars_delta: 2,
          subscribers_delta: 0,
          forks_delta: 1,
          community: {
            health_percentage: 70,
            has_readme: true,
            has_license: false,
            has_contributing: false,
            has_issue_template: true,
            has_pull_request_template: false,
            has_code_of_conduct: true,
          },
        },
      ];
    },
  });

  const items = helpers.buildTrustPlaybookItems([
    {
      name: 'owner/app',
      clones: 8,
      clone_uniques: 4,
      stars_delta: 2,
      subscribers_delta: 0,
      forks_delta: 1,
      community: {
        health_percentage: 70,
        has_readme: true,
        has_license: false,
        has_contributing: false,
        has_issue_template: true,
        has_pull_request_template: false,
        has_code_of_conduct: true,
      },
    },
  ], { portfolio_profile: { label: 'Maintainer portfolio' } });

  assert.deepEqual(items.map((item) => item.level), ['Level 1', 'Level 2', 'Level 3', 'Level 4', 'Track']);
  assert.equal(items[1].command, 'scorecard --repo=github.com/owner/app --show-details');
  assert.match(items[2].command, /osv-scanner scan -r \./);
  assert.match(items[2].command, /zizmor \./);
  assert.equal(items[3].links.some(([label]) => label === 'SLSA levels'), true);
  assert.equal(items[4].links.some(([label]) => label === 'SOC overview'), true);
});

test('opportunity map keeps focusable repo points visible to assistive tech', () => {
  const mapElement = fakeElement();
  const cardElement = { ...fakeElement(), closest() { return null; } };
  const notesElement = fakeElement();
  const elements = new Map([
    ['opportunity-map', mapElement],
    ['opportunity-card', cardElement],
    ['opportunity-notes', notesElement],
  ]);
  const helpers = installOpportunityMap({
    document: {
      getElementById(id) {
        return elements.get(id) || null;
      },
    },
    activateRepo() {},
    escapeHtml(value) {
      return String(value);
    },
    formatNumber(value) {
      return String(value);
    },
    formatSigned(value) {
      const number = Number(value || 0);
      return `${number >= 0 ? '+' : ''}${number}`;
    },
    getRepoColor() {
      return '#6bb8ff';
    },
    getShortName(name) {
      return name.split('/').pop();
    },
    getVisibleRepos() {
      return [
        { name: 'owner/app', views: 120, uniques: 45, clones: 6, clone_uniques: 3, stars_delta: 1, subscribers_delta: 0, forks_delta: 0 },
      ];
    },
  });

  helpers.renderOpportunityMap();

  assert.match(mapElement.innerHTML, /<svg[^>]*role="group"/);
  assert.doesNotMatch(mapElement.innerHTML, /aria-hidden="true"/);
  assert.match(mapElement.innerHTML, /tabindex="0" role="button"/);
});

test('guide asset containment rejects sibling directories with shared prefixes', () => {
  assert.equal(isPathInsideRoot('/tmp/reponomics-guide', '/tmp/reponomics-guide/index.html'), true);
  assert.equal(isPathInsideRoot('/tmp/reponomics-guide', '/tmp/reponomics-guide'), true);
  assert.equal(isPathInsideRoot('/tmp/reponomics-guide', '/tmp/reponomics-guide-secret/index.html'), false);
  assert.equal(isPathInsideRoot('/tmp/reponomics-guide', '/tmp/other-guide/index.html'), false);
});

test('event graph filters retained code events to the selected window', () => {
  const eventGraph = {
    repos: [
      {
        repo: 'owner/app',
        events: [
          { id: 'commit:old', date: '2026-06-01', type: 'commit', classification: 'docs', title: 'Old docs' },
          { id: 'commit:new', date: '2026-06-10', type: 'commit', classification: 'feature', title: 'New feature' },
          { id: 'release:v1', date: '2026-06-12', type: 'release', classification: 'release', title: 'v1.0.0' },
        ],
      },
      {
        repo: 'owner/hidden',
        events: [
          { id: 'commit:hidden', date: '2026-06-12', type: 'commit', classification: 'fix', title: 'Hidden' },
        ],
      },
    ],
  };
  const helpers = installEventGraph({
    document: fakeDocument(),
    activateRepo() {},
    currentPayload() {
      return { daily: { dates: ['2026-06-01', '2026-06-12'] }, event_graph: eventGraph };
    },
    escapeHtml(value) {
      return String(value);
    },
    formatNumber(value) {
      return String(value);
    },
    getRepoColor() {
      return '#6bb8ff';
    },
    getSelectedWindow() {
      return '7';
    },
    getShortName(name) {
      return name.split('/').pop();
    },
    getVisibleRepos() {
      return [];
    },
    getWindowCutoffDate() {
      return '2026-06-06';
    },
    parseIsoDate(value) {
      return value ? new Date(`${value}T00:00:00Z`) : null;
    },
  });

  const bounds = helpers.eventWindowBounds(eventGraph);
  const lanes = helpers.buildEventLanes(
    eventGraph,
    [{ name: 'owner/app' }],
    bounds,
  );
  const clusters = helpers.buildEventClusters(lanes);

  assert.deepEqual(bounds, { start: '2026-06-06', end: '2026-06-12' });
  assert.equal(lanes.length, 1);
  assert.deepEqual(lanes[0].events.map((event) => event.id), ['commit:new', 'release:v1']);
  assert.deepEqual(clusters.map((cluster) => cluster.date), ['2026-06-10', '2026-06-12']);
  assert.equal(clusters[1].releaseCount, 1);
  assert.equal(clusters[1].repo, 'owner/app');
  assert.equal(helpers.projectEventX('2026-06-06', bounds), 22);
  assert.equal(helpers.projectEventX('2026-06-12', bounds), 95);
});

test('readiness queue ranks visible repo setup gaps', () => {
  const helpers = installReadinessQueue({
    document: fakeDocument(),
    activateRepo() {},
    escapeHtml(value) {
      return String(value);
    },
    formatNumber(value) {
      return String(value);
    },
    getShortName(name) {
      return name.split('/').pop();
    },
    getVisibleRepos() {
      return [];
    },
  });
  const rows = helpers.buildReadinessRows([
    {
      name: 'owner/active-gap',
      activity: 80,
      community: {
        health_percentage: 70,
        has_readme: true,
        has_license: 'false',
        has_contributing: 'false',
        has_issue_template: true,
        has_pull_request_template: true,
        has_code_of_conduct: true,
      },
    },
    {
      name: 'owner/ready',
      activity: 120,
      community: {
        health_percentage: 96,
        has_readme: true,
        has_license: true,
        has_contributing: true,
        has_issue_template: true,
        has_pull_request_template: true,
        has_code_of_conduct: true,
      },
    },
  ]);
  const summary = helpers.readinessSummary(rows);

  assert.equal(rows[0].missing.length, 2);
  assert.equal(rows[0].missing[0].label, 'License');
  assert.match(rows[0].missing[0].href, /^https:\/\/docs\.github\.com\//);
  assert.equal(rows[1].missing.length, 0);
  assert.equal(summary.present, 10);
  assert.equal(summary.known, 12);
  assert.equal(summary.missingRepos, 1);
  assert.equal(summary.avgHealth, 83);
  assert.ok(rows[0].priority > rows[1].priority);
});

test('portfolio guide summarizes dashboard profile signals', () => {
  const helpers = installPortfolioGuide({
    document: fakeDocument(),
    currentPayload() {
      return {};
    },
    escapeHtml(value) {
      return String(value);
    },
    formatNumber(value) {
      return String(value);
    },
  });
  const rows = helpers.signalRows({
    repo_count: 2,
    signals: {
      active_repos: 1,
      quiet_repos: 1,
      recent_event_count: 3,
      readiness_gap_repos: 1,
      maintenance_items: 0,
    },
  });

  assert.deepEqual(rows.map((row) => row[0]), [
    'Published',
    'Active',
    'Quiet',
    'Events',
    'Readiness',
    'Maint.',
  ]);
});

test('secure core validates encrypted dashboard and export metadata contracts', () => {
  const data = validEncryptedData();
  const validated = secureCore.validateEncryptedDashboardData(data);

  assert.deepEqual(Array.from(validated.salt), Array(16).fill(1));
  assert.throws(
    () => secureCore.validateEncryptedDashboardData({ ...data, chunk_count: 2 }),
    /Invalid encrypted dashboard data/,
  );
  assert.throws(
    () => secureCore.validateEncryptedDashboardData({
      ...data,
      chunks: { repo1: validEncryptedToken() },
    }),
    /Invalid encrypted dashboard data/,
  );

  const manifest = secureCore.validateEncryptedExportManifest(validExportManifest());
  assert.deepEqual(Array.from(manifest.salt), Array(16).fill(1));
  assert.deepEqual(Array.from(manifest.iv), Array(12).fill(2));
  assert.throws(
    () => secureCore.validateEncryptedExportManifest({
      ...validExportManifest(),
      asset: 'assets/export-data-not-hex.enc',
    }),
    /Invalid encrypted export metadata/,
  );
});

test('secure core formats delay, storage, filenames, and digests deterministically', async () => {
  assert.equal(secureCore.nextUnlockDelayMs(0), 0);
  assert.equal(secureCore.nextUnlockDelayMs(2), 0);
  assert.equal(secureCore.nextUnlockDelayMs(3), 2000);
  assert.equal(secureCore.nextUnlockDelayMs(4), 4000);
  assert.equal(secureCore.nextUnlockDelayMs(20), 30000);
  assert.equal(secureCore.formatDelay(1), '1 second');
  assert.equal(secureCore.formatDelay(2), '2 seconds');

  assert.equal(
    secureCore.unlockAttemptStorageKey({
      version: 2,
      cipher: 'AES-GCM',
      salt: 'salt',
      summary: '123456789012345678901234567890123456',
      chunk_count: 7,
    }),
    'reponomics-unlock-attempts:2:AES-GCM:salt:12345678901234567890123456789012:7',
  );
  assert.equal(
    secureCore.buildExportFilename(
      'My Export.zip',
      new Date('2026-06-20T12:34:56.789Z'),
    ),
    'My-Export-20260620T123456Z.zip',
  );
  assert.deepEqual(Array.from(secureCore.b64urlToBytes('-_8')), [251, 255]);
  assert.equal(secureCore.bytesToHex(new Uint8Array([0, 15, 255])), '000fff');
  assert.equal(
    await secureCore.sha256Hex(new TextEncoder().encode('abc')),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
  );
});

test('data provider loads lazy plaintext chunks once and exposes loaded rows', async () => {
  const context = dataProviderContext();
  const helpers = installDataProvider(context);
  const provider = helpers.createDashboardDataProvider({
    summary: {
      meta: { default_window: '14' },
      repos: [{ name: 'owner/repo-a' }],
      repo_chunks: { 'owner/repo-a': 'c0001' },
    },
    chunks: {
      c0001: JSON.stringify({
        repo: 'owner/repo-a',
        repo_series: { dates: ['2026-06-20'], views: [7] },
        repo_weekday: { Monday: 3 },
        repo_referrers: [{ referrer: 'example.com', views: 5 }],
        repo_paths: [{ path: '/', views: 4 }],
        growth: {
          per_repo: { stars: 11 },
          series: { dates: ['2026-06-20'], stargazers: [11] },
        },
      }),
    },
  });
  context.state.dashboardData = provider;

  assert.equal(provider.isLazy(), true);
  assert.equal(provider.isRepoLoaded('owner/repo-a'), false);
  const firstLoad = provider.loadRepo('owner/repo-a');
  const secondLoad = provider.loadRepo('owner/repo-a');
  assert.strictEqual(firstLoad, secondLoad);
  await firstLoad;

  assert.equal(provider.isRepoLoaded('owner/repo-a'), true);
  assert.deepEqual(provider.getRepoSeries('owner/repo-a'), {
    dates: ['2026-06-20'],
    views: [7],
  });
  assert.deepEqual(provider.getRepoReferrers('owner/repo-a'), [
    { referrer: 'example.com', views: 5 },
  ]);
  assert.deepEqual(provider.getRepoPaths('owner/repo-a'), [{ path: '/', views: 4 }]);
  assert.deepEqual(provider.getRepoGrowth('owner/repo-a'), {
    stars: 11,
    series: { dates: ['2026-06-20'], stargazers: [11] },
  });
});

test('data provider reports chunk schema diagnostics without loading bad chunks', async () => {
  const context = dataProviderContext();
  const helpers = installDataProvider(context);
  const provider = helpers.createDashboardDataProvider({
    summary: {
      repos: [{ name: 'owner/repo-a' }],
      repo_chunks: { 'owner/repo-a': 'c0001' },
    },
    chunks: {
      c0001: JSON.stringify({ repo: 'owner/repo-a' }),
    },
  });
  context.state.dashboardData = provider;

  assert.throws(
    () => provider.loadRepo('owner/repo-a'),
    (error) => {
      assert.equal(error.dashboardDataStage, 'schema');
      assert.equal(error.chunkId, 'c0001');
      assert.equal(error.missingField, 'repo_series');
      return true;
    },
  );

  const diagnostic = helpers.normalizeChunkLoadError(
    'owner/repo-a',
    Object.assign(new Error('bad json'), {
      dashboardDataStage: 'parse',
      originalName: 'SyntaxError',
      originalMessage: 'Unexpected token',
    }),
  );
  assert.deepEqual(diagnostic, {
    repoName: 'owner/repo-a',
    chunkId: 'c0001',
    mode: 'plaintext',
    stage: 'parse',
    label: 'JSON parse failure',
    summaryDecrypted: false,
    exceptionName: 'SyntaxError',
    exceptionMessage: 'Unexpected token',
    missingField: '',
  });
  assert.equal(
    helpers.chunkDiagnosticsText([diagnostic]),
    [
      'repo=owner/repo-a',
      'chunk_id=c0001',
      'mode=plaintext',
      'stage=parse',
      'summary_decrypted=false',
      'exception_name=SyntaxError',
      'exception_message=Unexpected token',
    ].join('\n'),
  );
  assert.equal(helpers.summarizeChunkErrors([diagnostic]), '1 json parse failure');
});

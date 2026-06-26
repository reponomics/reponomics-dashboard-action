export function installState(context) {
  const dashboardData = (...args) => context.dashboardData(...args);


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
      views:    { key: 'views',         label: 'Views',         color: '#6bb8ff' },
      uniques:  { key: 'uniques',       label: 'Visitors',      color: '#4fc8a5' },
      clones:   { key: 'clones',        label: 'Clones',        color: '#d97eb7' },
      cloners:  { key: 'clone_uniques', label: 'Unique Clones', color: '#f0b75a' },
      stars:    { key: 'stars_delta',   label: 'Star Growth',   color: '#d6a84b', growth: true },
      subscribers: { key: 'subscribers_delta', label: 'Watcher Growth', color: '#6bb8ff', growth: true },
      forks:    { key: 'forks_delta',   label: 'Fork Growth',   color: '#4fc8a5', growth: true }
    };
    const SERIES_METRIC_KEYS = ['views', 'uniques', 'clones', 'clone_uniques', 'stars_delta', 'subscribers_delta', 'forks_delta'];
    const WINDOW_PRESETS = ['7', '14', '30', '90', 'all'];
    const DEFAULT_WINDOW = '14';
    const MAX_DISPLAY_REPOS = 20;
    const MAX_COMPARE_REPOS = 8;
    const CHUNK_FAILURE_LABELS = {
      missing: 'Missing chunk',
      decrypt: 'Decrypt/integrity failure',
      decompress: 'Decompression failure',
      parse: 'JSON parse failure',
      schema: 'Schema mismatch',
      runtime: 'Runtime failure'
    };
    const state = {
      dashboardData: null,
      window: DEFAULT_WINDOW,
      minActivity: 1,
      selectedRepo: null,
      compareRepos: [],
      chunkLoadErrors: {},
      metric: 'views',
      repoSortKey: null,
      repoSortDir: null,
      calendarMonth: null
    };
    function dashboardChunkError(stage, message, details) {
      const error = new Error(message);
      error.dashboardDataStage = stage || 'runtime';
      if (details) {
        Object.keys(details).forEach((key) => {
          error[key] = details[key];
        });
      }
      return error;
    }

  return { palette, DASH_PATTERNS, dashForRepoIndex, getRepoDash, METRICS, SERIES_METRIC_KEYS, WINDOW_PRESETS, DEFAULT_WINDOW, MAX_DISPLAY_REPOS, MAX_COMPARE_REPOS, CHUNK_FAILURE_LABELS, state, dashboardChunkError };
}

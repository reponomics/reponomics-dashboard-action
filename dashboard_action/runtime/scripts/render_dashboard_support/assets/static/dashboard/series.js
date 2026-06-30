export function installSeries(context) {
  const MAX_DISPLAY_REPOS = context.MAX_DISPLAY_REPOS;
  const SERIES_METRIC_KEYS = context.SERIES_METRIC_KEYS;
  const currentPayload = (...args) => context.currentPayload(...args);
  const dashboardData = (...args) => context.dashboardData(...args);
  const getSelectedWindow = (...args) => context.getSelectedWindow(...args);
  const getWindowCutoffDate = (...args) => context.getWindowCutoffDate(...args);
  const hasChunkLoadError = (...args) => context.hasChunkLoadError(...args);
  const isComparing = (...args) => context.isComparing(...args);
  const parseIsoDate = (...args) => context.parseIsoDate(...args);
  const state = context.state;

    function seriesForRange(series) {
      if (!series) {
        return {
          dates: [],
          views: [],
          uniques: [],
          clones: [],
          clone_uniques: [],
          stars_delta: [],
          subscribers_delta: [],
          forks_delta: []
        };
      }
      if (getSelectedWindow() === 'all') {
        return series;
      }

      const cutoff = getWindowCutoffDate();
      if (!cutoff) {
        return series;
      }

      const windowed = {};
      Object.keys(series).forEach((key) => {
        windowed[key] = Array.isArray(series[key]) ? [] : series[key];
      });
      (series.dates || []).forEach((date, idx) => {
        if (date >= cutoff) {
          Object.keys(windowed).forEach((key) => {
            if (!Array.isArray(windowed[key])) return;
            windowed[key].push(key === 'dates' ? date : seriesValueAt(series, key, idx));
          });
        }
      });
      if ('samples' in windowed) {
        windowed.samples = (windowed.dates || []).length;
      }
      return windowed;
    }

    function seriesValueAt(series, key, idx) {
      const values = (series && series[key]) || [];
      return values[idx] === null || values[idx] === undefined ? null : values[idx];
    }

    function latestSeriesValue(series, key, fallback) {
      const values = (series && series[key]) || [];
      if (!values.length) return Number(fallback || 0);
      return Number(values[values.length - 1] || 0);
    }

    function seriesDelta(series, key, fallback) {
      const values = (series && series[key]) || [];
      if (values.length < 2) {
        return values.length === 1 ? 0 : Number(fallback || 0);
      }
      return Number(values[values.length - 1] || 0) - Number(values[0] || 0);
    }

    function buildGrowthDeltaSeries(series) {
      const dates = Array.isArray(series?.dates) ? series.dates.slice() : [];
      const deltaFor = function(sourceKey) {
        return dates.map((_, idx) => {
          const current = seriesValueAt(series, sourceKey, idx);
          if (current === null) return null;
          if (idx === 0) return 0;
          const previous = seriesValueAt(series, sourceKey, idx - 1);
          if (previous === null) return null;
          return Number(current || 0) - Number(previous || 0);
        });
      };
      return {
        dates,
        stars_delta: deltaFor('stargazers'),
        subscribers_delta: deltaFor('subscribers'),
        forks_delta: deltaFor('forks')
      };
    }

    function mergeMetricSeries(trafficSeries, growthDeltaSeries) {
      const dates = [...new Set([
        ...((trafficSeries && trafficSeries.dates) || []),
        ...((growthDeltaSeries && growthDeltaSeries.dates) || [])
      ])].sort();
      const valueMap = function(series, key) {
        const map = new Map();
        (series?.dates || []).forEach((date, idx) => {
          map.set(date, seriesValueAt(series, key, idx));
        });
        return map;
      };
      const maps = Object.fromEntries(
        SERIES_METRIC_KEYS.map((key) => [
          key,
          valueMap(['stars_delta', 'subscribers_delta', 'forks_delta'].includes(key) ? growthDeltaSeries : trafficSeries, key)
        ])
      );
      const merged = { dates };
      SERIES_METRIC_KEYS.forEach((key) => {
        merged[key] = dates.map((date) => maps[key].has(date) ? maps[key].get(date) : null);
      });
      return merged;
    }

    function buildRepoMetrics(repoName) {
      const data = dashboardData();
      const baseRepo = data?.getRepoSummary(repoName) || {};
      const series = seriesForRange(data?.getRepoSeries(repoName));
      const growthRow = data?.getRepoGrowth(repoName) || {};
      const deltas = growthRow.deltas || {};
      const growthSeries = seriesForRange(growthRow.series || {});
      const growthDeltaSeries = buildGrowthDeltaSeries(growthSeries);
      const chartSeries = mergeMetricSeries(series, growthDeltaSeries);
      const sum = (values) => (values || []).reduce((total, value) => total + Number(value || 0), 0);
      const hasSeries = (series.dates || []).length > 0;
      const starsDelta = seriesDelta(growthSeries, 'stargazers', deltas.stars_delta || deltas.stargazers_delta);
      const subscribersDelta = seriesDelta(growthSeries, 'subscribers', deltas.subscribers_delta);
      const forksDelta = seriesDelta(growthSeries, 'forks', deltas.forks_delta);
      const community = baseRepo.community || {};
      const communityHealth = Number(community.health_percentage);
      return {
        name: repoName,
        views: hasSeries ? sum(series.views) : Number(baseRepo.views || 0),
        uniques: hasSeries ? sum(series.uniques) : Number(baseRepo.uniques || 0),
        clones: hasSeries ? sum(series.clones) : Number(baseRepo.clones || 0),
        clone_uniques: hasSeries ? sum(series.clone_uniques) : Number(baseRepo.clone_uniques || 0),
        created_at: String(baseRepo.created_at || ''),
        pushed_at: String(baseRepo.pushed_at || ''),
        updated_at: String(baseRepo.updated_at || ''),
        stars_delta: starsDelta,
        subscribers_delta: subscribersDelta,
        forks_delta: forksDelta,
        stars: latestSeriesValue(growthSeries, 'stargazers', deltas.current_stars || deltas.current_stargazers),
        subscribers: latestSeriesValue(growthSeries, 'subscribers', deltas.current_subscribers),
        forks: latestSeriesValue(growthSeries, 'forks', deltas.current_forks),
        days: hasSeries ? (series.dates || []).length : Number(baseRepo.days || 0),
        activity: (hasSeries ? sum(series.views) : Number(baseRepo.views || 0))
          + (hasSeries ? sum(series.clones) : Number(baseRepo.clones || 0)),
        community: {
          available: !!community.available,
          health_percentage: Number.isFinite(communityHealth) ? communityHealth : null,
          documentation: String(community.documentation || ''),
          updated_at: String(community.updated_at || ''),
          content_reports_enabled: community.content_reports_enabled,
          has_code_of_conduct: community.has_code_of_conduct,
          has_contributing: community.has_contributing,
          has_issue_template: community.has_issue_template,
          has_pull_request_template: community.has_pull_request_template,
          has_readme: community.has_readme,
          has_license: community.has_license
        },
        series: chartSeries
      };
    }

    function repoFreshnessTimestamp(repo) {
      return String(repo.updated_at || repo.pushed_at || repo.created_at || '');
    }

    function compareRepoFreshness(a, b) {
      const av = repoFreshnessTimestamp(a);
      const bv = repoFreshnessTimestamp(b);
      if (av && bv && av !== bv) return bv.localeCompare(av);
      if (av && !bv) return -1;
      if (!av && bv) return 1;
      return 0;
    }

    function getAllRepoMetrics() {
      return (dashboardData()?.getRepos() || [])
        .map((repo) => buildRepoMetrics(repo.name));
    }

    function getSelectableRepos() {
      return getAllRepoMetrics()
        .filter((repo) => !hasChunkLoadError(repo.name));
    }

    function getVisibleRepos() {
      const selectable = getSelectableRepos();
      const byName = new Map(selectable.map((repo) => [repo.name, repo]));
      const prioritized = [];
      const add = function(repoName) {
        const repo = byName.get(repoName);
        if (repo && !prioritized.some((item) => item.name === repo.name)) {
          prioritized.push(repo);
        }
      };
      if (state.selectedRepo) {
        add(state.selectedRepo);
      }
      state.compareRepos.forEach(add);
      selectable.forEach((repo) => {
        if (prioritized.length < MAX_DISPLAY_REPOS) {
          add(repo.name);
        }
      });
      return prioritized.slice(0, MAX_DISPLAY_REPOS);
    }

    function buildAggregateSeries(repos) {
      const byDate = new Map();
      repos.forEach((repo) => {
        const series = repo.series || {};
        (series.dates || []).forEach((date, idx) => {
          const current = byDate.get(date) || {
            samples: Object.fromEntries(SERIES_METRIC_KEYS.map((key) => [key, 0]))
          };
          SERIES_METRIC_KEYS.forEach((key) => {
            if (!(key in current)) current[key] = 0;
            const value = seriesValueAt(series, key, idx);
            if (value !== null) {
              current[key] += Number(value || 0);
              current.samples[key] += 1;
            }
          });
          byDate.set(date, current);
        });
      });
      const dates = [...byDate.keys()].sort();
      const projected = (date, key) => {
        const row = byDate.get(date);
        return row.samples[key] ? row[key] : null;
      };
      return Object.assign(
        { dates },
        Object.fromEntries(SERIES_METRIC_KEYS.map((key) => [key, dates.map((date) => projected(date, key))]))
      );
    }

    function buildWeekdaySummaryFromSeries(seriesMap) {
      const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      const totals = labels.map(() => ({
        samples: Object.fromEntries(SERIES_METRIC_KEYS.map((key) => [key, 0]))
      }));
      Object.values(seriesMap || {}).forEach((series) => {
        (series.dates || []).forEach((date, idx) => {
          const parsed = parseIsoDate(date);
          if (!parsed) return;
          const weekday = (parsed.getUTCDay() + 6) % 7;
          SERIES_METRIC_KEYS.forEach((key) => {
            if (!(key in totals[weekday])) totals[weekday][key] = 0;
            const value = seriesValueAt(series, key, idx);
            if (value !== null) {
              totals[weekday][key] += Number(value || 0);
              totals[weekday].samples[key] += 1;
            }
          });
        });
      });
      const avg = (field) => totals.map((b) => b.samples[field] ? Math.round((b[field] / b.samples[field]) * 10) / 10 : 0);
      return Object.assign(
        { labels },
        Object.fromEntries(SERIES_METRIC_KEYS.map((key) => [key, avg(key)]))
      );
    }

    function getCurrentWindowData() {
      const repos = getVisibleRepos();
      const aggregate = buildAggregateSeries(repos);
      const totals = repos.reduce((acc, repo) => {
        acc.repo_count += 1;
        acc.total_views += repo.views;
        acc.total_uniques += repo.uniques;
        acc.total_clones += repo.clones;
        acc.total_clone_uniques += repo.clone_uniques;
        acc.total_stars_delta += repo.stars_delta;
        acc.total_subscribers_delta += repo.subscribers_delta;
        acc.total_forks_delta += repo.forks_delta;
        acc.total_stars += repo.stars;
        acc.total_subscribers += repo.subscribers;
        acc.total_forks += repo.forks;
        return acc;
      }, {
        repo_count: 0,
        total_views: 0,
        total_uniques: 0,
        total_clones: 0,
        total_clone_uniques: 0,
        total_stars_delta: 0,
        total_subscribers_delta: 0,
        total_forks_delta: 0,
        total_stars: 0,
        total_subscribers: 0,
        total_forks: 0
      });
      return {
        repos,
        totals,
        daily: aggregate,
        weekday: buildWeekdaySummaryFromSeries(
          Object.fromEntries(repos.map((repo) => [repo.name, repo.series]))
        )
      };
    }

    function aggregateSnapshotRows(rowsByRepo, selectedRepos, keyField) {
      const totals = new Map();
      selectedRepos.forEach((repoName) => {
        (rowsByRepo?.[repoName] || []).forEach((row) => {
          const key = row[keyField] || '';
          const current = totals.get(key) || { ...row, count: 0, uniques: 0 };
          current.count += Number(row.count || 0);
          current.uniques += Number(row.uniques || 0);
          totals.set(key, current);
        });
      });
      return [...totals.values()].sort((a, b) => (b.count - a.count) || String(a[keyField]).localeCompare(String(b[keyField])));
    }

    function getCurrentSnapshotRepoNames() {
      if (isComparing()) {
        return state.compareRepos;
      }
      if (state.selectedRepo) {
        return [state.selectedRepo];
      }
      return getVisibleRepos().map((repo) => repo.name);
    }

    function getCurrentReferrerRows() {
      if (!isComparing() && !state.selectedRepo) {
        return currentPayload()?.referrers || [];
      }
      return aggregateSnapshotRows(
        dashboardData()?.getReferrersByRepo(),
        getCurrentSnapshotRepoNames(),
        'referrer'
      );
    }

    function getCurrentPathRows() {
      if (!isComparing() && !state.selectedRepo) {
        return currentPayload()?.paths || [];
      }
      return aggregateSnapshotRows(
        dashboardData()?.getPathsByRepo(),
        getCurrentSnapshotRepoNames(),
        'path'
      );
    }

  return { seriesForRange, seriesValueAt, latestSeriesValue, seriesDelta, buildGrowthDeltaSeries, mergeMetricSeries, buildRepoMetrics, repoFreshnessTimestamp, compareRepoFreshness, getAllRepoMetrics, getSelectableRepos, getVisibleRepos, buildAggregateSeries, buildWeekdaySummaryFromSeries, getCurrentWindowData, aggregateSnapshotRows, getCurrentSnapshotRepoNames, getCurrentReferrerRows, getCurrentPathRows };
}

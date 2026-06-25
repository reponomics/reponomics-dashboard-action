export function installStory(context) {
  const document = context.document;
  const buildAggregateSeries = (...args) => context.buildAggregateSeries(...args);
  const compactNumber = (...args) => context.compactNumber(...args);
  const currentPayload = (...args) => context.currentPayload(...args);
  const escapeHtml = (...args) => context.escapeHtml(...args);
  const formatIsoDate = (...args) => context.formatIsoDate(...args);
  const formatNumber = (...args) => context.formatNumber(...args);
  const formatSigned = (...args) => context.formatSigned(...args);
  const getCurrentPathRows = (...args) => context.getCurrentPathRows(...args);
  const getCurrentReferrerRows = (...args) => context.getCurrentReferrerRows(...args);
  const getCurrentWindowData = (...args) => context.getCurrentWindowData(...args);
  const getShortName = (...args) => context.getShortName(...args);
  const getThemeColor = (...args) => context.getThemeColor(...args);
  const getVisibleRepos = (...args) => context.getVisibleRepos(...args);
  const hexAlpha = (...args) => context.hexAlpha(...args);
  const isComparing = (...args) => context.isComparing(...args);
  const parseIsoDate = (...args) => context.parseIsoDate(...args);
  const state = context.state;

  const READINESS_SIGNALS = [
    { key: 'has_readme', label: 'README', action: 'Improve the README so visitors immediately understand setup, value, and next steps.' },
    { key: 'has_license', label: 'License', action: 'Add a license so interested users know whether they can adopt the project.' },
    { key: 'has_contributing', label: 'Contributing', action: 'Add contribution guidance before attention turns into drive-by confusion.' },
    { key: 'has_issue_template', label: 'Issue template', action: 'Add an issue template so new attention produces usable reports.' },
    { key: 'has_pull_request_template', label: 'PR template', action: 'Add a pull request template so incoming changes carry review context.' },
    { key: 'has_code_of_conduct', label: 'Code of conduct', action: 'Add a code of conduct to make public participation expectations explicit.' },
  ];

  const STORY_METRICS = [
    { key: 'views', label: 'views', noun: 'views', floor: 5 },
    { key: 'uniques', label: 'visitors', noun: 'visitors', floor: 3 },
    { key: 'clones', label: 'clones', noun: 'clones', floor: 3 },
    { key: 'clone_uniques', label: 'unique cloners', noun: 'unique cloners', floor: 2 },
    { key: 'stars_delta', label: 'stars', noun: 'stars', floor: 1, growth: true },
    { key: 'subscribers_delta', label: 'watchers', noun: 'watchers', floor: 1, growth: true },
    { key: 'forks_delta', label: 'forks', noun: 'forks', floor: 1, growth: true },
  ];

  const ACTION_INSIGHT_SUBTYPES = new Set([
    'high_attention_low_interest',
    'traffic_without_downstream_growth',
    'clone_heavy_star_light',
    'negative_counter_movement',
  ]);

  const POSITIVE_INSIGHT_SUBTYPES = new Set([
    'quiet_resonance',
    'downstream_without_traffic_spike',
    'fork_spike',
    'watcher_subscriber_spike',
  ]);

  function contextPayload() {
    return currentPayload()?.context || {};
  }

  function asArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function scopeRepoNames() {
    if (isComparing()) return state.compareRepos.slice();
    if (state.selectedRepo) return [state.selectedRepo];
    return getVisibleRepos().map((repo) => repo.name);
  }

  function latestTrafficDate() {
    const dates = currentPayload()?.daily?.dates || [];
    return dates.length ? dates[dates.length - 1] : '';
  }

  function daysBetweenIso(a, b) {
    const da = parseIsoDate(a);
    const db = parseIsoDate(b);
    if (!da || !db) return Infinity;
    return Math.round(Math.abs(da.getTime() - db.getTime()) / 86400000);
  }

  function dateLabel(iso) {
    const date = parseIsoDate(String(iso || '').slice(0, 10));
    if (!date) return iso || '';
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' });
  }

  function eventLabel(event) {
    if (event.event_type === 'release') return 'Release';
    if (event.event_type === 'commit') return event.classification ? titleCase(event.classification) : 'Commit';
    return titleCase(event.event_type || event.classification || 'Event');
  }

  function titleCase(value) {
    return String(value || '')
      .replace(/[_-]+/g, ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/"/g, '&quot;');
  }

  function scopedEvents() {
    const repos = new Set(scopeRepoNames());
    return asArray(contextPayload().events).filter((event) => repos.has(event.repo));
  }

  function nearbyEvent(repoName, anchorDate) {
    if (!repoName || !anchorDate) return null;
    return asArray(contextPayload().events)
      .filter((event) => event.repo === repoName && event.event_date)
      .map((event) => ({ event, distance: daysBetweenIso(event.event_date, anchorDate) }))
      .filter((item) => item.distance <= 14)
      .sort((a, b) => a.distance - b.distance || Number(b.event.magnitude || 0) - Number(a.event.magnitude || 0))[0]?.event || null;
  }

  function visibleInsights() {
    const repos = new Set(scopeRepoNames());
    return asArray(currentPayload()?.insights_v2).filter((insight) => !insight.repo || repos.has(insight.repo));
  }

  function topInsight() {
    return visibleInsights()[0] || asArray(currentPayload()?.insights_v2)[0] || null;
  }

  function readinessRows() {
    return getVisibleRepos().map((repo) => {
      const community = repo.community || {};
      const missing = READINESS_SIGNALS.filter((signal) => asBool(community[signal.key]) === false);
      const known = READINESS_SIGNALS.filter((signal) => asBool(community[signal.key]) !== null);
      const present = known.filter((signal) => asBool(community[signal.key]) === true).length;
      const health = Number(community.health_percentage);
      return {
        repo,
        health: Number.isFinite(health) ? health : null,
        missing,
        knownCount: known.length,
        presentCount: present,
      };
    });
  }

  function asBool(value) {
    if (value === true || value === false) return value;
    const normalized = String(value || '').trim().toLowerCase();
    if (!normalized) return null;
    if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
    if (['false', '0', 'no', 'off'].includes(normalized)) return false;
    return null;
  }

  function finiteNumber(value) {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function median(values) {
    const sorted = values.map(finiteNumber).filter((value) => value !== null).sort((a, b) => a - b);
    if (!sorted.length) return null;
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }

  function sumMetricValues(values, metric) {
    return values.reduce((total, value) => {
      const number = finiteNumber(value);
      if (number === null) return total;
      return total + (metric.growth ? Math.max(0, number) : number);
    }, 0);
  }

  function formatMetricValue(metric, value) {
    return metric.growth ? formatSigned(value) : formatNumber(value);
  }

  function insightScore(insight) {
    return Number(insight?.score || 0)
      + Math.log1p(Math.abs(Number(insight?.delta || insight?.downstream_delta || insight?.traffic || insight?.clones || 0)));
  }

  function isPositiveInsight(insight) {
    if (!insight) return false;
    if (insight.kind === 'trend') return Number(insight.delta || 0) > 0;
    if (insight.kind === 'spike') return insight.direction === 'spiked';
    if (insight.kind === 'growth') {
      if (POSITIVE_INSIGHT_SUBTYPES.has(insight.subtype)) return true;
      if (ACTION_INSIGHT_SUBTYPES.has(insight.subtype)) return false;
      return Number(insight.delta || insight.downstream_delta || 0) > 0;
    }
    return false;
  }

  function isActionInsight(insight) {
    if (!insight) return false;
    if (insight.kind === 'trend') return Number(insight.delta || 0) < 0;
    if (insight.kind === 'spike') return insight.direction === 'dropped';
    if (insight.kind === 'growth') return ACTION_INSIGHT_SUBTYPES.has(insight.subtype) || Number(insight.delta || 0) < 0;
    return false;
  }

  function findSeriesAnomalies(kind = 'positive') {
    const latest = latestTrafficDate();
    const candidates = [];
    getVisibleRepos().forEach((repo) => {
      const series = repo.series || {};
      const dates = asArray(series.dates);
      STORY_METRICS.forEach((metric) => {
        const values = asArray(series[metric.key]);
        dates.forEach((date, idx) => {
          const current = finiteNumber(values[idx]);
          if (idx < 5 || current === null) return;
          const baselineValues = values
            .slice(Math.max(0, idx - 10), idx)
            .map(finiteNumber)
            .filter((value) => value !== null);
          if (baselineValues.length < 4) return;
          const baseline = median(baselineValues);
          if (baseline === null) return;
          const delta = current - baseline;
          const threshold = metric.growth
            ? metric.floor
            : Math.max(metric.floor, Math.abs(baseline) * 0.55);
          const positive = delta >= threshold && current >= metric.floor;
          const negative = -delta >= threshold && baseline >= metric.floor;
          if ((kind === 'positive' && !positive) || (kind === 'negative' && !negative)) return;
          const daysAgo = daysBetweenIso(date, latest);
          const recency = Number.isFinite(daysAgo) ? Math.max(0, 14 - daysAgo) / 3 : 0;
          candidates.push({
            repo,
            metric,
            date,
            index: idx,
            current,
            baseline,
            delta,
            score: Math.log1p(Math.abs(delta)) + Math.log1p(Math.abs(current)) + recency,
          });
        });
      });
    });
    return candidates.sort((a, b) => b.score - a.score || String(b.date).localeCompare(String(a.date)));
  }

  function anomalyEvidence(anomaly) {
    const event = nearbyEvent(anomaly.repo.name, anomaly.date);
    const evidence = [
      { label: 'Metric', value: formatMetricValue(anomaly.metric, Math.round(anomaly.current)), meta: anomaly.metric.label },
      { label: 'Baseline', value: formatMetricValue(anomaly.metric, Math.round(anomaly.baseline)), meta: 'recent median' },
      { label: 'Date', value: dateLabel(anomaly.date), meta: 'spike day' },
    ];
    if (event) {
      evidence.push({
        label: eventLabel(event),
        value: dateLabel(event.event_date),
        meta: event.title || event.event_id,
      });
    }
    return evidence;
  }

  function anomalyStory(anomaly, options = {}) {
    const shortRepo = getShortName(anomaly.repo.name);
    const positive = anomaly.delta >= 0;
    const verb = positive ? 'jumped' : 'fell';
    return {
      tab: options.tab || (positive ? 'Bright spot' : 'Fix next'),
      tone: options.tone || (positive ? 'positive' : 'action'),
      headline: `${shortRepo} ${anomaly.metric.label} ${verb} away from the usual line`,
      summary: positive
        ? `${titleCase(anomaly.metric.label)} landed above its recent baseline on ${dateLabel(anomaly.date)}. That is the kind of movement worth checking while the trail is fresh.`
        : `${titleCase(anomaly.metric.label)} came in below its recent baseline on ${dateLabel(anomaly.date)}. Look at what changed nearby before the pattern gets stale.`,
      evidence: anomalyEvidence(anomaly),
      score: anomaly.score,
    };
  }

  function followThroughStory() {
    const candidates = findSeriesAnomalies('positive')
      .map((anomaly) => {
        const series = anomaly.repo.series || {};
        const values = asArray(series[anomaly.metric.key]);
        const dates = asArray(series.dates);
        const followValues = values
          .slice(anomaly.index + 1, Math.min(values.length, anomaly.index + 4))
          .map(finiteNumber)
          .filter((value) => value !== null);
        if (followValues.length < 2) return null;
        const followTotal = sumMetricValues(followValues, anomaly.metric);
        const baselineTotal = Math.max(0, anomaly.baseline) * followValues.length;
        const continued = anomaly.metric.growth
          ? followTotal >= anomaly.metric.floor
          : followTotal >= Math.max(anomaly.metric.floor, baselineTotal * 0.85);
        if (!continued) return null;
        const endDate = dates[Math.min(dates.length - 1, anomaly.index + followValues.length)];
        return {
          anomaly,
          followDays: followValues.length,
          followTotal,
          endDate,
          score: anomaly.score + Math.log1p(followTotal),
        };
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score);
    const item = candidates[0];
    if (!item) return null;
    const { anomaly } = item;
    const event = nearbyEvent(anomaly.repo.name, anomaly.date);
    const shortRepo = getShortName(anomaly.repo.name);
    const summaryTail = event
      ? ` The nearest repo event was ${eventLabel(event).toLowerCase()} activity on ${dateLabel(event.event_date)}.`
      : '';
    const added = formatMetricValue(anomaly.metric, Math.round(item.followTotal));
    return {
      tab: 'Follow-up',
      tone: 'context',
      headline: `${shortRepo} had follow-through after ${dateLabel(anomaly.date)}`,
      summary: `${titleCase(anomaly.metric.label)} jumped on ${dateLabel(anomaly.date)}; over the next ${item.followDays} days it added ${added} more. The daily read: this did not stop at the spike day.${summaryTail}`,
      evidence: [
        { label: 'Spike day', value: formatMetricValue(anomaly.metric, Math.round(anomaly.current)), meta: dateLabel(anomaly.date) },
        { label: 'Next ' + item.followDays + ' days', value: added, meta: anomaly.metric.noun },
        { label: 'Recent baseline', value: formatMetricValue(anomaly.metric, Math.round(anomaly.baseline)), meta: 'median before the jump' },
        ...(event ? [{ label: eventLabel(event), value: dateLabel(event.event_date), meta: event.title || event.event_id }] : []),
      ],
      score: item.score,
    };
  }

  function latestEventStory() {
    const event = scopedEvents()[0];
    if (!event) return null;
    const release = event.event_type === 'release';
    return {
      tab: 'Context',
      tone: 'context',
      headline: `${getShortName(event.repo)} ${release ? 'shipped a release' : 'changed code'} recently`,
      summary: `${eventLabel(event)} activity on ${dateLabel(event.event_date)} gives the next few traffic and growth days something concrete to react to.`,
      evidence: [
        { label: eventLabel(event), value: dateLabel(event.event_date), meta: event.title || event.event_id },
        { label: 'Repo', value: getShortName(event.repo), meta: 'selected scope' },
      ],
      score: Number(event.magnitude || 0),
    };
  }

  function describeInsight(insight, options = {}) {
    if (!insight) return null;
    const repo = insight.repo || '';
    const shortRepo = getShortName(repo);
    const anchorDate = latestTrafficDate();
    const event = nearbyEvent(repo, anchorDate);
    const evidence = [];
    let headline = shortRepo ? shortRepo + ' has the clearest movement' : 'The selected window has a clear movement';
    let summary = insight.text || 'A traffic or growth pattern stands out in the selected window.';

    if (insight.kind === 'trend') {
      const direction = insight.pct === null || insight.pct === undefined
        ? 'started getting activity'
        : (Number(insight.pct) > 0 ? 'is gaining attention' : 'cooled off');
      headline = `${shortRepo} ${direction}`;
      summary = `${titleCase(insight.metric)} moved from ${formatNumber(insight.prior)} to ${formatNumber(insight.current)} over ${formatNumber(insight.window_days)} days.`;
      evidence.push({ label: titleCase(insight.metric), value: formatSigned(insight.delta), meta: 'window delta' });
    } else if (insight.kind === 'spike') {
      headline = `${shortRepo} had a ${insight.direction === 'spiked' ? 'jump' : 'drop'} in ${insight.metric}`;
      summary = `${titleCase(insight.metric)} ${insight.direction} versus the trailing median.`;
      evidence.push({ label: 'Latest', value: formatNumber(insight.current), meta: `${titleCase(insight.metric)} on the latest day` });
      evidence.push({ label: 'Baseline', value: formatNumber(Math.round(Number(insight.baseline || 0))), meta: 'trailing median' });
    } else if (insight.kind === 'growth') {
      if (insight.subtype === 'quiet_resonance') {
        headline = `${shortRepo} is resonating with a small crowd`;
        summary = `Downstream signals moved on ${formatNumber(insight.traffic)} views. Small audience, real intent.`;
      } else if (insight.subtype === 'downstream_without_traffic_spike') {
        headline = `${shortRepo} got interest without a traffic wave`;
        summary = `Stars, watchers, or forks moved even though traffic stayed modest. That is a good candidate for word-of-mouth or a niche user finding it useful.`;
      } else if (insight.subtype === 'fork_spike') {
        headline = `${shortRepo} picked up fork activity`;
        summary = `Forks moved in the selected window, which is usually closer to "I may use this" than casual browsing.`;
      } else if (insight.subtype === 'watcher_subscriber_spike') {
        headline = `${shortRepo} picked up watchers`;
        summary = `Watchers rose in the selected window. Someone wants to keep tabs on what happens next.`;
      } else if (insight.subtype === 'clone_heavy_star_light') {
        headline = `${shortRepo} is getting tried, not saved`;
        summary = `Clone activity is ahead of stars. Make the first-run path and next step more obvious while people are already pulling the code.`;
      } else if (ACTION_INSIGHT_SUBTYPES.has(insight.subtype)) {
        headline = `${shortRepo} has attention to convert`;
        summary = `People are showing up, but downstream signals are not moving with them yet. Tighten the handoff from visitor to user.`;
      } else {
        headline = `${shortRepo} has a cross-signal growth pattern`;
        summary = insight.text || summary;
      }
      if (insight.traffic !== undefined) evidence.push({ label: 'Views', value: formatNumber(insight.traffic), meta: 'attention' });
      if (insight.visitors !== undefined) evidence.push({ label: 'Visitors', value: formatNumber(insight.visitors), meta: 'reach' });
      if (insight.clones !== undefined) evidence.push({ label: 'Clones', value: formatNumber(insight.clones), meta: 'adoption' });
      if (insight.downstream_delta !== undefined) evidence.push({ label: 'Downstream', value: formatSigned(insight.downstream_delta), meta: 'stars, watchers, forks' });
      if (insight.delta !== undefined) evidence.push({ label: titleCase(insight.metric), value: formatSigned(insight.delta), meta: 'growth counter' });
    }

    if (event) {
      evidence.push({
        label: eventLabel(event),
        value: dateLabel(event.event_date),
        meta: event.title || event.event_id,
      });
      summary += ` The useful context is ${eventLabel(event).toLowerCase()} activity on ${dateLabel(event.event_date)}.`;
    }

    const repoRow = readinessRows().find((row) => row.repo.name === repo);
    if (repoRow && repoRow.health !== null) {
      evidence.push({ label: 'Readiness', value: formatNumber(repoRow.health) + '%', meta: 'community profile' });
    }

    return {
      tab: options.tab || 'Context',
      tone: options.tone || (isActionInsight(insight) ? 'action' : (isPositiveInsight(insight) ? 'positive' : 'context')),
      headline,
      summary,
      evidence,
      score: insightScore(insight),
    };
  }

  function quietNarrative(kind = 'context') {
    const rows = readinessRows().filter((row) => row.missing.length);
    const events = scopedEvents();
    const releases = asArray(contextPayload().releases);
    const evidence = [];

    if (rows.length) {
      const row = rows.slice().sort((a, b) => (a.health ?? 101) - (b.health ?? 101))[0];
      evidence.push({
        label: 'Readiness gap',
        value: getShortName(row.repo.name),
        meta: row.missing.slice(0, 2).map((item) => item.label).join(', '),
      });
    }
    if (events.length) {
      const latest = events[0];
      evidence.push({
        label: eventLabel(latest),
        value: dateLabel(latest.event_date),
        meta: latest.title || latest.event_id,
      });
    }
    if (releases.length) {
      evidence.push({
        label: 'Recent release',
        value: releases[0].tag_name || releases[0].name,
        meta: getShortName(releases[0].repo),
      });
    }

    if (kind === 'positive') {
      return {
        tab: 'Bright spot',
        tone: 'positive',
        headline: 'The baseline is getting cleaner',
        summary: 'No huge move is showing right now, which means the next release, docs push, or refactor gets a cleaner before-and-after.',
        evidence,
      };
    }
    if (kind === 'action') {
      const row = rows.slice().sort((a, b) => (a.health ?? 101) - (b.health ?? 101))[0];
      return {
        tab: 'Fix next',
        tone: 'action',
        headline: row ? `${getShortName(row.repo.name)} has an easy front-door win` : 'Pick one small public-facing improvement',
        summary: row
          ? `${row.missing[0].label} is missing. That is a quick way to make quiet traffic more useful when the next bump arrives.`
          : 'When traffic is quiet, docs, examples, topics, and release notes are the highest-leverage cleanup work.',
        evidence,
      };
    }
    return {
      tab: 'Context',
      tone: 'context',
      headline: rows.length ? 'Traffic is steady. Fix the obvious leaks.' : 'No big swing today. That is still useful.',
      summary: rows.length
        ? 'Nothing is swinging hard right now, so use the calm window to make the repos easier to understand, trust, and try.'
        : 'Nothing is swinging hard yet. Keep collecting so the next release, docs push, or refactor has a clean before and after.',
      evidence,
    };
  }

  function buildPositiveStory() {
    const insight = visibleInsights().filter(isPositiveInsight).sort((a, b) => insightScore(b) - insightScore(a))[0];
    if (insight) return describeInsight(insight, { tab: 'Bright spot', tone: 'positive' });
    const anomaly = findSeriesAnomalies('positive')[0];
    if (anomaly) return anomalyStory(anomaly, { tab: 'Bright spot', tone: 'positive' });
    const ready = readinessRows()
      .filter((row) => row.health !== null && row.health >= 80)
      .sort((a, b) => b.repo.activity - a.repo.activity)[0];
    if (ready) {
      return {
        tab: 'Bright spot',
        tone: 'positive',
        headline: `${getShortName(ready.repo.name)} is ready for visitors`,
        summary: `The public-readiness profile is at ${formatNumber(ready.health)}%. When attention lands here, the basics are already in place.`,
        evidence: [
          { label: 'Readiness', value: formatNumber(ready.health) + '%', meta: 'community profile' },
          { label: 'Activity', value: formatNumber(ready.repo.activity), meta: 'views + clones in scope' },
        ],
      };
    }
    return quietNarrative('positive');
  }

  function buildContextStory() {
    const follow = followThroughStory();
    if (follow) return follow;
    const anomaly = findSeriesAnomalies('positive')[0] || findSeriesAnomalies('negative')[0];
    if (anomaly) {
      const event = nearbyEvent(anomaly.repo.name, anomaly.date);
      if (event) {
        return {
          tab: 'Context',
          tone: 'context',
          headline: `${getShortName(anomaly.repo.name)} had repo activity near the movement`,
          summary: `${titleCase(anomaly.metric.label)} moved on ${dateLabel(anomaly.date)}, with ${eventLabel(event).toLowerCase()} activity nearby. That gives the traffic pattern a concrete repo-side timestamp.`,
          evidence: [
            { label: 'Movement', value: formatMetricValue(anomaly.metric, Math.round(anomaly.current)), meta: `${anomaly.metric.label} on ${dateLabel(anomaly.date)}` },
            { label: eventLabel(event), value: dateLabel(event.event_date), meta: event.title || event.event_id },
            { label: 'Baseline', value: formatMetricValue(anomaly.metric, Math.round(anomaly.baseline)), meta: 'recent median' },
          ],
          score: anomaly.score,
        };
      }
    }
    return latestEventStory() || quietNarrative('context');
  }

  function buildActionStory() {
    const insight = visibleInsights().filter(isActionInsight).sort((a, b) => insightScore(b) - insightScore(a))[0];
    if (insight) return describeInsight(insight, { tab: 'Fix next', tone: 'action' });
    const anomaly = findSeriesAnomalies('negative')[0];
    if (anomaly) return anomalyStory(anomaly, { tab: 'Fix next', tone: 'action' });
    const row = readinessRows()
      .filter((item) => item.missing.length)
      .sort((a, b) => (a.health ?? 101) - (b.health ?? 101) || b.repo.activity - a.repo.activity)[0];
    if (row) {
      const missing = row.missing[0];
      return {
        tab: 'Fix next',
        tone: 'action',
        headline: `${getShortName(row.repo.name)} needs ${missing.label.toLowerCase()} before the next bump`,
        summary: missing.action,
        evidence: [
          { label: 'Missing', value: missing.label, meta: 'public readiness' },
          { label: 'Readiness', value: row.health === null ? '-' : formatNumber(row.health) + '%', meta: 'community profile' },
          { label: 'Traffic', value: formatNumber(row.repo.views), meta: 'views in scope' },
        ],
      };
    }
    return quietNarrative('action');
  }

  function buildStoryCards() {
    const cards = [buildPositiveStory(), buildContextStory(), buildActionStory()].filter(Boolean);
    const seen = new Set();
    const deduped = cards.filter((card) => {
      const key = `${card.tab}:${card.headline}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    while (deduped.length < 3) {
      deduped.push(quietNarrative(['positive', 'context', 'action'][deduped.length] || 'context'));
    }
    return deduped.slice(0, 3);
  }

  function storyEvidenceHtml(evidence) {
    return evidence?.length
      ? evidence.slice(0, 4).map((item) => `
        <div class="story-evidence-item">
          <span class="story-evidence-label">${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
          <span>${escapeHtml(item.meta || '')}</span>
        </div>`).join('')
      : '<p class="empty-msg">Collect a few more runs to build a stronger story baseline.</p>';
  }

  function storySlideHtml(card, idx, activeIndex) {
    const active = idx === activeIndex;
    const tone = card.tone || 'context';
    return `
      <article class="story-slide ${escapeHtml(tone)}${active ? ' is-active' : ''}"${active ? '' : ' aria-hidden="true"'}>
        <span class="story-slide-tone">${escapeHtml(card.tab || 'Story')}</span>
        <h2${active ? ' id="storyHeadline"' : ''}>${escapeHtml(card.headline)}</h2>
        <p class="story-summary"${active ? ' id="storySummary"' : ''}>${escapeHtml(card.summary)}</p>
        <div class="story-evidence-grid"${active ? ' id="storyEvidence"' : ''}>${storyEvidenceHtml(card.evidence || [])}</div>
      </article>`;
  }

  function renderStoryLead() {
    const cards = buildStoryCards();
    const carousel = document.getElementById('storyCarousel');
    const controls = document.getElementById('storyControls');
    if (!carousel) return;
    const activeIndex = Math.min(Math.max(Number(state.storyIndex || 0), 0), Math.max(0, cards.length - 1));
    state.storyIndex = activeIndex;
    carousel.innerHTML = cards.map((card, idx) => storySlideHtml(card, idx, activeIndex)).join('');
    if (!controls) return;
    controls.innerHTML = cards.map((card, idx) => `
      <button class="story-tab${idx === activeIndex ? ' is-active' : ''}" type="button" data-story-index="${idx}" aria-pressed="${idx === activeIndex ? 'true' : 'false'}">
        ${escapeHtml(card.tab || 'Story')}
      </button>`).join('');
    controls.querySelectorAll('[data-story-index]').forEach((button) => {
      button.addEventListener('click', () => {
        state.storyIndex = Number(button.dataset.storyIndex || 0);
        renderStoryLead();
      });
    });
  }

  function buildActions() {
    const actions = [];
    const insight = topInsight();
    const follow = followThroughStory();
    if (follow) {
      actions.push({
        tag: 'Follow-up',
        title: 'Check what kept the movement going',
        body: `${follow.headline}. Compare paths, referrers, and nearby repo events while the trail is still fresh.`,
      });
    }
    if (insight?.kind === 'growth' && ['high_attention_low_interest', 'traffic_without_downstream_growth'].includes(insight.subtype)) {
      actions.push({
        tag: 'Conversion',
        title: 'Tighten the path from visitor to user',
        body: `${getShortName(insight.repo)} is getting attention without matching downstream growth. Make the README, examples, and release notes answer "why adopt this now?" quickly.`,
      });
    }
    if (insight?.subtype === 'clone_heavy_star_light') {
      actions.push({
        tag: 'Adoption',
        title: 'Explain what cloners should do next',
        body: `${getShortName(insight.repo)} is being cloned more than it is being starred. Add quickstart, verification, and follow-up links near install instructions.`,
      });
    }

    readinessRows()
      .filter((row) => row.missing.length)
      .sort((a, b) => (a.health ?? 101) - (b.health ?? 101) || b.repo.activity - a.repo.activity)
      .slice(0, 3)
      .forEach((row) => {
        const missing = row.missing[0];
        actions.push({
          tag: 'Readiness',
          title: `${missing.label}: ${getShortName(row.repo.name)}`,
          body: missing.action,
        });
      });

    const releases = asArray(contextPayload().releases);
    if (releases.length) {
      const release = releases[0];
      actions.push({
        tag: 'Release',
        title: 'Watch release impact in the next window',
        body: `${release.tag_name || release.name || 'The latest release'} gives future traffic, clone, path, and referrer changes a concrete timestamp to compare against.`,
      });
    }

    if (!actions.length) {
      actions.push({
        tag: 'Baseline',
        title: 'Keep collecting until the next move',
        body: 'Nothing needs a fire drill. Keep collecting so the next release, docs push, or refactor has a clean before and after.',
      });
    }
    return actions.slice(0, 4);
  }

  function renderActions() {
    const container = document.getElementById('next-actions');
    if (!container) return;
    container.innerHTML = '<div class="action-stack">' + buildActions().map((action) => `
      <div class="action-item">
        <span class="action-tag">${escapeHtml(action.tag)}</span>
        <strong>${escapeHtml(action.title)}</strong>
        <span>${escapeHtml(action.body)}</span>
      </div>`).join('') + '</div>';
  }

  function renderContextTimeline() {
    const container = document.getElementById('context-timeline');
    if (!container) return;
    const events = scopedEvents().slice(0, 8);
    if (!events.length) {
      container.innerHTML = '<p class="empty-msg">No commit or release trail for this scope yet. Once collected, this lane will show what shipped around the traffic.</p>';
      return;
    }
    container.innerHTML = '<div class="event-timeline">' + events.map((event) => {
      const title = event.title || event.event_id;
      const label = eventLabel(event);
      const linked = event.url
        ? `<a href="${escapeAttr(event.url)}" rel="noreferrer">${escapeHtml(title)}</a>`
        : escapeHtml(title);
      return `
        <div class="event-row">
          <div class="event-date mono">${escapeHtml(dateLabel(event.event_date))}</div>
          <div class="event-marker ${escapeHtml(event.event_type || 'event')}"></div>
          <div class="event-main">
            <div class="event-title">${linked}</div>
            <div class="event-meta">${escapeHtml(label)} &middot; ${escapeHtml(getShortName(event.repo))}${event.magnitude ? ' &middot; magnitude ' + escapeHtml(formatNumber(event.magnitude)) : ''}</div>
          </div>
        </div>`;
    }).join('') + '</div>';
  }

  function renderReadinessPanel() {
    const container = document.getElementById('readiness-panel');
    if (!container) return;
    const rows = readinessRows();
    if (!rows.length) {
      container.innerHTML = '<p class="empty-msg">No community health data yet.</p>';
      return;
    }
    const knownRows = rows.filter((row) => row.knownCount > 0);
    const present = knownRows.reduce((total, row) => total + row.presentCount, 0);
    const known = knownRows.reduce((total, row) => total + row.knownCount, 0);
    const avgHealthValues = rows.map((row) => row.health).filter((value) => value !== null);
    const avgHealth = avgHealthValues.length
      ? Math.round(avgHealthValues.reduce((total, value) => total + value, 0) / avgHealthValues.length)
      : null;
    const categoryRows = READINESS_SIGNALS.map((signal) => {
      const knownForSignal = rows.filter((row) => asBool(row.repo.community?.[signal.key]) !== null);
      const presentForSignal = knownForSignal.filter((row) => asBool(row.repo.community?.[signal.key]) === true);
      const pct = knownForSignal.length ? (presentForSignal.length / knownForSignal.length) * 100 : 0;
      return { label: signal.label, present: presentForSignal.length, known: knownForSignal.length, pct };
    });

    container.innerHTML = `
      <div class="readiness-score">
        <span class="readiness-score-value">${avgHealth === null ? '-' : formatNumber(avgHealth) + '%'}</span>
        <span class="readiness-score-meta">${formatNumber(present)} of ${formatNumber(known)} known public-readiness files present</span>
      </div>
      <div class="readiness-bars">
        ${categoryRows.map((row) => `
          <div class="readiness-row">
            <span>${escapeHtml(row.label)}</span>
            <div class="readiness-track" aria-hidden="true"><span data-pct="${Math.max(0, Math.min(100, row.pct)).toFixed(1)}"></span></div>
            <span class="mono">${formatNumber(row.present)}/${formatNumber(row.known)}</span>
          </div>`).join('')}
      </div>`;
    container.querySelectorAll('.readiness-track span').forEach((bar) => {
      bar.style.width = (bar.dataset.pct || '0') + '%';
    });
  }

  function renderPositioningPanel() {
    const container = document.getElementById('positioning-panel');
    if (!container) return;
    const ctx = contextPayload();
    const languages = asArray(ctx.languages?.top);
    const topics = asArray(ctx.topics?.top);
    const referrers = getCurrentReferrerRows();
    const paths = getCurrentPathRows();
    const totalLanguageShare = Math.max(...languages.map((row) => Number(row.share || 0)), 0) || 1;
    const topReferrer = referrers[0];
    const topPath = paths[0];

    const languageHtml = languages.length
      ? languages.slice(0, 5).map((row) => {
          const pct = Math.max(2, (Number(row.share || 0) / totalLanguageShare) * 100);
          return `<div class="position-row"><span>${escapeHtml(row.language)}</span><div class="position-track" aria-hidden="true"><span data-pct="${pct.toFixed(1)}"></span></div><span class="mono">${Math.round(Number(row.share || 0) * 100)}%</span></div>`;
        }).join('')
      : '<p class="empty-msg compact-empty">No language snapshot yet.</p>';

    const topicHtml = topics.length
      ? topics.slice(0, 10).map((row) => `<span class="topic-chip">${escapeHtml(row.topic)}<span>${formatNumber(row.repo_count)}</span></span>`).join('')
      : '<p class="empty-msg compact-empty">No topic snapshot yet.</p>';

    container.innerHTML = `
      <div class="position-block">
        <div class="position-label">Language mix</div>
        ${languageHtml}
      </div>
      <div class="position-block">
        <div class="position-label">Topics</div>
        <div class="topic-cloud">${topicHtml}</div>
      </div>
      <div class="position-sources">
        <div><span>Top referrer</span><strong>${escapeHtml(topReferrer?.referrer || 'No referrer yet')}</strong></div>
        <div><span>Top content</span><strong>${escapeHtml(topPath?.content || topPath?.title || topPath?.path || 'No path yet')}</strong></div>
      </div>`;
    container.querySelectorAll('.position-track span').forEach((bar) => {
      bar.style.width = (bar.dataset.pct || '0') + '%';
    });
  }

  function weekStartForIso(iso) {
    const date = parseIsoDate(iso);
    if (!date) return '';
    const weekday = (date.getUTCDay() + 6) % 7;
    date.setUTCDate(date.getUTCDate() - weekday);
    return formatIsoDate(date);
  }

  function weeklyTraffic() {
    const aggregate = buildAggregateSeries(getVisibleRepos());
    const byWeek = new Map();
    (aggregate.dates || []).forEach((date, idx) => {
      const week = weekStartForIso(date);
      if (!week) return;
      byWeek.set(week, (byWeek.get(week) || 0) + Number((aggregate.views || [])[idx] || 0));
    });
    return byWeek;
  }

  function ensureContextChart() {
    if (context.charts.contextChart) return;
    const canvas = document.getElementById('contextChart');
    if (!canvas) return;
    context.charts.contextChart = context.chartAdapter.createChart(canvas, {
      type: 'bar',
      data: { labels: [], datasets: [] },
      options: contextChartOptions(),
    });
  }

  function contextChartOptions() {
    const tick = getThemeColor('--text-muted', '#8b949e');
    const grid = getThemeColor('--chart-grid', 'rgba(48, 54, 61, 0.4)');
    const axis = getThemeColor('--chart-axis', 'rgba(48, 54, 61, 0.7)');
    const tipBg = getThemeColor('--chart-tooltip-bg', 'rgba(22, 27, 34, 0.96)');
    const tipBorder = getThemeColor('--chart-tooltip-border', '#30363d');
    const text = getThemeColor('--text', '#e6edf3');
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 320 },
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: { color: tick, boxWidth: 10, boxHeight: 10, usePointStyle: true, padding: 14 },
        },
        tooltip: {
          backgroundColor: tipBg,
          borderColor: tipBorder,
          borderWidth: 1,
          titleColor: text,
          bodyColor: text,
          padding: 10,
          boxPadding: 4,
        },
      },
      scales: {
        x: {
          ticks: { color: tick, maxRotation: 0, autoSkipPadding: 16 },
          grid: { color: grid, drawTicks: false },
          border: { color: axis },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: 'Code churn', color: tick },
          ticks: { color: tick, callback: (value) => compactNumber(value) },
          grid: { color: grid, drawTicks: false },
          border: { display: false },
        },
        y1: {
          beginAtZero: true,
          position: 'right',
          title: { display: true, text: 'Views', color: tick },
          ticks: { color: tick, callback: (value) => compactNumber(value) },
          grid: { drawOnChartArea: false },
          border: { display: false },
        },
      },
    };
  }

  function updateContextMetrics(codeWeeks, contributorWeeks, issueTotals, releases) {
    const container = document.getElementById('context-metrics');
    if (!container) return;
    const churn = codeWeeks.reduce((total, row) => total + Number(row.additions || 0) + Number(row.deletions || 0), 0);
    const commits = contributorWeeks.reduce((total, row) => total + Number(row.commits || 0), 0);
    const releaseDownloads = releases.reduce((total, row) => total + Number(row.asset_download_count || 0), 0);
    container.innerHTML = [
      { label: 'Code churn', value: formatNumber(churn), meta: 'adds + deletes' },
      { label: 'Commits', value: formatNumber(commits), meta: 'weekly contributor stats' },
      { label: 'Open issues', value: formatNumber(issueTotals.open_issues || 0), meta: 'latest sampled load' },
      { label: 'Release downloads', value: formatNumber(releaseDownloads), meta: 'recent releases' },
    ].map((item) => `
      <div class="context-metric">
        <span>${escapeHtml(item.label)}</span>
        <strong class="mono">${escapeHtml(item.value)}</strong>
        <small>${escapeHtml(item.meta)}</small>
      </div>`).join('');
  }

  function updateContextChart() {
    const ctx = contextPayload();
    const codeWeeks = asArray(ctx.code_frequency?.weeks);
    const contributorWeeks = asArray(ctx.contributors?.weeks);
    const issueTotals = ctx.issues?.totals || {};
    const releases = asArray(ctx.releases);
    updateContextMetrics(codeWeeks, contributorWeeks, issueTotals, releases);

    const empty = document.getElementById('contextChartEmpty');
    const trafficByWeek = weeklyTraffic();
    const labels = [...new Set([
      ...codeWeeks.map((row) => row.week_start),
      ...trafficByWeek.keys(),
    ].filter(Boolean))].sort().slice(-16);
    const hasCode = codeWeeks.length > 0;
    if (!labels.length || !hasCode) {
      if (empty) empty.style.display = 'grid';
      if (context.charts.contextChart) {
        context.charts.contextChart.data.labels = [];
        context.charts.contextChart.data.datasets = [];
        context.charts.contextChart.update();
      }
      return;
    }
    if (empty) empty.style.display = 'none';
    ensureContextChart();
    if (!context.charts.contextChart) return;

    const codeByWeek = new Map(codeWeeks.map((row) => [row.week_start, row]));
    const labelText = labels.map(dateLabel);
    const churn = labels.map((week) => {
      const row = codeByWeek.get(week) || {};
      return Number(row.additions || 0) + Number(row.deletions || 0);
    });
    const views = labels.map((week) => trafficByWeek.get(week) || 0);

    context.charts.contextChart.options = contextChartOptions();
    context.charts.contextChart.data.labels = labelText;
    context.charts.contextChart.data.datasets = [
      {
        type: 'bar',
        label: 'Code churn',
        data: churn,
        yAxisID: 'y',
        backgroundColor: hexAlpha(getThemeColor('--accent-2', '#bf6a02'), 0.55),
        borderColor: getThemeColor('--accent-2', '#bf6a02'),
        borderWidth: 1,
        borderRadius: 6,
        maxBarThickness: 26,
      },
      {
        type: 'line',
        label: 'Views',
        data: views,
        yAxisID: 'y1',
        borderColor: getThemeColor('--c-views', '#58a6ff'),
        backgroundColor: hexAlpha(getThemeColor('--c-views', '#58a6ff'), 0.12),
        borderWidth: 2.2,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.32,
        fill: false,
      },
    ];
    context.charts.contextChart.update();
  }

  function renderStory() {
    renderStoryLead();
    renderActions();
    renderContextTimeline();
    renderReadinessPanel();
    renderPositioningPanel();
    updateContextChart();
  }

  return {
    contextPayload,
    scopeRepoNames,
    latestTrafficDate,
    daysBetweenIso,
    dateLabel,
    eventLabel,
    titleCase,
    escapeAttr,
    scopedEvents,
    nearbyEvent,
    visibleInsights,
    topInsight,
    readinessRows,
    asBool,
    finiteNumber,
    median,
    sumMetricValues,
    formatMetricValue,
    insightScore,
    isPositiveInsight,
    isActionInsight,
    findSeriesAnomalies,
    anomalyEvidence,
    anomalyStory,
    followThroughStory,
    latestEventStory,
    describeInsight,
    quietNarrative,
    buildPositiveStory,
    buildContextStory,
    buildActionStory,
    buildStoryCards,
    storyEvidenceHtml,
    storySlideHtml,
    renderStoryLead,
    buildActions,
    renderActions,
    renderContextTimeline,
    renderReadinessPanel,
    renderPositioningPanel,
    weekStartForIso,
    weeklyTraffic,
    ensureContextChart,
    contextChartOptions,
    updateContextMetrics,
    updateContextChart,
    renderStory,
  };
}

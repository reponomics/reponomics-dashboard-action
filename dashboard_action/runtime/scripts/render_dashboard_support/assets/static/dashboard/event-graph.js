export function installEventGraph(context) {
  const document = context.document;
  const activateRepo = (...args) => context.activateRepo(...args);
  const currentPayload = (...args) => context.currentPayload(...args);
  const escapeHtml = (...args) => context.escapeHtml(...args);
  const formatNumber = (...args) => context.formatNumber(...args);
  const getRepoColor = (...args) => context.getRepoColor(...args);
  const getSelectedWindow = (...args) => context.getSelectedWindow(...args);
  const getShortName = (...args) => context.getShortName(...args);
  const getVisibleRepos = (...args) => context.getVisibleRepos(...args);
  const getWindowCutoffDate = (...args) => context.getWindowCutoffDate(...args);
  const parseIsoDate = (...args) => context.parseIsoDate(...args);

    function allEventDates(eventGraph) {
      return (eventGraph?.repos || [])
        .flatMap((repo) => repo.events || [])
        .map((event) => String(event.date || '').slice(0, 10))
        .filter(Boolean)
        .sort();
    }

    function eventWindowBounds(eventGraph) {
      const payload = currentPayload() || {};
      const dates = payload.daily?.dates || [];
      const eventDates = allEventDates(eventGraph);
      const startFallback = dates[0] || eventDates[0] || '';
      const endFallback = dates[dates.length - 1] || eventDates[eventDates.length - 1] || startFallback;
      const start = getSelectedWindow() === 'all'
        ? startFallback
        : (getWindowCutoffDate() || startFallback);
      return { start, end: endFallback };
    }

    function daysBetween(start, end) {
      const startDate = parseIsoDate(start);
      const endDate = parseIsoDate(end);
      if (!startDate || !endDate) return 0;
      return Math.round((endDate.getTime() - startDate.getTime()) / 86400000);
    }

    function projectEventX(date, bounds) {
      const span = Math.max(1, daysBetween(bounds.start, bounds.end));
      const offset = Math.max(0, Math.min(span, daysBetween(bounds.start, date)));
      return 22 + (offset / span) * 73;
    }

    function cleanClass(value) {
      return String(value || 'unknown').toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
    }

    function buildEventLanes(eventGraph, visibleRepos, bounds) {
      const visibleNames = new Set((visibleRepos || []).map((repo) => repo.name));
      const visibleOrder = new Map((visibleRepos || []).map((repo, idx) => [repo.name, idx]));
      return (eventGraph?.repos || [])
        .filter((repo) => visibleNames.has(repo.repo))
        .map((repo) => {
          const color = getRepoColor(repo.repo);
          const events = (repo.events || [])
            .filter((event) => {
              const date = String(event.date || '').slice(0, 10);
              if (!date) return false;
              if (bounds.start && date < bounds.start) return false;
              if (bounds.end && date > bounds.end) return false;
              return true;
            })
            .map((event) => ({
              ...event,
              repo: repo.repo,
              shortName: getShortName(repo.repo),
              color,
              x: projectEventX(event.date, bounds),
              typeClass: cleanClass(event.type),
              classificationClass: cleanClass(event.classification)
            }));
          return {
            repo: repo.repo,
            shortName: getShortName(repo.repo),
            color,
            events,
            order: visibleOrder.get(repo.repo) ?? 999
          };
        })
        .filter((repo) => repo.events.length)
        .sort((a, b) => a.order - b.order);
    }

    function formatEventType(event) {
      if (event.type === 'release') return 'release';
      if (event.type === 'commit') return event.classification && event.classification !== 'unknown'
        ? event.classification
        : 'commit';
      return event.type || 'event';
    }

    function plural(count, singular, pluralLabel) {
      return `${formatNumber(count)} ${count === 1 ? singular : (pluralLabel || singular + 's')}`;
    }

    function buildEventClusters(lanes) {
      const groups = new Map();
      lanes.flatMap((lane) => lane.events).forEach((event) => {
        const date = String(event.date || '').slice(0, 10);
        if (!date) return;
        const group = groups.get(date) || { date, x: event.x, events: [], repos: new Set(), classifications: new Map(), releaseCount: 0, commitCount: 0 };
        group.events.push(event);
        group.repos.add(event.repo);
        group.x = Math.min(group.x, event.x);
        if (event.type === 'release') group.releaseCount += 1;
        if (event.type === 'commit') group.commitCount += 1;
        const classification = formatEventType(event);
        group.classifications.set(classification, (group.classifications.get(classification) || 0) + 1);
        groups.set(date, group);
      });
      return [...groups.values()]
        .map((group) => {
          const repos = [...group.repos];
          const topClassifications = [...group.classifications.entries()]
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
            .slice(0, 2)
            .map(([name, count]) => count > 1 ? `${name} x${count}` : name);
          return {
            ...group,
            repos,
            repo: repos.length === 1 ? repos[0] : '',
            repoCount: repos.length,
            label: [
              plural(group.commitCount, 'commit'),
              group.releaseCount ? plural(group.releaseCount, 'release') : '',
              repos.length > 1 ? plural(repos.length, 'repo') : (repos[0] ? getShortName(repos[0]) : ''),
            ].filter(Boolean).join(' · '),
            classificationLabel: topClassifications.join(', '),
          };
        })
        .sort((a, b) => String(a.date).localeCompare(String(b.date)));
    }

    function renderEventCluster(cluster) {
      const count = cluster.events.length;
      const x = cluster.x;
      const baseY = 31;
      const height = Math.min(20, 4 + Math.log2(count + 1) * 5 + (cluster.releaseCount ? 2 : 0));
      const topY = baseY - height;
      const radius = Math.min(4.6, 2.2 + Math.sqrt(count) * 0.42);
      const repoAttr = cluster.repo ? ` data-repo="${escapeHtml(cluster.repo)}"` : '';
      const roleAttr = cluster.repo ? ' role="button"' : '';
      const tabAttr = cluster.repo ? ' tabindex="0"' : '';
      const title = `${cluster.date} · ${cluster.label}${cluster.classificationLabel ? ' · ' + cluster.classificationLabel : ''}`;
      const releaseDiamond = cluster.releaseCount
        ? `<polygon class="event-cluster-release" points="${[
            [x, topY - 4.4],
            [x + 4.4, topY],
            [x, topY + 4.4],
            [x - 4.4, topY],
          ].map((point) => point.map((value) => value.toFixed(2)).join(',')).join(' ')}"></polygon>`
        : '';
      return `
        <g class="event-cluster${cluster.releaseCount ? ' has-release' : ''}"${repoAttr}${roleAttr}${tabAttr} aria-label="${escapeHtml(title)}">
          <line class="event-cluster-stem" x1="${x.toFixed(2)}" y1="${baseY.toFixed(2)}" x2="${x.toFixed(2)}" y2="${topY.toFixed(2)}"></line>
          <circle class="event-cluster-dot" cx="${x.toFixed(2)}" cy="${topY.toFixed(2)}" r="${radius.toFixed(2)}"></circle>
          ${releaseDiamond}
          <title>${escapeHtml(title)}</title>
        </g>`;
    }

    function renderEventLog(lanes) {
      const log = document.getElementById('event-log');
      if (!log) return;
      const events = lanes
        .flatMap((lane) => lane.events)
        .sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')))
        .slice(0, 6);
      if (!events.length) {
        log.innerHTML = '<p class="empty-msg">No retained commits or releases in this selected window.</p>';
        return;
      }
      log.innerHTML = events.map((event) => {
        const traffic = event.traffic || {};
        const nearbyViews = Number(traffic.nearby_views || 0);
        return `
          <button class="event-log-item" type="button" data-repo="${escapeHtml(event.repo)}">
            <span class="event-log-kind type-${escapeHtml(event.typeClass)}">${escapeHtml(formatEventType(event))}</span>
            <span class="event-log-title">${escapeHtml(event.title || formatEventType(event))}</span>
            <span class="event-log-meta">${escapeHtml(event.shortName)} · ${escapeHtml(event.date)} · ${formatNumber(nearbyViews)} nearby views</span>
          </button>`;
      }).join('');
      log.querySelectorAll('.event-log-item').forEach((button) => {
        button.style.setProperty('--event-color', getRepoColor(button.dataset.repo));
        button.addEventListener('click', function(event) {
          activateRepo(button.dataset.repo, !!(event && (event.metaKey || event.ctrlKey || event.shiftKey)));
        });
      });
    }

    function renderEventGraph() {
      const payload = currentPayload();
      const eventGraph = payload?.event_graph || {};
      const card = document.getElementById('event-graph-card');
      const graph = document.getElementById('event-graph');
      if (!card || !graph) return;
      const section = card.closest ? card.closest('.event-graph-section') : null;
      const visibleRepos = getVisibleRepos();
      const visibleNames = new Set(visibleRepos.map((repo) => repo.name));
      const hasVisibleEventData = (eventGraph.repos || []).some((repo) => visibleNames.has(repo.repo));
      if (!hasVisibleEventData) {
        if (section) section.style.display = 'none';
        card.style.display = 'none';
        return;
      }
      if (section) section.style.display = 'grid';
      card.style.display = 'block';
      const bounds = eventWindowBounds(eventGraph);
      const lanes = buildEventLanes(eventGraph, visibleRepos, bounds);
      if (!lanes.length) {
        graph.innerHTML = '<p class="empty-msg event-graph-empty">No retained code events in this selected window.</p>';
        renderEventLog([]);
        return;
      }
      const clusters = buildEventClusters(lanes);
      const clusterMarkup = clusters.map((cluster) => renderEventCluster(cluster)).join('');
      graph.innerHTML = `
        <svg viewBox="0 0 100 42" preserveAspectRatio="xMidYMid meet" role="list" aria-label="Code events from ${escapeHtml(bounds.start)} to ${escapeHtml(bounds.end)}">
          <line class="event-ribbon-axis" x1="22" y1="31" x2="96" y2="31"></line>
          <text class="git-axis git-axis-start" x="22" y="39">${escapeHtml(bounds.start || 'start')}</text>
          <text class="git-axis git-axis-end" x="96" y="39">${escapeHtml(bounds.end || 'latest')}</text>
          <text class="event-ribbon-label" x="2.5" y="9">code activity</text>
          ${clusterMarkup}
        </svg>`;
      graph.querySelectorAll('.event-cluster[data-repo]').forEach((node) => {
        node.style.setProperty('--event-color', getRepoColor(node.dataset.repo));
      });
      graph.querySelectorAll('.event-cluster[data-repo]').forEach((node) => {
        node.addEventListener('click', function(event) {
          activateRepo(node.dataset.repo, !!(event && (event.metaKey || event.ctrlKey || event.shiftKey)));
        });
        node.addEventListener('keydown', function(event) {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            activateRepo(node.dataset.repo, !!(event.metaKey || event.ctrlKey || event.shiftKey));
          }
        });
      });
      renderEventLog(lanes);
    }

  return { allEventDates, eventWindowBounds, daysBetween, projectEventX, buildEventLanes, buildEventClusters, renderEventGraph };
}

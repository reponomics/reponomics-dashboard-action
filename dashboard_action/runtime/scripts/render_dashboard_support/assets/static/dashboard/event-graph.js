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

    function renderEventMarker(event, y) {
      const traffic = event.traffic || {};
      const nearbyViews = Number(traffic.nearby_views || 0);
      const label = `${event.shortName}: ${formatEventType(event)} on ${event.date}`;
      if (event.type === 'release') {
        const points = [
          [event.x, y - 3.2],
          [event.x + 3.2, y],
          [event.x, y + 3.2],
          [event.x - 3.2, y]
        ].map((point) => point.map((value) => value.toFixed(2)).join(',')).join(' ');
        return `
          <g class="git-event-node type-${event.typeClass} class-${event.classificationClass}" data-repo="${escapeHtml(event.repo)}" tabindex="0" role="button" aria-label="${escapeHtml(label)}">
            <polygon class="git-event-tag" points="${points}"></polygon>
            <text class="git-event-kicker" x="${event.x.toFixed(2)}" y="${(y - 5.2).toFixed(2)}">tag</text>
            <title>${escapeHtml(event.title)} · ${event.date} · ${formatNumber(nearbyViews)} nearby views</title>
          </g>`;
      }
      return `
        <g class="git-event-node type-${event.typeClass} class-${event.classificationClass}" data-repo="${escapeHtml(event.repo)}" tabindex="0" role="button" aria-label="${escapeHtml(label)}">
          <circle class="git-event-dot" cx="${event.x.toFixed(2)}" cy="${y.toFixed(2)}" r="2.45"></circle>
          <title>${escapeHtml(event.title)} · ${event.date} · ${formatNumber(nearbyViews)} nearby views</title>
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
      const laneGap = 12;
      const top = 12;
      const height = top + laneGap * Math.max(1, lanes.length) + 12;
      const laneMarkup = lanes.map((lane, idx) => {
        const y = top + idx * laneGap;
        const branch = idx > 0
          ? `<path class="git-branch-link" d="M22 ${(y - laneGap).toFixed(2)} C28 ${(y - laneGap).toFixed(2)} 29 ${y.toFixed(2)} 36 ${y.toFixed(2)}"></path>`
          : '';
        const markers = lane.events.map((event) => renderEventMarker(event, y)).join('');
        return `
          <g class="git-lane" data-repo="${escapeHtml(lane.repo)}">
            <text class="git-lane-label" x="2.5" y="${(y + 1.1).toFixed(2)}">${escapeHtml(lane.shortName)}</text>
            <line class="git-rail" x1="21" y1="${y.toFixed(2)}" x2="96" y2="${y.toFixed(2)}"></line>
            ${branch}
            ${markers}
          </g>`;
      }).join('');
      graph.innerHTML = `
        <svg viewBox="0 0 100 ${height}" preserveAspectRatio="xMidYMid meet" role="list" aria-label="Code events from ${escapeHtml(bounds.start)} to ${escapeHtml(bounds.end)}">
          <text class="git-axis git-axis-start" x="21" y="${(height - 2.5).toFixed(2)}">${escapeHtml(bounds.start || 'start')}</text>
          <text class="git-axis git-axis-end" x="96" y="${(height - 2.5).toFixed(2)}">${escapeHtml(bounds.end || 'latest')}</text>
          ${laneMarkup}
        </svg>`;
      graph.querySelectorAll('.git-lane, .git-event-node').forEach((node) => {
        node.style.setProperty('--event-color', getRepoColor(node.dataset.repo));
      });
      graph.querySelectorAll('.git-event-node').forEach((node) => {
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

  return { allEventDates, eventWindowBounds, daysBetween, projectEventX, buildEventLanes, renderEventGraph };
}

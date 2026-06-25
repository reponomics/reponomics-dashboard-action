export function installNarrativeInsights(context) {
  const document = context.document;
  const window = context.window;
  const currentPayload = (...args) => context.currentPayload(...args);
  const escapeHtml = (...args) => context.escapeHtml(...args);
  const getShortName = (...args) => context.getShortName(...args);
  const isComparing = (...args) => context.isComparing(...args);
  const selectRepo = (...args) => context.selectRepo(...args);
  const state = context.state;

    function narrativeScope(items) {
      if (isComparing()) {
        const compare = new Set(state.compareRepos);
        const scoped = items.filter((item) => !item.repo || compare.has(item.repo));
        return scoped.length ? scoped : items;
      }
      if (state.selectedRepo) {
        const scoped = items.filter((item) => !item.repo || item.repo === state.selectedRepo);
        return scoped.length ? scoped : items;
      }
      return items;
    }

    function narrativeToneClass(tone) {
      if (tone === 'positive') return 'positive';
      if (tone === 'warning') return 'warning';
      if (tone === 'attention') return 'attention';
      return 'neutral';
    }

    function recipeLabel(recipe) {
      return String(recipe || 'narrative')
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
    }

    function safeEventUrl(url) {
      const value = String(url || '');
      if (!value) return '';
      if (value.startsWith('https://github.com/')) return value;
      if (value.startsWith('#') || value.startsWith('/')) return value;
      return '';
    }

    function renderEvidence(evidence) {
      const items = Array.isArray(evidence) ? evidence : [];
      if (!items.length) return '';
      return '<div class="narrative-evidence">' + items.slice(0, 4).map((item) => {
        const detail = item.detail ? `<span class="narrative-evidence-detail">${escapeHtml(item.detail)}</span>` : '';
        return `<span class="narrative-evidence-chip">` +
          `<span class="narrative-evidence-label">${escapeHtml(item.label || '')}</span>` +
          `<strong>${escapeHtml(item.value || '')}</strong>` +
          detail +
          `</span>`;
      }).join('') + '</div>';
    }

    function renderEvents(events) {
      const items = Array.isArray(events) ? events : [];
      if (!items.length) return '';
      return '<div class="narrative-events">' + items.slice(0, 2).map((event) => {
        const href = safeEventUrl(event.url);
        const title = escapeHtml(event.title || 'Repository event');
        const linkedTitle = href
          ? `<a class="narrative-event-link" href="${escapeHtml(href)}">${title}</a>`
          : `<span>${title}</span>`;
        const meta = [
          event.date || '',
          event.classification || event.type || ''
        ].filter(Boolean).join(' · ');
        return `<div class="narrative-event">` +
          `<span class="narrative-event-dot" aria-hidden="true"></span>` +
          `<span class="narrative-event-copy">${linkedTitle}` +
          (meta ? `<span class="narrative-event-meta">${escapeHtml(meta)}</span>` : '') +
          `</span></div>`;
      }).join('') + '</div>';
    }

    function renderNarrativeItem(item) {
      const repo = item.repo || '';
      const repoTag = repo
        ? `<span class="narrative-repo">${escapeHtml(getShortName(repo))}</span>`
        : '';
      const action = item.action
        ? `<div class="narrative-action">${escapeHtml(item.action)}</div>`
        : '';
      const anchor = item.anchor_date
        ? `<span class="narrative-anchor mono">${escapeHtml(item.anchor_date)}</span>`
        : '';
      return `
        <article class="narrative-item ${narrativeToneClass(item.tone)}" ${repo ? `data-repo="${escapeHtml(repo)}" tabindex="0" role="button" aria-label="Focus on ${escapeHtml(getShortName(repo))}"` : ''}>
          <div class="narrative-marker" aria-hidden="true"></div>
          <div class="narrative-body">
            <div class="narrative-kicker">
              ${repoTag}
              <span>${escapeHtml(recipeLabel(item.recipe))}</span>
              ${anchor}
            </div>
            <h3>${escapeHtml(item.title || 'Repository story')}</h3>
            <p>${escapeHtml(item.summary || '')}</p>
            ${renderEvidence(item.evidence)}
            ${renderEvents(item.events)}
            ${action}
          </div>
        </article>`;
    }

    function bindNarrativeInteractions(panel) {
      panel.querySelectorAll('.narrative-item[data-repo]').forEach((item) => {
        const focus = function(event) {
          if (event && event.target && event.target.closest('a')) return;
          selectRepo(item.dataset.repo);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        };
        item.addEventListener('click', focus);
        item.addEventListener('keydown', function(event) {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            focus(event);
          }
        });
      });
    }

    function renderNarrativeInsights() {
      const section = document.getElementById('narrative-insights-section');
      const panel = document.getElementById('narrative-insights-panel');
      if (!section || !panel) return;

      const payload = currentPayload() || {};
      const narratives = Array.isArray(payload.narratives) ? payload.narratives : [];
      section.style.display = 'block';

      if (!narratives.length) {
        panel.innerHTML = '<p class="empty-msg">Needs more contextual collection before repository stories can be ranked.</p>';
        return;
      }

      const scoped = narrativeScope(narratives).slice(0, 6);
      panel.innerHTML = '<div class="narrative-list">' + scoped.map(renderNarrativeItem).join('') + '</div>';
      bindNarrativeInteractions(panel);
    }

  return { narrativeScope, narrativeToneClass, recipeLabel, safeEventUrl, renderEvidence, renderEvents, renderNarrativeItem, bindNarrativeInteractions, renderNarrativeInsights };
}

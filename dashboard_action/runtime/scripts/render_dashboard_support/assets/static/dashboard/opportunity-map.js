export function installOpportunityMap(context) {
  const document = context.document;
  const activateRepo = (...args) => context.activateRepo(...args);
  const escapeHtml = (...args) => context.escapeHtml(...args);
  const formatNumber = (...args) => context.formatNumber(...args);
  const formatSigned = (...args) => context.formatSigned(...args);
  const getRepoColor = (...args) => context.getRepoColor(...args);
  const getShortName = (...args) => context.getShortName(...args);
  const getVisibleRepos = (...args) => context.getVisibleRepos(...args);

    function downstreamDelta(repo) {
      return Number(repo.stars_delta || 0) + Number(repo.subscribers_delta || 0) + Number(repo.forks_delta || 0);
    }

    function attentionValue(repo) {
      return Number(repo.views || 0) + Number(repo.uniques || 0);
    }

    function adoptionValue(repo) {
      return Number(repo.clones || 0) + Number(repo.clone_uniques || 0);
    }

    function buildOpportunityPoints(repos) {
      const scoped = (repos || []).filter((repo) => repo && repo.name);
      const maxAttention = Math.max(...scoped.map(attentionValue), 1);
      const maxDownstream = Math.max(...scoped.map((repo) => Math.max(0, downstreamDelta(repo))), 1);
      const maxAdoption = Math.max(...scoped.map(adoptionValue), 1);
      return scoped.map((repo) => {
        const attention = attentionValue(repo);
        const downstream = downstreamDelta(repo);
        const adoption = adoptionValue(repo);
        const attentionScore = Math.log1p(attention) / Math.log1p(maxAttention);
        const growthScore = downstream <= 0 ? 0 : Math.log1p(downstream) / Math.log1p(maxDownstream);
        const adoptionScore = Math.log1p(adoption) / Math.log1p(maxAdoption);
        return {
          repo: repo.name,
          shortName: getShortName(repo.name),
          attention,
          visitors: Number(repo.uniques || 0),
          downstream,
          adoption,
          attentionScore: Math.max(0, Math.min(1, attentionScore || 0)),
          growthScore: Math.max(0, Math.min(1, growthScore || 0)),
          adoptionScore: Math.max(0, Math.min(1, adoptionScore || 0))
        };
      });
    }

    function classifyOpportunityPoint(point) {
      if (point.attentionScore >= 0.58 && point.growthScore < 0.28) return 'clarify next step';
      if (point.attentionScore >= 0.58 && point.growthScore >= 0.28) return 'amplify';
      if (point.attentionScore < 0.58 && point.growthScore >= 0.28) return 'protect niche pull';
      return 'seed discovery';
    }

    function mapPoint(point) {
      const left = 13;
      const right = 95;
      const top = 8;
      const bottom = 52;
      return {
        x: left + point.attentionScore * (right - left),
        y: bottom - point.growthScore * (bottom - top),
        r: 1.25 + point.adoptionScore * 2.05
      };
    }

    function renderOpportunityNotes(points) {
      const notes = document.getElementById('opportunity-notes');
      if (!notes) return;
      if (!points.length) {
        notes.innerHTML = '<p class="empty-msg">No repository activity in the selected window yet.</p>';
        return;
      }
      const ranked = points.slice().sort((a, b) => {
        const aGap = a.attentionScore * (1 - a.growthScore);
        const bGap = b.attentionScore * (1 - b.growthScore);
        return bGap - aGap;
      }).slice(0, 3);
      notes.innerHTML = ranked.map((point) => {
        const label = classifyOpportunityPoint(point);
        return `
          <button class="opportunity-note" type="button" data-repo="${escapeHtml(point.repo)}">
            <span class="note-repo">${escapeHtml(point.shortName)}</span>
            <span class="note-label">${escapeHtml(label)}</span>
            <span class="note-meta">${formatNumber(point.attention)} attention · ${formatSigned(point.downstream)} growth</span>
          </button>`;
      }).join('');
      notes.querySelectorAll('.opportunity-note').forEach((button) => {
        button.addEventListener('click', function(event) {
          activateRepo(button.dataset.repo, !!(event && (event.metaKey || event.ctrlKey || event.shiftKey)));
        });
      });
    }

    function renderOpportunityMap() {
      const container = document.getElementById('opportunity-map');
      const card = document.getElementById('opportunity-card');
      if (!container || !card) return;
      const section = card.closest ? card.closest('.opportunity-section') : null;
      const repos = getVisibleRepos();
      if (!repos.length) {
        if (section) section.style.display = 'none';
        card.style.display = 'none';
        renderOpportunityNotes([]);
        return;
      }
      if (section) section.style.display = 'grid';
      card.style.display = 'block';
      const points = buildOpportunityPoints(repos);
      const pointMarkup = points.map((point, idx) => {
        const mapped = mapPoint(point);
        const label = classifyOpportunityPoint(point);
        const labelDy = idx % 2 ? -mapped.r - 0.8 : mapped.r + 2.35;
        return `
          <g class="opportunity-point" data-repo="${escapeHtml(point.repo)}" tabindex="0" role="button" aria-label="${escapeHtml(point.shortName + ': ' + label)}">
            <circle class="point-halo" cx="${mapped.x.toFixed(2)}" cy="${mapped.y.toFixed(2)}" r="${(mapped.r + 0.75).toFixed(2)}"></circle>
            <circle class="point-dot" cx="${mapped.x.toFixed(2)}" cy="${mapped.y.toFixed(2)}" r="${mapped.r.toFixed(2)}"></circle>
            <text x="${mapped.x.toFixed(2)}" y="${(mapped.y + labelDy).toFixed(2)}">${escapeHtml(point.shortName)}</text>
            <title>${escapeHtml(point.shortName)} · ${label} · ${formatNumber(point.attention)} attention · ${formatSigned(point.downstream)} growth · ${formatNumber(point.adoption)} clone activity</title>
          </g>`;
      }).join('');
      container.innerHTML = `
        <svg viewBox="0 0 100 64" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
          <defs>
            <pattern id="opportunity-grid" width="7" height="7" patternUnits="userSpaceOnUse">
              <path d="M7 0H0V7" fill="none"></path>
            </pattern>
          </defs>
          <rect class="map-frame" x="7" y="4" width="89" height="52" rx="3"></rect>
          <rect class="map-grid" x="7" y="4" width="89" height="52" rx="3"></rect>
          <line class="map-midline" x1="54" y1="6" x2="54" y2="54"></line>
          <line class="map-midline" x1="9" y1="31" x2="94" y2="31"></line>
          <text class="map-zone zone-seed" x="12" y="50">seed discovery</text>
          <text class="map-zone zone-clarify" x="60" y="50">clarify next step</text>
          <text class="map-zone zone-niche" x="12" y="13">protect niche pull</text>
          <text class="map-zone zone-amplify" x="60" y="13">amplify</text>
          <text class="map-axis axis-x" x="57" y="62">more attention</text>
          <text class="map-axis axis-y" x="3" y="36" transform="rotate(-90 3 36)">more downstream growth</text>
          ${pointMarkup}
        </svg>`;
      container.querySelectorAll('.opportunity-point').forEach((point) => {
        point.style.setProperty('--point-color', getRepoColor(point.dataset.repo));
        point.addEventListener('click', function(event) {
          activateRepo(point.dataset.repo, !!(event && (event.metaKey || event.ctrlKey || event.shiftKey)));
        });
        point.addEventListener('keydown', function(event) {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            activateRepo(point.dataset.repo, !!(event.metaKey || event.ctrlKey || event.shiftKey));
          }
        });
      });
      renderOpportunityNotes(points);
    }

  return { downstreamDelta, attentionValue, adoptionValue, buildOpportunityPoints, classifyOpportunityPoint, renderOpportunityMap };
}

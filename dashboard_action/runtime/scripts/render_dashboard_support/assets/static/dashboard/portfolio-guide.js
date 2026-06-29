export function installPortfolioGuide(context) {
  const document = context.document;
  const currentPayload = (...args) => context.currentPayload(...args);
  const escapeHtml = (...args) => context.escapeHtml(...args);
  const formatNumber = (...args) => context.formatNumber(...args);

  function signalRows(profile) {
    const signals = profile.signals || {};
    const rows = [
      ['Published', profile.repo_count, 'repos'],
      ['Active', signals.active_repos, 'repos'],
      ['Quiet', signals.quiet_repos, 'repos'],
      ['Events', signals.recent_event_count, 'recent'],
      ['Readiness', signals.readiness_gap_repos, 'gaps'],
      ['Maint.', signals.maintenance_items, 'open'],
    ];
    return rows.filter((row) => row[1] !== undefined && row[1] !== null && row[1] !== '');
  }

  function renderSignal(row) {
    const [label, value, detail] = row;
    return `
      <span class="profile-signal">
        <span>${escapeHtml(label)}</span>
        <strong>${formatNumber(value)}</strong>
        <em>${escapeHtml(detail)}</em>
      </span>`;
  }

  function renderGuidanceItem(item) {
    return `
      <li>
        <span>${escapeHtml(item.label || 'Move')}</span>
        <p>${escapeHtml(item.text || '')}</p>
      </li>`;
  }

  function renderPortfolioGuide() {
    const card = document.getElementById('portfolio-guide-card');
    const container = document.getElementById('portfolio-guide');
    if (!card || !container) return;
    const profile = currentPayload()?.portfolio_profile || {};
    if (!profile.id || profile.id === 'empty') {
      card.style.display = 'none';
      return;
    }
    card.style.display = 'block';
    const guidance = Array.isArray(profile.guidance) ? profile.guidance.slice(0, 3) : [];
    const signals = signalRows(profile);
    const fullSet = profile.signals?.selected_set_full
      ? '<span class="profile-note">Full 8-repo publish set</span>'
      : '';
    container.innerHTML = `
      <div class="profile-overview">
        <div class="profile-copy">
          <div class="profile-badges">
            <span class="profile-pill">${escapeHtml(profile.label || 'Project profile')}</span>
            <span class="profile-bucket">${escapeHtml(profile.bucket || '')}</span>
            ${fullSet}
          </div>
          <p>${escapeHtml(profile.summary || '')}</p>
          <strong>${escapeHtml(profile.primary_goal || '')}</strong>
        </div>
        <div class="profile-signal-grid">
          ${signals.map(renderSignal).join('')}
        </div>
      </div>
      ${guidance.length ? `<ul class="profile-guidance">${guidance.map(renderGuidanceItem).join('')}</ul>` : ''}`;
  }

  return { signalRows, renderPortfolioGuide };
}

export function installFormat(context) {
  const document = context.document;

    function formatNumber(value) {
      return Number(value || 0).toLocaleString();
    }

    function compactNumber(value) {
      const n = Number(value || 0);
      const abs = Math.abs(n);
      if (abs >= 1_000_000) return (n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1) + 'M';
      if (abs >= 1_000) return (n / 1_000).toFixed(n >= 10_000 ? 0 : 1) + 'k';
      return String(Math.round(n));
    }

    function axisTickLabel(value) {
      const n = Number(value || 0);
      if (Math.abs(n) <= 10 && !Number.isInteger(n)) return '';
      return compactNumber(n);
    }

    function formatSigned(value) {
      const n = Number(value || 0);
      return (n >= 0 ? '+' : '') + formatNumber(n);
    }

    function sumArray(values) {
      return (values || []).reduce((total, value) => total + Number(value || 0), 0);
    }

    function buildSparklinePath(values, width, height) {
      const n = (values || []).length;
      if (!n) { return { line: '', area: '' }; }
      if (n === 1) {
        const y = height / 2;
        return { line: `M0 ${y.toFixed(2)} L${width} ${y.toFixed(2)}`, area: '' };
      }
      const max = Math.max(...values);
      const min = Math.min(...values);
      const range = max - min || 1;
      const pad = 2;
      const innerH = height - pad * 2;
      const pts = values.map((v, i) => {
        const x = (i / (n - 1)) * width;
        const y = pad + (1 - (Number(v || 0) - min) / range) * innerH;
        return [x, y];
      });
      const line = pts.map(([x, y], i) => (i === 0 ? 'M' : 'L') + x.toFixed(2) + ' ' + y.toFixed(2)).join(' ');
      const area = line + ` L${width} ${height} L0 ${height} Z`;
      return { line, area };
    }

    function renderSparkline(id, values, color) {
      const el = document.getElementById(id);
      if (!el) return;
      if (!values || values.length < 2) {
        el.innerHTML = '';
        return;
      }
      const { line, area } = buildSparklinePath(values, 100, 34);
      // pathLength="1" normalizes the path's apparent stroke length to 1
      // unit so the CSS draw-in animation (stroke-dasharray: 1) always
      // covers the entire line regardless of how spiky the underlying
      // data is. Without this, jagged metrics (Views, Visitors) had path
      // lengths that exceeded the dash and clipped the tail.
      el.innerHTML =
        `<path class="area" d="${area}" fill="${color}"></path>` +
        `<path class="line" d="${line}" stroke="${color}" pathLength="1"></path>`;
    }

    function splitWindow(series) {
      const dates = (series && series.dates) || [];
      if (dates.length < 2) return null;
      const mid = Math.ceil(dates.length / 2);
      const slice = (arr) => ({
        first: (arr || []).slice(0, mid),
        second: (arr || []).slice(mid)
      });
      return {
        views: slice(series.views),
        uniques: slice(series.uniques),
        clones: slice(series.clones),
        clone_uniques: slice(series.clone_uniques),
        firstDays: mid,
        secondDays: dates.length - mid
      };
    }

    function computeDelta(split, field) {
      if (!split) return null;
      const f = split[field];
      if (!f) return null;
      const prior = sumArray(f.first);
      const current = sumArray(f.second);
      if (prior === 0 && current === 0) return null;
      // Prior window had no data (brand-new repo, or first collection
      // window). Percentage is undefined; omit the pill rather than
      // pretending we know the delta.
      if (prior === 0) return null;
      const pct = ((current - prior) / prior) * 100;
      let direction = 'flat';
      if (pct > 2) direction = 'up';
      else if (pct < -2) direction = 'down';
      return { pct, direction, current, prior };
    }

    function renderDelta(id, delta) {
      const el = document.getElementById(id);
      if (!el) return;
      if (!delta) {
        el.className = 'stat-delta hidden';
        el.textContent = '';
        return;
      }
      let label;
      if (delta.pct === null) {
        label = delta.label || 'new';
      } else {
        const sign = delta.pct >= 0 ? '+' : '';
        const arrow = delta.direction === 'up' ? '▲' : delta.direction === 'down' ? '▼' : '•';
        const rounded = Math.abs(delta.pct) >= 100 ? Math.round(delta.pct) : delta.pct.toFixed(1);
        label = `${arrow} ${sign}${rounded}%`;
      }
      el.className = 'stat-delta ' + (delta.direction || 'flat');
      el.textContent = label;
    }

  return { formatNumber, compactNumber, axisTickLabel, formatSigned, sumArray, buildSparklinePath, renderSparkline, splitWindow, computeDelta, renderDelta };
}

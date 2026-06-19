export function installQualityCalendar(context) {
  const document = context.document;
  const window = context.window;
  const currentPayload = (...args) => context.currentPayload(...args);
  const escapeHtml = (...args) => context.escapeHtml(...args);
  const formatIsoDate = (...args) => context.formatIsoDate(...args);
  const formatNumber = (...args) => context.formatNumber(...args);
  const getSelectedWindow = (...args) => context.getSelectedWindow(...args);
  const getVisibleRepos = (...args) => context.getVisibleRepos(...args);
  const getWindowCutoffDate = (...args) => context.getWindowCutoffDate(...args);
  const hasTrafficLag = (...args) => context.hasTrafficLag(...args);
  const parseIsoDate = (...args) => context.parseIsoDate(...args);
  const state = context.state;

    function qualityDaysForSelectedWindow() {
      const allDays = applyVisibilityThresholdToQualityDays(
        (currentPayload()?.data_quality?.days || []).slice()
      );
      if (!allDays.length) return [];
      if (getSelectedWindow() === 'all') return allDays;
      const cutoff = getWindowCutoffDate();
      if (!cutoff) return allDays;
      return allDays.filter((day) => String(day.date || '') >= cutoff);
    }

    function summarizeQualityDayStatuses(day, repos) {
      const counts = {
        ok_with_data: 0,
        ok_zero_data: 0,
        skipped_unavailable: 0,
        error: 0,
        error_secondary_rate_limit: 0,
      };
      (repos || []).forEach((row) => {
        const status = String(row?.status || '');
        if (status in counts) counts[status] += 1;
      });
      const trackedRepos = (repos || []).length;
      const withDataRepos = counts.ok_with_data;
      const zeroTrafficRepos = counts.ok_zero_data;
      const skippedRepos = counts.skipped_unavailable;
      const errorRepos = counts.error + counts.error_secondary_rate_limit;
      const observedRepos = withDataRepos + zeroTrafficRepos;
      const hasCollectionGaps = skippedRepos > 0 || errorRepos > 0;
      let status = 'healthy';
      if (hasCollectionGaps) status = 'gaps_detected';
      else if (trackedRepos > 0 && zeroTrafficRepos === trackedRepos) status = 'all_zero';
      return {
        ...day,
        status,
        has_collection_gaps: hasCollectionGaps,
        tracked_repos: trackedRepos,
        with_data_repos: withDataRepos,
        zero_traffic_repos: zeroTrafficRepos,
        skipped_repos: skippedRepos,
        error_repos: errorRepos,
        coverage_ratio: trackedRepos ? Math.round((observedRepos / trackedRepos) * 10000) / 10000 : 1,
        repos: repos || [],
      };
    }

    function applyVisibilityThresholdToQualityDays(days) {
      const hasRepoBreakdown = (days || []).some((day) => Array.isArray(day?.repos) && day.repos.length > 0);
      if (!hasRepoBreakdown) return days;
      const visibleRepoNames = new Set(getVisibleRepos().map((repo) => repo.name));
      if (!visibleRepoNames.size) return [];
      return (days || [])
        .map((day) => {
          const dayRepos = Array.isArray(day?.repos) ? day.repos : [];
          const filtered = dayRepos.filter((row) => visibleRepoNames.has(String(row?.repo || '')));
          return summarizeQualityDayStatuses(day, filtered);
        })
        .filter((day) => Number(day?.tracked_repos || 0) > 0);
    }

    function monthKeyFromIsoDate(value) {
      const raw = String(value || '');
      return raw.length >= 7 ? raw.slice(0, 7) : '';
    }

    function parseMonthKey(key) {
      if (!/^\d{4}-\d{2}$/.test(String(key || ''))) return null;
      const year = Number(key.slice(0, 4));
      const month = Number(key.slice(5, 7));
      if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) return null;
      return { year, month };
    }

    function monthLabelFromKey(key) {
      const parsed = parseMonthKey(key);
      if (!parsed) return 'No data';
      const date = new Date(Date.UTC(parsed.year, parsed.month - 1, 1));
      return date.toLocaleString(undefined, { month: 'long', year: 'numeric', timeZone: 'UTC' });
    }

    function latestMonthKeyFallback() {
      const qualityDays = currentPayload()?.data_quality?.days || [];
      if (qualityDays.length) {
        return monthKeyFromIsoDate(qualityDays[qualityDays.length - 1].date);
      }
      const dates = currentPayload()?.daily?.dates || [];
      if (dates.length) {
        return monthKeyFromIsoDate(dates[dates.length - 1]);
      }
      return '';
    }

    function calendarMonthKeys(days) {
      const keys = Array.from(new Set((days || []).map((day) => monthKeyFromIsoDate(day.date)).filter(Boolean))).sort();
      if (keys.length) return keys;
      const fallback = latestMonthKeyFallback();
      return fallback ? [fallback] : [];
    }

    function resolveCalendarMonth(days, monthKeys) {
      if (!monthKeys.length) {
        state.calendarMonth = null;
        return null;
      }
      if (!state.calendarMonth || !monthKeys.includes(state.calendarMonth)) {
        state.calendarMonth = monthKeys[monthKeys.length - 1];
      }
      return state.calendarMonth;
    }

    function daysInMonth(year, month) {
      return new Date(Date.UTC(year, month, 0)).getUTCDate();
    }

    function calendarStatusLabel(day) {
      if (!day) return 'no-run';
      if (String(day.status || '') === 'no_run') return 'no-run';
      if (day.has_collection_gaps) return 'collection-gap';
      if (String(day.status || '') === 'all_zero') return 'all-zero';
      return 'healthy';
    }

    function visibleTrafficReportingRanges() {
      const ranges = currentPayload()?.traffic_reporting?.unreported_ranges || [];
      const visibleRepos = new Set(getVisibleRepos().map((repo) => repo.name));
      if (!visibleRepos.size) return [];
      return ranges.filter((range) => visibleRepos.has(String(range?.repo || '')));
    }

    function trafficReportingByDate() {
      const byDate = new Map();
      visibleTrafficReportingRanges().forEach((range) => {
        const repo = String(range?.repo || '');
        const start = parseIsoDate(range?.start);
        const end = parseIsoDate(range?.end);
        if (!repo || !start || !end) return;
        const cursor = new Date(start.getTime());
        while (cursor.getTime() <= end.getTime()) {
          const iso = formatIsoDate(cursor);
          if (!byDate.has(iso)) byDate.set(iso, []);
          byDate.get(iso).push(repo);
          cursor.setUTCDate(cursor.getUTCDate() + 1);
        }
      });
      byDate.forEach((repos, date) => {
        byDate.set(date, Array.from(new Set(repos)).sort());
      });
      return byDate;
    }

    function calendarStateForDay(day, unreportedRepos) {
      if (!day || String(day.status || '') === 'no_run') {
        return {
          label: 'no-run',
          className: 'calendar-day no-run',
          summary: 'no workflow run',
        };
      }
      const skipped = Number(day.skipped_repos || 0);
      const errors = Number(day.error_repos || 0);
      const hasTrafficLag = (unreportedRepos || []).length > 0;
      if (errors > 0 || skipped > 0 || day.has_collection_gaps) {
        return {
          label: hasTrafficLag ? 'collection-gap + traffic-lag' : 'collection-gap',
          className: `calendar-day gap${hasTrafficLag ? ' lag' : ''}`,
          summary: 'collection ran with skipped or failed repo checks',
        };
      }
      if (hasTrafficLag) {
        return {
          label: 'traffic-lag',
          className: 'calendar-day lag',
          summary: 'collection ran; GitHub did not report traffic for this trailing date',
        };
      }
      if (String(day.status || '') === 'all_zero') {
        return {
          label: 'all-zero',
          className: 'calendar-day zero',
          summary: 'collection ran; GitHub reported zero traffic',
        };
      }
      return {
        label: 'healthy',
        className: 'calendar-day ok',
        summary: 'collection ran; traffic was reported',
      };
    }

    function formatCalendarDayTooltip(day, unreportedRepos) {
      const stateForDay = calendarStateForDay(day, unreportedRepos);
      const parts = [
        `${day.date} · ${stateForDay.summary}`,
        `status ${stateForDay.label}`,
        `tracked ${formatNumber(day.tracked_repos || 0)}`,
        `with data ${formatNumber(day.with_data_repos || 0)}`,
        `zero ${formatNumber(day.zero_traffic_repos || 0)}`,
        `skipped ${formatNumber(day.skipped_repos || 0)}`,
        `errors ${formatNumber(day.error_repos || 0)}`
      ];
      if ((unreportedRepos || []).length) {
        parts.push(`GitHub traffic unreported for ${formatNumber(unreportedRepos.length)} repo(s)`);
        parts.push(`repos: ${unreportedRepos.slice(0, 4).join(', ')}${unreportedRepos.length > 4 ? ', …' : ''}`);
      }
      if (Number(day.run_count || 0) > 1) {
        parts.push(`${formatNumber(day.run_count)} runs`);
      }
      return parts.join(' · ');
    }

    function renderCollectionCalendar() {
      const panel = document.getElementById('calendar-panel');
      const monthLabel = document.getElementById('calendarMonthLabel');
      const grid = document.getElementById('calendarGrid');
      const hint = document.getElementById('calendarHint');
      const dayDetail = document.getElementById('calendarDayDetail');
      const prevBtn = document.getElementById('calendarPrevBtn');
      const nextBtn = document.getElementById('calendarNextBtn');
      if (!panel || !monthLabel || !grid || !hint || !dayDetail || !prevBtn || !nextBtn) return;

      const days = qualityDaysForSelectedWindow();
      const monthKeys = calendarMonthKeys(days);
      const activeMonth = resolveCalendarMonth(days, monthKeys);
      const monthIndex = activeMonth ? monthKeys.indexOf(activeMonth) : -1;
      prevBtn.disabled = monthIndex <= 0;
      nextBtn.disabled = monthIndex < 0 || monthIndex >= monthKeys.length - 1;

      if (!activeMonth) {
        panel.style.display = 'none';
        dayDetail.textContent = '';
        return;
      }

      panel.style.display = '';
      monthLabel.textContent = monthLabelFromKey(activeMonth);

      const parsed = parseMonthKey(activeMonth);
      if (!parsed) {
        grid.innerHTML = '';
        hint.textContent = 'Collection status per day in the selected window.';
        dayDetail.textContent = 'Hover or focus a day to inspect collection details.';
        return;
      }

      const byDate = new Map((days || []).map((day) => [String(day.date || ''), day]));
      const reportingByDate = trafficReportingByDate();
      const firstDay = new Date(Date.UTC(parsed.year, parsed.month - 1, 1));
      const leading = (firstDay.getUTCDay() + 6) % 7;
      const count = daysInMonth(parsed.year, parsed.month);

      const cells = [];
      for (let i = 0; i < leading; i += 1) {
        cells.push('<span class="calendar-day blank" aria-hidden="true"></span>');
      }
      for (let dayNum = 1; dayNum <= count; dayNum += 1) {
        const iso = `${parsed.year}-${String(parsed.month).padStart(2, '0')}-${String(dayNum).padStart(2, '0')}`;
        const day = byDate.get(iso);
        const unreportedRepos = reportingByDate.get(iso) || [];
        let cls = 'calendar-day no-run';
        let detail = `${iso} · no workflow run · traffic availability unknown`;
        let title = detail;
        if (day) {
          const stateForDay = calendarStateForDay(day, unreportedRepos);
          cls = stateForDay.className;
          detail = formatCalendarDayTooltip(day, unreportedRepos);
          title = detail;
        } else if (unreportedRepos.length) {
          cls = 'calendar-day lag';
          detail = `${iso} · GitHub traffic unreported for ${formatNumber(unreportedRepos.length)} repo(s) · no collection-day row`;
          title = detail;
        }
        cells.push(
          `<span class="${cls}" title="${escapeHtml(title)}" data-detail="${escapeHtml(detail)}" tabindex="0">${dayNum}</span>`
        );
      }
      const trailing = (7 - (cells.length % 7)) % 7;
      for (let i = 0; i < trailing; i += 1) {
        cells.push('<span class="calendar-day blank" aria-hidden="true"></span>');
      }
      grid.innerHTML = cells.join('');
      const defaultDayDetail = 'Hover or focus a day to inspect collection details.';
      dayDetail.textContent = defaultDayDetail;
      grid.querySelectorAll('.calendar-day:not(.blank)').forEach((cell) => {
        const showDetail = function() {
          const detail = cell.getAttribute('data-detail') || '';
          dayDetail.textContent = detail || defaultDayDetail;
        };
        const resetDetail = function() {
          dayDetail.textContent = defaultDayDetail;
        };
        cell.addEventListener('mouseenter', showDetail);
        cell.addEventListener('focus', showDetail);
        cell.addEventListener('click', showDetail);
        cell.addEventListener('mouseleave', resetDetail);
        cell.addEventListener('blur', resetDetail);
      });

      const gapDays = days.filter((day) => day.has_collection_gaps).length;
      const windowCutoff = getSelectedWindow() === 'all' ? '' : (getWindowCutoffDate() || '');
      const lagDays = Array.from(reportingByDate.keys())
        .filter((date) => !windowCutoff || date >= windowCutoff)
        .length;
      const zeroDays = days.filter((day) => day.status === 'all_zero').length;
      const noRunStats = computeNoRunStats(days);
      const streakText = noRunStats.longestNoRunStreak > 0
        ? ` (longest streak ${formatNumber(noRunStats.longestNoRunStreak)})`
        : '';
      hint.textContent = (
        `${formatNumber(noRunStats.collectedDays)} collected day(s), `
        + `${formatNumber(noRunStats.noRunDays)} no-run day(s)${streakText}, `
        + `${formatNumber(gapDays)} collection gap day(s), `
        + `${formatNumber(lagDays)} traffic lag day(s), `
        + `${formatNumber(zeroDays)} all-zero day(s).`
      );
    }

    function shiftCalendarMonth(delta) {
      const days = qualityDaysForSelectedWindow();
      const monthKeys = calendarMonthKeys(days);
      if (!monthKeys.length) return;
      const activeMonth = resolveCalendarMonth(days, monthKeys);
      const index = Math.max(0, monthKeys.indexOf(activeMonth));
      const nextIndex = Math.min(monthKeys.length - 1, Math.max(0, index + delta));
      state.calendarMonth = monthKeys[nextIndex];
      renderCollectionCalendar();
    }

    function computeNoRunStats(days) {
      const dayByDate = new Map(
        (days || [])
          .filter((day) => String(day?.date || ''))
          .map((day) => [String(day.date), day])
      );
      const allDates = Array.from(dayByDate.keys()).sort();
      if (!allDates.length) {
        return {
          collectedDays: 0,
          noRunDays: 0,
          longestNoRunStreak: 0
        };
      }

      const start = parseIsoDate(allDates[0]);
      const end = parseIsoDate(allDates[allDates.length - 1]);
      if (!start || !end) {
        return {
          collectedDays: allDates.filter((date) => String(dayByDate.get(date)?.status || '') !== 'no_run').length,
          noRunDays: 0,
          longestNoRunStreak: 0
        };
      }

      const cursor = new Date(start.getTime());
      let collectedDays = 0;
      let noRunDays = 0;
      let streak = 0;
      let longestNoRunStreak = 0;

      while (cursor.getTime() <= end.getTime()) {
        const iso = formatIsoDate(cursor);
        const day = dayByDate.get(iso);
        if (day && String(day.status || '') !== 'no_run') {
          collectedDays += 1;
          streak = 0;
        } else {
          noRunDays += 1;
          streak += 1;
          if (streak > longestNoRunStreak) longestNoRunStreak = streak;
        }
        cursor.setUTCDate(cursor.getUTCDate() + 1);
      }

      return {
        collectedDays,
        noRunDays,
        longestNoRunStreak
      };
    }

  return { qualityDaysForSelectedWindow, summarizeQualityDayStatuses, applyVisibilityThresholdToQualityDays, monthKeyFromIsoDate, parseMonthKey, monthLabelFromKey, latestMonthKeyFallback, calendarMonthKeys, resolveCalendarMonth, daysInMonth, calendarStatusLabel, visibleTrafficReportingRanges, trafficReportingByDate, calendarStateForDay, formatCalendarDayTooltip, renderCollectionCalendar, shiftCalendarMonth, computeNoRunStats };
}

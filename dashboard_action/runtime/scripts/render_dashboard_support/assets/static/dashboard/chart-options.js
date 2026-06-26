export function installChartOptions(context) {
  const axisTickLabel = (...args) => context.axisTickLabel(...args);
  const formatTooltipDate = (...args) => context.formatTooltipDate(...args);
  const getThemeColor = (...args) => context.getThemeColor(...args);

    function chartOptions(stacked) {
      const tick = getThemeColor('--text-muted', '#a4b1c1');
      const grid = getThemeColor('--chart-grid', 'rgba(38, 45, 56, 0.4)');
      const axis = getThemeColor('--chart-axis', 'rgba(38, 45, 56, 0.7)');
      const tipBg = getThemeColor('--chart-tooltip-bg', 'rgba(12, 16, 22, 0.97)');
      const tipBorder = getThemeColor('--chart-tooltip-border', 'rgba(214, 168, 75, 0.30)');
      const text = getThemeColor('--text', '#edf3f8');
      return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        animation: { duration: 320 },
        plugins: {
          legend: {
            display: !!stacked,
            position: 'bottom',
            labels: { color: tick, boxWidth: 10, boxHeight: 10, usePointStyle: true, padding: 14 }
          },
          tooltip: {
            backgroundColor: tipBg,
            borderColor: tipBorder,
            borderWidth: 1,
            titleColor: text,
            bodyColor: text,
            padding: 10,
            cornerRadius: 8,
            caretSize: 6,
            boxPadding: 4,
            usePointStyle: true,
            callbacks: {
              title: function(items) { return items.length ? formatTooltipDate(items[0].label) : ''; },
              label: function(ctx) {
                const value = ctx.parsed && typeof ctx.parsed.y === 'number' ? ctx.parsed.y : ctx.parsed;
                return ' ' + (ctx.dataset.label || '') + '  ' + Number(value || 0).toLocaleString();
              }
            }
          }
        },
        scales: {
          x: {
            ticks: { color: tick, maxRotation: 0, autoSkipPadding: 18 },
            grid: { color: grid, drawTicks: false },
            border: { color: axis }
          },
          y: {
            beginAtZero: true,
            grace: '8%',
            stacked: !!stacked,
            ticks: {
              color: tick,
              precision: 0,
              callback: function(value) { return axisTickLabel(value); }
            },
            grid: { color: grid, drawTicks: false },
            border: { display: false }
          }
        }
      };
    }

    function numericDatasetValues(datasets) {
      return (datasets || []).flatMap((dataset) =>
        (dataset.data || [])
          .filter((value) => value !== null && value !== undefined)
          .map((value) => Number(value))
          .filter((value) => Number.isFinite(value))
      );
    }

    function stackedDatasetValues(labels, datasets) {
      return (labels || []).map((_, idx) =>
        (datasets || []).reduce((total, dataset) => {
          const value = dataset.data?.[idx];
          const n = Number(value);
          return Number.isFinite(n) ? total + n : total;
        }, 0)
      );
    }

    function configureYAxis(chart, labels, datasets, stacked) {
      const y = chart?.options?.scales?.y;
      if (!y) return;
      const values = stacked ? stackedDatasetValues(labels, datasets) : numericDatasetValues(datasets);
      const finite = values.filter((value) => Number.isFinite(value));
      const min = finite.length ? Math.min(...finite) : 0;
      const max = finite.length ? Math.max(...finite) : 0;
      const largest = Math.max(Math.abs(min), Math.abs(max));

      y.beginAtZero = min >= 0;
      y.grace = '8%';
      delete y.min;
      delete y.max;
      delete y.suggestedMax;
      if (y.ticks) {
        y.ticks.precision = 0;
        delete y.ticks.stepSize;
        y.ticks.callback = function(value) { return axisTickLabel(value); };
      }

      if (largest <= 5) {
        y.grace = 0;
        if (y.ticks) y.ticks.stepSize = 1;
        if (min < 0) {
          y.min = Math.floor(min) - 1;
          y.max = Math.ceil(max) + 1;
        } else {
          y.min = 0;
          y.max = Math.max(1, Math.ceil(max) + 1);
        }
      }
    }

  return { chartOptions, numericDatasetValues, stackedDatasetValues, configureYAxis };
}

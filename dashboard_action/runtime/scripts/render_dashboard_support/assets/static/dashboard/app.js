import { createChartAdapter } from './chart-adapter.js';
import { installState } from './state.js';
import { installDataProvider } from './data-provider.js';
import { installTheme } from './theme.js';
import { installFormat } from './format.js';
import { installSelection } from './selection.js';
import { installQualityCalendar } from './quality-calendar.js';
import { installSeries } from './series.js';
import { installMomentum } from './momentum.js';
import { installChartOptions } from './chart-options.js';
import { installControls } from './controls.js';
import { installCharts } from './charts.js';
import { installOpportunityMap } from './opportunity-map.js';
import { installEventGraph } from './event-graph.js';
import { installReadinessQueue } from './readiness-queue.js';
import { installTables } from './tables.js';
import { installController } from './controller.js';

const installers = [
  installState,
  installDataProvider,
  installTheme,
  installFormat,
  installSelection,
  installQualityCalendar,
  installSeries,
  installMomentum,
  installChartOptions,
  installControls,
  installEventGraph,
  installCharts,
  installOpportunityMap,
  installReadinessQueue,
  installTables,
  installController,
];

export function createDashboardApp(options = {}) {
  const win = options.window || globalThis.window;
  const doc = options.document || win?.document || globalThis.document;
  const context = {
    document: doc,
    window: win,
    navigator: options.navigator || win?.navigator || globalThis.navigator,
    localStorage: options.localStorage || win?.localStorage || globalThis.localStorage,
    history: options.history || win?.history || globalThis.history,
    getComputedStyle: options.getComputedStyle || win?.getComputedStyle?.bind(win) || globalThis.getComputedStyle,
    chartAdapter: options.chartAdapter || createChartAdapter(options.Chart || globalThis.Chart),
    charts: {
      dailyChart: null,
      weekdayChart: null,
      stackedChart: null,
    },
  };

  installers.forEach((install) => {
    Object.assign(context, install(context));
  });

  return {
    context,
    renderDashboard(payload) {
      return context.renderDashboard(payload);
    },
    updateDashboard() {
      return context.updateDashboard();
    },
    applyTheme(theme, persist) {
      return context.applyTheme(theme, persist);
    },
    preferredTheme() {
      return context.preferredTheme();
    },
    toggleTheme() {
      return context.toggleTheme();
    },
  };
}

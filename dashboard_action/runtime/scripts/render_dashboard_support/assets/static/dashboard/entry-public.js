import { createDashboardApp } from './app.js';
import { readJsonAsset } from './json-assets.js';

const dashboardData = await readJsonAsset(
  document,
  'reponomics-dashboard-data',
  'plaintext-dashboard-data'
);

createDashboardApp().renderDashboard(dashboardData);

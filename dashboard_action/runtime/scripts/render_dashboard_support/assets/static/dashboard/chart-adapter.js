export function createChartAdapter(chartConstructor = globalThis.Chart) {
  return {
    createChart(element, config) {
      if (!chartConstructor) {
        throw new Error('Chart.js was not loaded before the dashboard module.');
      }
      return new chartConstructor(element, config);
    }
  };
}

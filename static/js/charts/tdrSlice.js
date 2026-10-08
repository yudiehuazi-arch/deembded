/** TDR 曲线的时间窗裁剪与抽点（纯函数）。 */

import { TDR_DISPLAY_POINTS_DEFAULT } from '../config/constants.js';

/**
 * 按时间范围与点数上限裁剪 TDR 结果。
 * @param {{time_ns: number[], series?: Object<string, number[]>, impedance_ohm?: number[]}} data
 * @param {{startNs?: number|string, endNs?: number|string, pointLimit?: number|string}} window
 */
export function sliceTdrDisplay(data, { startNs = '', endNs = '', pointLimit = TDR_DISPLAY_POINTS_DEFAULT } = {}) {
  if (!data?.time_ns?.length) return { time_ns: [], series: {} };
  const time = data.time_ns;
  const parsedStart = startNs === '' || startNs === null ? 0 : Number(startNs);
  const parsedEnd = endNs === '' || endNs === null ? time[time.length - 1] : Number(endNs);
  const start = Number.isFinite(parsedStart) ? Math.max(time[0], parsedStart) : time[0];
  const end = Number.isFinite(parsedEnd) ? Math.min(time[time.length - 1], parsedEnd) : time[time.length - 1];

  const indices = [];
  if (end >= start) {
    for (let i = 0; i < time.length; i++) if (time[i] >= start && time[i] <= end) indices.push(i);
  }

  const sourceSeries = data.series || { input: data.impedance_ohm || [] };
  const limit = Math.max(2, Number.parseInt(pointLimit, 10) || TDR_DISPLAY_POINTS_DEFAULT);
  let plottedIndices = indices;
  if (indices.length > limit) {
    plottedIndices = Array.from({ length: limit }, (_, i) => indices[Math.round((i * (indices.length - 1)) / (limit - 1))]);
  }

  const series = {};
  Object.entries(sourceSeries).forEach(([key, values]) => {
    series[key] = plottedIndices.map((index) => values[index]);
  });
  return { time_ns: plottedIndices.map((index) => time[index]), series };
}

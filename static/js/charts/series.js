/** 曲线构造：把接口数据转换为 renderer 需要的 trace 列表（纯函数）。 */

import { INPUT_PARAMETER_DASHES, INPUT_TDR_COLORS, INPUT_TDR_NETWORK_LABELS, INPUT_TDR_NETWORK_ORDER, MAX_CHART_PARAMETERS, NETWORK_DASH, NETWORK_DOT_COLORS, PARAMETER_COLORS } from '../config/constants.js';
import { networkLabel } from '../core/format.js';

/** 结果图表（频域）：参数 × 网络 → 曲线 */
export function buildResultSparamTraces(calculation, parameters, networkKeys) {
  const traces = [];
  parameters.forEach((parameter, parameterIndex) => {
    const color = PARAMETER_COLORS[parameterIndex % PARAMETER_COLORS.length];
    networkKeys.forEach((networkKey) => {
      const values = calculation?.chart?.series?.[parameter]?.[networkKey];
      if (!values) return;
      traces.push({
        values,
        color,
        dash: NETWORK_DASH[networkKey] || [],
        width: networkKey === 'dut' ? 2.2 : 1.45,
        alpha: networkKey === 'dut' ? 1 : 0.78,
        label: `${parameter} · ${networkLabel(networkKey, calculation)}`,
        networkKey,
        parameter,
      });
    });
  });
  return traces;
}

/** 结果图表（时域）：每条网络一条阶跃阻抗曲线 */
export function buildResultTdrTraces(display, networkKeys, parameter, calculation = null) {
  return networkKeys
    .filter((key) => display.series?.[key])
    .map((key) => ({
      values: display.series[key],
      color: NETWORK_DOT_COLORS[key],
      dash: NETWORK_DASH[key] || [],
      width: key === 'dut' ? 2.2 : 1.6,
      alpha: key === 'dut' ? 1 : 0.82,
      label: `${networkLabel(key, calculation)} · ${parameter}`,
      networkKey: key,
    }));
}

/** 输入图表（频域）：按 A / Total / B 各自参数叠加，并插值到共同频段 */
export function buildInputSparamDisplay(items) {
  if (!items.length) return null;
  const start = Math.max(...items.map((item) => Number(item.preview.freq_ghz[0])));
  const lastValues = items.map((item) => item.preview.freq_ghz[item.preview.freq_ghz.length - 1]);
  const stop = Math.min(...lastValues.map(Number));
  if (!Number.isFinite(start) || !Number.isFinite(stop) || stop <= start) return null;

  const count = Math.max(8, Math.min(600, ...items.map((item) => item.preview.freq_ghz.length)));
  const freqGhz = Array.from({ length: count }, (_, index) => start + ((stop - start) * index) / (count - 1));

  const traces = [];
  items.forEach((item) => {
    item.codes.forEach((code, parameterIndex) => {
      const sourceFreq = item.preview.freq_ghz;
      const sourceValues = item.preview.series[code] || [];
      let cursor = 0;
      const values = freqGhz.map((frequency) => {
        while (cursor + 1 < sourceFreq.length && Number(sourceFreq[cursor + 1]) < frequency) cursor++;
        const x0 = Number(sourceFreq[cursor]);
        const x1 = Number(sourceFreq[Math.min(cursor + 1, sourceFreq.length - 1)]);
        const y0 = Number(sourceValues[cursor]);
        const y1 = Number(sourceValues[Math.min(cursor + 1, sourceValues.length - 1)]);
        if (frequency < x0 || (frequency > x1 && cursor + 1 >= sourceFreq.length)) return NaN;
        if (x1 === x0) return Number.isFinite(y0) ? y0 : NaN;
        return Number.isFinite(y0) && Number.isFinite(y1) ? y0 + (y1 - y0) * ((frequency - x0) / (x1 - x0)) : NaN;
      });
      traces.push({
        slot: item.slot,
        code,
        label: `${item.label} · ${code}`,
        values,
        color: INPUT_TDR_COLORS[item.slot],
        dash: INPUT_PARAMETER_DASHES[parameterIndex % INPUT_PARAMETER_DASHES.length] || [],
        width: 1.9,
      });
    });
  });

  if (traces.length > MAX_CHART_PARAMETERS * 3) traces.length = MAX_CHART_PARAMETERS * 3;
  return { freq_ghz: freqGhz, traces };
}

/** 输入图表（时域）：A / Total / B 三条阶跃阻抗曲线 */
export function buildInputTdrTraces(display, parameter) {
  return INPUT_TDR_NETWORK_ORDER.filter((key) => display.series?.[key]).map((key) => ({
    key,
    label: `${INPUT_TDR_NETWORK_LABELS[key]} · ${parameter}`,
    values: display.series[key],
    color: INPUT_TDR_COLORS[key],
    dash: NETWORK_DASH[key] || [],
    width: key === 'total' ? 2.1 : 1.8,
  }));
}

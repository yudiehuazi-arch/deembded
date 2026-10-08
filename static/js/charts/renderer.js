/** Canvas 折线图渲染器（与业务无关，只负责绘制）。 */

import { CHART_PADDING } from '../config/constants.js';
import { chartScaleWithLimits } from './scale.js';

/**
 * 绘制折线图。
 * @param {HTMLCanvasElement} targetCanvas
 * @param {number[]} xValues 横轴数据（频率 GHz 或时间 ns）
 * @param {{values: number[], color: string, dash?: number[], width?: number, alpha?: number}[]} traces
 * @param {{xDecimals?: number, yMin?: number|null, yMax?: number|null}} options
 */
export function drawLineChart(targetCanvas, xValues, traces, options = {}) {
  if (!targetCanvas) return;
  const rect = targetCanvas.getBoundingClientRect();
  if (rect.width < 10 || rect.height < 10) return;

  const ratio = Math.max(1, window.devicePixelRatio || 1);
  targetCanvas.width = Math.round(rect.width * ratio);
  targetCanvas.height = Math.round(rect.height * ratio);
  const ctx = targetCanvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);

  if (!xValues?.length) return;

  const { left: padLeft, right: padRight, top: padTop, bottom: padBottom } = CHART_PADDING;
  const width = rect.width;
  const height = rect.height;
  const plotW = Math.max(20, width - padLeft - padRight);
  const plotH = Math.max(20, height - padTop - padBottom);
  const scale = chartScaleWithLimits(
    traces.flatMap((trace) => trace.values),
    { min: options.yMin, max: options.yMax },
  );
  if (!scale) return;
  const { yMin, yMax } = scale;

  const xAt = (index) => padLeft + (xValues.length <= 1 ? 0 : index / (xValues.length - 1)) * plotW;
  const yAt = (value) => padTop + ((yMax - value) / (yMax - yMin)) * plotH;

  ctx.font = '10px Inter, system-ui, sans-serif';
  ctx.textBaseline = 'middle';

  for (let tick = 0; tick <= 5; tick++) {
    const value = yMax - ((yMax - yMin) * tick) / 5;
    const y = padTop + (plotH * tick) / 5;
    ctx.strokeStyle = 'rgba(126,151,174,.14)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(width - padRight, y);
    ctx.stroke();
    ctx.fillStyle = '#718399';
    ctx.textAlign = 'right';
    ctx.fillText(value.toFixed(0), padLeft - 9, y);
  }

  const xTicks = Math.min(5, Math.max(2, xValues.length - 1));
  for (let tick = 0; tick <= xTicks; tick++) {
    const x = padLeft + (plotW * tick) / xTicks;
    const index = Math.round(((xValues.length - 1) * tick) / xTicks);
    const label = xValues[index];
    ctx.strokeStyle = 'rgba(126,151,174,.1)';
    ctx.beginPath();
    ctx.moveTo(x, padTop);
    ctx.lineTo(x, padTop + plotH);
    ctx.stroke();
    ctx.fillStyle = '#718399';
    ctx.textAlign = tick === 0 ? 'left' : tick === xTicks ? 'right' : 'center';
    ctx.fillText(Number(label).toFixed(options.xDecimals ?? 2), x, height - 11);
  }

  ctx.strokeStyle = 'rgba(148,163,184,.25)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padLeft, padTop);
  ctx.lineTo(padLeft, padTop + plotH);
  ctx.lineTo(width - padRight, padTop + plotH);
  ctx.stroke();

  traces.forEach((trace) => {
    ctx.beginPath();
    ctx.strokeStyle = trace.color;
    ctx.globalAlpha = trace.alpha ?? 1;
    ctx.lineWidth = trace.width || 1.8;
    ctx.setLineDash(trace.dash || []);
    let started = false;
    const count = Math.min(xValues.length, trace.values.length);
    for (let i = 0; i < count; i++) {
      const value = trace.values[i];
      if (!Number.isFinite(value)) {
        started = false;
        continue;
      }
      const x = xAt(i);
      const y = yAt(value);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
  });

  ctx.globalAlpha = 1;
  ctx.setLineDash([]);
  ctx.textAlign = 'left';
}

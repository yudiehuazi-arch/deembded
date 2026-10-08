/** 画布几何与坐标换算（纯函数，可单测）。 */

import { CHART_PADDING } from '../config/constants.js';

export { CHART_PADDING };

export function plotGeometry(element) {
  const rect = element.getBoundingClientRect();
  const plotWidth = rect.width - CHART_PADDING.left - CHART_PADDING.right;
  const plotHeight = rect.height - CHART_PADDING.top - CHART_PADDING.bottom;
  return {
    rect,
    width: rect.width,
    height: rect.height,
    plotLeft: CHART_PADDING.left,
    plotTop: CHART_PADDING.top,
    plotWidth,
    plotHeight,
  };
}

/** 采样点数 + 归一化位置(0–1) → 索引位置（可能是小数，用于线性插值）。 */
export function indexPositionForFraction(count, fraction) {
  const clamped = Math.max(0, Math.min(1, fraction));
  return clamped * Math.max(0, count - 1);
}

/** 按索引位置线性插值；越界或非数值返回 NaN。 */
export function interpolateAt(values, indexPosition) {
  if (!values?.length) return NaN;
  const index = Math.floor(indexPosition);
  const nextIndex = Math.min(values.length - 1, index + 1);
  const rawFirst = values[index];
  const rawSecond = values[nextIndex];
  const first = rawFirst == null || rawFirst === '' ? NaN : Number(rawFirst);
  const second = rawSecond == null || rawSecond === '' ? NaN : Number(rawSecond);
  if (index === nextIndex) return Number.isFinite(first) ? first : NaN;
  if (!Number.isFinite(first) || !Number.isFinite(second)) return NaN;
  return first + (second - first) * (indexPosition - index);
}

/** 在单调递增数组中找到目标值的归一化位置；不在范围内返回 null。 */
export function fractionForXValue(values, target) {
  if (!values?.length || !Number.isFinite(target)) return null;
  if (values.length === 1) return target === Number(values[0]) ? 0 : null;
  const first = Number(values[0]);
  const last = Number(values[values.length - 1]);
  if (!Number.isFinite(first) || !Number.isFinite(last) || target < first || target > last) return null;
  let low = 0;
  let high = values.length - 1;
  while (high - low > 1) {
    const mid = (low + high) >> 1;
    if (Number(values[mid]) < target) low = mid;
    else high = mid;
  }
  const x0 = Number(values[low]);
  const x1 = Number(values[high]);
  const indexPosition = x1 === x0 ? low : low + (target - x0) / (x1 - x0);
  return indexPosition / (values.length - 1);
}

/** 指针事件 → 画布内的归一化 X 位置；落在绘图区外返回 null。 */
export function pointerFraction(event, element) {
  const geometry = plotGeometry(element);
  const offsetX = event.clientX - geometry.rect.left - geometry.plotLeft;
  if (geometry.plotWidth <= 0 || offsetX < 0 || offsetX > geometry.plotWidth) return null;
  return offsetX / geometry.plotWidth;
}

export function pointerYFraction(event, element) {
  const { rect, height } = plotGeometry(element);
  return height > 0 ? (event.clientY - rect.top) / height : 0.25;
}

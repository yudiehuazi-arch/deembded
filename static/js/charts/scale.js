/** Y 轴范围计算。 */

/** 依据数据自动缩放（5 的整数倍刻度，含 11% 边距）。 */
export function chartScaleFromValues(values) {
  const finiteValues = values.filter(Number.isFinite);
  if (!finiteValues.length) return null;
  let yMin = Math.min(...finiteValues);
  let yMax = Math.max(...finiteValues);
  if (Math.abs(yMax - yMin) < 1) {
    yMax += 1;
    yMin -= 1;
  }
  const margin = (yMax - yMin) * 0.11;
  yMin = Math.floor((yMin - margin) / 5) * 5;
  yMax = Math.ceil((yMax + margin) / 5) * 5;
  if (yMax <= yMin) yMax = yMin + 5;
  return { yMin, yMax };
}

/** 结合用户手填的 Y 轴上下限（留空则自动）。 */
export function chartScaleWithLimits(values, limits = {}) {
  const automatic = chartScaleFromValues(values);
  if (!automatic) return null;
  const yMin = Number.isFinite(limits.min) ? limits.min : automatic.yMin;
  const yMax = Number.isFinite(limits.max) ? limits.max : automatic.yMax;
  return yMax > yMin ? { yMin, yMax } : null;
}

/** 解析 Y 轴输入框：空字符串 → null，非法 → error。 */
export function parseAxisBound(rawValue) {
  const raw = String(rawValue ?? '').trim();
  if (!raw) return { value: null };
  const value = Number(raw);
  return Number.isFinite(value) ? { value } : { error: '请输入有效的有限数值，或留空使用自动范围。' };
}

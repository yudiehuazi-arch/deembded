/** 展示层格式化工具（纯函数，便于单元测试）。 */

import { NETWORK_LABELS, PARAMETER_PATTERN } from '../config/constants.js';

export function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatScientific(value) {
  if (!Number.isFinite(value)) return '—';
  return value === 0 ? '0' : value.toExponential(2);
}

const SIDE_LABELS = { both: '双边去嵌', left: '仅去除左夹具 A', right: '仅去除右夹具 B' };

export function sideLabel(side) {
  return SIDE_LABELS[side] || side;
}

/** 逗号/空格/分号分隔的参数输入 → 去重后的参数代码数组 */
export function splitParameterCodes(value) {
  return [
    ...new Set(
      String(value || '')
        .toUpperCase()
        .split(/[\s,;，；]+/)
        .map((code) => code.trim())
        .filter(Boolean),
    ),
  ];
}

export function isValidParameterCode(code) {
  return PARAMETER_PATTERN.test(code);
}

export function formatAxisValue(value, digits = 3) {
  return Number.isFinite(value) ? value.toFixed(digits) : '—';
}

export function formatPoints(value) {
  return Number(value).toLocaleString('en-US');
}

/**
 * 结果网络的显示名。差分结果带对照算法时，DUT 曲线标注各自的劈半算法，
 * 便于与 PLTS 结果逐条比对。
 */
export function networkLabel(key, calculation = null) {
  if (calculation?.comparison_label) {
    if (key === 'dut' && calculation.split_algorithm_label) return `DUT · ${calculation.split_algorithm_label}`;
    if (key === 'dut_alt') return `DUT · ${calculation.comparison_label}`;
  }
  return NETWORK_LABELS[key] || key;
}

/** 带符号的小数（+0.123 / −0.123），非有限值显示为 “—”。 */
export function formatSigned(value, digits = 3) {
  if (!Number.isFinite(value)) return '—';
  const text = Math.abs(value).toFixed(digits);
  if (Number(text) === 0) return text;
  return `${value > 0 ? '+' : '−'}${text}`;
}

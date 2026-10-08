/** 展示层格式化工具（纯函数，便于单元测试）。 */

import { PARAMETER_PATTERN } from '../config/constants.js';

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

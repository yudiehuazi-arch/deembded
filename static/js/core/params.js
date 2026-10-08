/** S 参数输入解析（输入图表通用）。 */

import { MAX_CHART_PARAMETERS } from '../config/constants.js';
import { splitParameterCodes } from './format.js';

/**
 * 解析用户输入的参数列表。
 * @returns {{codes: string[]}|{error: string}}
 */
export function parseParameterInput(value, availableCodes) {
  const codes = splitParameterCodes(value);
  if (!codes.length) return { error: '请输入至少一个参数，例如 S11。' };
  if (codes.length > MAX_CHART_PARAMETERS) return { error: `每张图最多生成 ${MAX_CHART_PARAMETERS} 条参数曲线。` };
  const invalid = codes.filter((code) => !availableCodes.includes(code));
  if (invalid.length) return { error: `不支持：${invalid.join(', ')}。请检查 S 参数代码。` };
  return { codes };
}

/** 在参数输入框中切换某个参数（返回新文本值）。 */
export function toggleParameterCode(currentValue, code, maxCount = MAX_CHART_PARAMETERS) {
  const codes = splitParameterCodes(currentValue);
  const index = codes.indexOf(code);
  if (index >= 0) {
    codes.splice(index, 1);
    return { value: codes.join(', '), overflow: false };
  }
  if (codes.length >= maxCount) return { value: currentValue, overflow: true };
  codes.push(code);
  return { value: codes.join(', '), overflow: false };
}

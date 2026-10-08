/** Y 轴范围与输入解析测试。 */

import assert from 'node:assert/strict';
import test from 'node:test';

const { chartScaleFromValues, chartScaleWithLimits, parseAxisBound } = await import('../../static/js/charts/scale.js');

test('chartScaleFromValues 自动加边距并取整到 5 的倍数', () => {
  const scale = chartScaleFromValues([-3, -12, -21.5, -35]);
  assert.ok(scale.yMax % 5 === 0 && scale.yMin % 5 === 0);
  assert.ok(Number.isInteger(scale.yMax) && Number.isInteger(scale.yMin));
  assert.ok(scale.yMax > -3 && scale.yMin < -35);
});

test('chartScaleFromValues 处理全平曲线与无数据', () => {
  const flat = chartScaleFromValues([7, 7, 7]);
  assert.ok(flat.yMin < 7 && flat.yMax > 7);
  assert.equal(chartScaleFromValues([NaN, undefined, '']), null);
});

test('chartScaleWithLimits 支持手填上下限', () => {
  const withMin = chartScaleWithLimits([0, -20], { min: -80 });
  assert.equal(withMin.yMin, -80);
  assert.ok(withMin.yMax > 0);
  assert.deepEqual(chartScaleWithLimits([0, -20], { min: 5, max: 10 }), { yMin: 5, yMax: 10 });
  assert.equal(chartScaleWithLimits([0, -20], { min: 10, max: -10 }), null);
});

test('parseAxisBound 区分留空、非法与合法输入', () => {
  assert.deepEqual(parseAxisBound(''), { value: null });
  assert.deepEqual(parseAxisBound('  '), { value: null });
  assert.deepEqual(parseAxisBound('-45.5'), { value: -45.5 });
  assert.ok(parseAxisBound('abc').error);
  assert.ok(parseAxisBound('Infinity').error);
});

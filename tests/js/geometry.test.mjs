/** 画布几何与坐标换算测试。 */

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom, stubRect } from './helpers/dom.js';

installDom();

const { fractionForXValue, indexPositionForFraction, interpolateAt, plotGeometry, pointerFraction, pointerYFraction } =
  await import('../../static/js/charts/geometry.js');
const { CHART_PADDING } = await import('../../static/js/config/constants.js');

test('indexPositionForFraction 映射到索引区间并做限制', () => {
  assert.equal(indexPositionForFraction(11, 0), 0);
  assert.equal(indexPositionForFraction(11, 0.5), 5);
  assert.equal(indexPositionForFraction(11, 1), 10);
  assert.equal(indexPositionForFraction(11, 2), 10);
  assert.equal(indexPositionForFraction(11, -1), 0);
});

test('interpolateAt 支持线性插值与空值', () => {
  assert.equal(interpolateAt([0, 10, 20, 30], 1.5), 15);
  assert.ok(Number.isNaN(interpolateAt([0, 10, null, 30], 1.5)));
  assert.ok(Number.isNaN(interpolateAt([], 0)));
  assert.equal(interpolateAt([5], 0), 5);
});

test('fractionForXValue 定位 X 值并拒绝越界', () => {
  const frequencies = [0, 1, 2, 3, 4];
  assert.equal(fractionForXValue(frequencies, 0), 0);
  assert.equal(fractionForXValue(frequencies, 4), 1);
  assert.equal(fractionForXValue(frequencies, 1), 0.25);
  assert.equal(fractionForXValue(frequencies, 2), 0.5);
  assert.equal(fractionForXValue(frequencies, -1), null);
  assert.equal(fractionForXValue(frequencies, 9), null);
  assert.equal(fractionForXValue([7], 7), 0);
  assert.equal(fractionForXValue([7], 8), null);
});

test('plotGeometry 与 pointer* 基于真实布局计算归一化位置', () => {
  const element = stubRect(document.createElement('canvas'), { width: 400, height: 220, left: 10, top: 20 });
  const geometry = plotGeometry(element);
  assert.equal(geometry.plotLeft, CHART_PADDING.left);
  assert.equal(geometry.plotWidth, 400 - CHART_PADDING.left - CHART_PADDING.right);

  const inside = { clientX: 10 + CHART_PADDING.left + geometry.plotWidth / 2, clientY: 20 + 80 };
  assert.ok(Math.abs(pointerFraction(inside, element) - 0.5) < 1e-9);
  assert.equal(pointerYFraction(inside, element), 80 / 220);
});

test('pointerFraction 在绘图区外返回 null', () => {
  const element = stubRect(document.createElement('canvas'), { width: 400, height: 220, left: 10, top: 20 });
  assert.equal(pointerFraction({ clientX: 5, clientY: 40 }, element), null);
  assert.equal(pointerFraction({ clientX: 5000, clientY: 40 }, element), null);
});

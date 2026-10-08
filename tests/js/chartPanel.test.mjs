/** ChartPanel（画布交互控制器）测试。 */

import assert from 'node:assert/strict';
import test from 'node:test';
import { canvasElement, installDom } from './helpers/dom.js';

installDom(
  `<!doctype html><html><body>
    <div id="wrap">
      <canvas id="canvas"></canvas>
      <span id="marker" hidden></span>
      <span id="marker-label"></span>
      <div id="points"></div>
      <div id="readout" hidden></div>
    </div>
    <input id="x-value">
    <span id="x-unit">GHz</span>
    <input id="y-min"><input id="y-max">
    <button id="y-apply"></button><button id="y-auto"></button><button id="x-locate"></button>
    <p id="status"></p>
  </body></html>`,
);

const { ChartPanel } = await import('../../static/js/charts/chartPanel.js');

const $ = (id) => document.getElementById(id);

function buildPanel(overrides = {}) {
  const canvas = canvasElement();
  $('wrap').appendChild(canvas);
  const panel = new ChartPanel({
    canvas,
    wrap: $('wrap'),
    marker: $('marker'),
    markerLabel: $('marker-label'),
    points: $('points'),
    readout: $('readout'),
    xValueInput: $('x-value'),
    xUnitLabel: $('x-unit'),
    yMinInput: $('y-min'),
    yMaxInput: $('y-max'),
    yApplyButton: $('y-apply'),
    yAutoButton: $('y-auto'),
    xLocateButton: $('x-locate'),
    statusElement: $('status'),
    ...overrides,
  });
  panel.setView({
    xValues: [0, 1, 2, 3],
    xUnit: 'GHz',
    yUnit: 'dB',
    xDecimals: 2,
    traces: [{ values: [-1, -2, -3, -4], color: '#54e1d2', label: 'S21 · DUT 去嵌', dash: [] }],
  });
  return panel;
}

test('draw 按画布尺寸与设备像素比初始化', () => {
  const panel = buildPanel();
  panel.draw();
  const canvas = panel.elements.canvas;
  assert.equal(canvas.width, 400);
  assert.equal(canvas.height, 220);
});

test('positionMarker 定位标记线、数据点与读数', () => {
  const panel = buildPanel();
  panel.draw();
  panel.positionMarker(0.5, 0.5);

  const marker = $('marker');
  assert.equal(marker.hidden, false);
  assert.match(marker.style.left, /px$/);
  assert.equal($('points').children.length, 1);
  assert.equal($('points').children[0].style.backgroundColor, 'rgb(84, 225, 210)');
  assert.equal($('x-value').value, '1.500000');
  assert.match($('marker-label').textContent, /1\.50 GHz/);
});

test('hideMarker 在未固定时隐藏标记并清空散点', () => {
  const panel = buildPanel();
  panel.positionMarker(0.25);
  panel.hideMarker();
  assert.equal($('marker').hidden, true);
  assert.equal($('points').children.length, 0);
  assert.equal(panel.hoverFraction, null);
});

test('pointermove 事件定位标记，pointerleave 收起', () => {
  const panel = buildPanel();
  panel.attachPointer();
  const move = new window.Event('pointermove');
  Object.defineProperty(move, 'clientX', { value: 218 });
  Object.defineProperty(move, 'clientY', { value: 100 });
  $('wrap').dispatchEvent(move);
  assert.equal($('marker').hidden, false);
  assert.ok(panel.hoverFraction > 0.3 && panel.hoverFraction < 0.7);

  $('wrap').dispatchEvent(new window.Event('pointerleave'));
  assert.equal($('marker').hidden, true);
});

test('locateXMarker 校验输入值并给出提示', () => {
  const panel = buildPanel();
  $('x-value').value = '2';
  panel.locateXMarker();
  assert.equal(panel.pinned, true);
  assert.match($('status').textContent, /X 标记线已定位：2\.0000 GHz/);

  $('x-value').value = '9';
  panel.locateXMarker();
  assert.match($('status').textContent, /不在当前显示范围内/);
  assert.ok($('status').classList.contains('is-error'));

  $('x-value').value = 'abc';
  panel.locateXMarker();
  assert.match($('status').textContent, /请输入有效的 X 标记值/);

  $('x-value').value = '';
  panel.locateXMarker();
  assert.equal(panel.pinned, false);
  assert.match($('status').textContent, /已清除/);
});

test('applyYRange 支持手填范围与错误提示，resetYRange 恢复自动', () => {
  const panel = buildPanel();
  $('y-min').value = '-60';
  $('y-max').value = '10';
  panel.applyYRange();
  assert.deepEqual(panel.yLimits, { min: -60, max: 10 });
  assert.match($('status').textContent, /Y 轴范围已应用：-60–10 dB/);

  $('y-min').value = '10';
  $('y-max').value = '0';
  panel.applyYRange();
  assert.match($('status').textContent, /Y 轴最小值必须小于最大值/);

  $('y-min').value = 'abc';
  $('y-max').value = '';
  panel.applyYRange();
  assert.match($('status').textContent, /请输入有效的有限数值/);

  panel.resetYRange();
  assert.deepEqual(panel.yLimits, { min: null, max: null });
  assert.equal($('y-min').value, '');
  assert.match($('status').textContent, /自动缩放/);
});

test('轴控件按钮绑定到对应动作', () => {
  const panel = buildPanel();
  panel.attachAxisControls();
  $('y-min').value = '-30';
  $('y-apply').click();
  assert.deepEqual(panel.yLimits, { min: -30, max: null });
  $('y-auto').click();
  assert.deepEqual(panel.yLimits, { min: null, max: null });

  $('x-value').value = '3';
  $('x-locate').click();
  assert.equal(panel.pinned, true);
});

test('shutdown 复位视图与轴控件', () => {
  const panel = buildPanel();
  $('y-min').value = '-30';
  $('x-value').value = '1';
  panel.applyYRange();
  panel.shutdown();
  assert.deepEqual(panel.yLimits, { min: null, max: null });
  assert.deepEqual(panel.view.traces, []);
  assert.equal($('marker').hidden, true);
});

/** 曲线构造（结果 / 输入 / TDR）测试。 */

import assert from 'node:assert/strict';
import test from 'node:test';

const { buildResultSparamTraces, buildResultTdrTraces, buildInputSparamDisplay, buildInputTdrTraces } = await import(
  '../../static/js/charts/series.js'
);
const { MAX_CHART_PARAMETERS, NETWORK_DOT_COLORS, PARAMETER_COLORS } = await import('../../static/js/config/constants.js');

const calculation = {
  chart: {
    series: {
      S21: { total: [-1.15, -5.06, -3.06], dut: [-1.0, -4.0, -2.0] },
      SDD21: { dut: [-1.2, -4.2, -2.2] },
    },
  },
};

test('buildResultSparamTraces 为每个参数×网络生成曲线并突出 DUT', () => {
  const traces = buildResultSparamTraces(calculation, ['S21'], ['total', 'dut']);
  assert.deepEqual(
    traces.map((trace) => trace.label),
    ['S21 · Total', 'S21 · DUT 去嵌'],
  );
  const [total, dut] = traces;
  assert.equal(total.width, 1.45);
  assert.ok(dut.width > total.width);
  assert.deepEqual(dut.values, [-1.0, -4.0, -2.0]);
  assert.equal(total.color, PARAMETER_COLORS[0]);
});

test('buildResultSparamTraces 跳过缺失数据并按参数换色', () => {
  const traces = buildResultSparamTraces(calculation, ['S21', 'SDD21'], ['total', 'dut']);
  assert.deepEqual(
    traces.map((trace) => `${trace.parameter}/${trace.networkKey}`),
    ['S21/total', 'S21/dut', 'SDD21/dut'],
  );
  assert.equal(traces[0].color, PARAMETER_COLORS[0]);
  assert.equal(traces[2].color, PARAMETER_COLORS[1]);
});

test('buildResultTdrTraces 带上网络标签与参考参数', () => {
  const traces = buildResultTdrTraces({ series: { dut: [50, 60], total: [50, 55] } }, ['dut', 'total'], 'SDD11');
  assert.deepEqual(
    traces.map((trace) => trace.label),
    ['DUT 去嵌 · SDD11', 'Total · SDD11'],
  );
  assert.equal(traces[0].color, NETWORK_DOT_COLORS.dut);
});

test('buildInputTdrTraces 按 A/Total/B 固定顺序输出', () => {
  const traces = buildInputTdrTraces({ series: { thru_b: [1], total: [2], thru_a: [3] } }, 'S11');
  assert.deepEqual(
    traces.map((trace) => trace.key),
    ['thru_a', 'total', 'thru_b'],
  );
  assert.equal(traces[1].label, 'Total · S11');
});

test('buildInputSparamDisplay 在重叠频段重采样并合并曲线', () => {
  const items = [
    { slot: 'thru_a', label: 'A', codes: ['S21'], preview: { freq_ghz: [0, 1, 2, 3], series: { S21: [0, -1, -2, -3] } } },
    { slot: 'total', label: 'Total', codes: ['S21'], preview: { freq_ghz: [1, 2, 3, 4], series: { S21: [-4, -5, -6, -7] } } },
  ];
  const display = buildInputSparamDisplay(items);
  assert.equal(display.freq_ghz[0], 1);
  assert.equal(display.freq_ghz.at(-1), 3);
  assert.deepEqual(
    display.traces.map((trace) => trace.slot),
    ['thru_a', 'total'],
  );
  assert.ok(Math.abs(display.traces[0].values[0] - -1) < 1e-9);
});

test('buildInputSparamDisplay 限制曲线总数', () => {
  const many = Array.from({ length: MAX_CHART_PARAMETERS }, (_, index) => `S${index % 2 ? 21 : 12}`);
  const items = ['thru_a', 'total', 'thru_b'].map((slot) => ({
    slot,
    label: slot,
    codes: many,
    preview: { freq_ghz: [0, 1, 2], series: Object.fromEntries(many.map((code) => [code, [0, -1, -2]])) },
  }));
  const display = buildInputSparamDisplay(items);
  assert.equal(display.traces.length, MAX_CHART_PARAMETERS * 3);
});

test('buildInputSparamDisplay 对无重叠频段与空输入返回 null', () => {
  const disjoint = [
    { slot: 'thru_a', label: 'A', codes: ['S21'], preview: { freq_ghz: [0, 1], series: { S21: [0, 0] } } },
    { slot: 'total', label: 'T', codes: ['S21'], preview: { freq_ghz: [5, 6], series: { S21: [0, 0] } } },
  ];
  assert.equal(buildInputSparamDisplay(disjoint), null);
  assert.equal(buildInputSparamDisplay([]), null);
});

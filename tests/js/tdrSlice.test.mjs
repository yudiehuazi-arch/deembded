/** TDR 显示窗裁剪测试。 */

import assert from 'node:assert/strict';
import test from 'node:test';

const { sliceTdrDisplay } = await import('../../static/js/charts/tdrSlice.js');

const payload = {
  time_ns: [0, 1, 2, 3, 4, 5],
  series: { input: [50, 51, 52, 53, 54, 55], dut: [50, 50, 60, 70, 80, 90] },
};

test('sliceTdrDisplay 裁剪时间窗并保留全部曲线', () => {
  const display = sliceTdrDisplay(payload, { startNs: '1', endNs: '3' });
  assert.deepEqual(display.time_ns, [1, 2, 3]);
  assert.deepEqual(display.series.input, [51, 52, 53]);
  assert.deepEqual(display.series.dut, [50, 60, 70]);
});

test('sliceTdrDisplay 缺省使用全窗，并限制显示点数', () => {
  assert.deepEqual(sliceTdrDisplay(payload, {}).time_ns, [0, 1, 2, 3, 4, 5]);
  const limited = sliceTdrDisplay(payload, { pointLimit: 3 });
  assert.equal(limited.time_ns.length, 3);
  assert.equal(limited.series.input.length, 3);
  assert.equal(limited.time_ns[0], 0);
  assert.equal(limited.time_ns.at(-1), 5);
});

test('sliceTdrDisplay 处理空数据与倒置时间窗', () => {
  assert.deepEqual(sliceTdrDisplay(null, {}), { time_ns: [], series: {} });
  assert.deepEqual(sliceTdrDisplay(payload, { startNs: '4', endNs: '1' }).time_ns, []);
});

test('sliceTdrDisplay 兼容单槽 impedance_ohm 结构', () => {
  const single = sliceTdrDisplay({ time_ns: [0, 1], impedance_ohm: [50, 60] }, {});
  assert.deepEqual(single.series.input, [50, 60]);
});

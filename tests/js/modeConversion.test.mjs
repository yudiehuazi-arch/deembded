/** 差分模式转换诊断：解读文案、网络标签与对照曲线的默认勾选。 */

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './helpers/dom.js';

installDom();

const { describeModeConversion, formatSkew, ModeConversionPanel, NEGLIGIBLE_DELTA_DB } = await import(
  '../../static/js/ui/modeConversionPanel.js'
);
const { networkLabel, formatSigned } = await import('../../static/js/core/format.js');
const { availableNetworkKeys, defaultNetworkChecked } = await import('../../static/js/ui/resultSummary.js');

const significant = {
  thru_a: { skew_ps: 2.86, max_conversion_db: -5.1 },
  thru_b: { skew_ps: 1.9, max_conversion_db: -8.4 },
  dut: { skew_ps: 1.45, max_conversion_db: -10.6 },
  comparison: {
    primary: 'mc_nzc',
    primary_label: '混合模 NZC + 模式转换',
    alternative: 'classic_nzc',
    alternative_label: 'IEEE 370 经典 MM-NZC',
    max_delta_db: 1.5694,
    max_delta_ghz: 67,
    checkpoints: [
      { freq_ghz: 16.8, delta_db: 0.081 },
      { freq_ghz: 67, delta_db: 1.569 },
    ],
  },
};

test('formatSigned / formatSkew 输出带符号的文案', () => {
  assert.equal(formatSigned(0.1234), '+0.123');
  assert.equal(formatSigned(-0.1234, 2), '−0.12');
  assert.equal(formatSigned(0.0001), '0.000');
  assert.equal(formatSigned(Number.NaN), '—');
  assert.equal(formatSkew(2.857), '+2.86 ps（P 线较长）');
  assert.equal(formatSkew(-0.5), '−0.50 ps（N 线较长）');
  assert.equal(formatSkew(0), '≈ 0 ps');
  assert.equal(formatSkew(null), '—');
});

test('describeModeConversion：差异可忽略时提示检查 PLTS 其它设置', () => {
  const result = describeModeConversion({
    thru_a: { skew_ps: 0, max_conversion_db: -200 },
    thru_b: { skew_ps: 0, max_conversion_db: -200 },
    dut: { skew_ps: 0, max_conversion_db: -200 },
    comparison: { ...significant.comparison, max_delta_db: 0.01 },
  });
  assert.equal(result.level, 'info');
  assert.equal(result.messages.length, 1);
  assert.match(result.messages[0], new RegExp(`< ${NEGLIGIBLE_DELTA_DB} dB`));
  assert.match(result.messages[0], /Deskew/);
});

test('describeModeConversion：模式转换显著时给出方向与 skew 提示', () => {
  const result = describeModeConversion(significant, { primaryAlgorithm: 'mc_nzc' });
  assert.equal(result.level, 'warn');
  assert.match(result.messages[0], /1\.57 dB/);
  assert.match(result.messages[0], /经典 MM-NZC 结果在该处偏低/);
  assert.ok(result.messages.some((message) => /同向/.test(message)));
  assert.ok(result.messages.some((message) => /DUT 自身约有 1\.45 ps/.test(message)));

  // 主算法为经典时，差值符号相反，但物理结论（经典偏低）不变
  const reversed = describeModeConversion(
    { ...significant, comparison: { ...significant.comparison, max_delta_db: -1.5694 } },
    { primaryAlgorithm: 'classic_nzc' },
  );
  assert.match(reversed.messages[0], /经典 MM-NZC 结果在该处偏低/);
  assert.equal(describeModeConversion(null).messages.length, 0);
});

test('networkLabel 在有对照算法时标注各自算法', () => {
  const calculation = { split_algorithm_label: '混合模 NZC + 模式转换', comparison_label: 'IEEE 370 经典 MM-NZC' };
  assert.equal(networkLabel('dut', calculation), 'DUT · 混合模 NZC + 模式转换');
  assert.equal(networkLabel('dut_alt', calculation), 'DUT · IEEE 370 经典 MM-NZC');
  assert.equal(networkLabel('total', calculation), 'Total');
  assert.equal(networkLabel('dut'), 'DUT 去嵌');
  assert.equal(networkLabel('mystery'), 'mystery');
});

test('对照曲线仅在两种算法差异明显时默认勾选', () => {
  const calc = (delta) => ({ diagnostics: { comparison: { max_delta_db: delta } } });
  assert.equal(defaultNetworkChecked('dut_alt', calc(0.01)), false);
  assert.equal(defaultNetworkChecked('dut_alt', calc(-0.5)), true);
  assert.equal(defaultNetworkChecked('dut_alt', null), false);
  assert.equal(defaultNetworkChecked('dut', calc(0)), true);
  assert.equal(defaultNetworkChecked('fix_a', calc(1)), false);

  assert.deepEqual(availableNetworkKeys({ chart: { network_keys: ['total', 'dut'] } }), ['total', 'dut']);
  assert.deepEqual(availableNetworkKeys({ chart: { series: { SDD21: { total: [], dut_alt: [] }, S11: { dut: [] } } } }), [
    'total',
    'dut_alt',
    'dut',
  ]);
});

test('ModeConversionPanel 渲染诊断卡片，单端时隐藏', () => {
  document.body.innerHTML = `
    <section id="mc-diagnostics" hidden>
      <small id="mc-diagnostics-note"></small>
      <dl id="mc-diag-thru-a"></dl><dl id="mc-diag-thru-b"></dl><dl id="mc-diag-dut"></dl>
      <h5 id="mc-diag-compare-title"></h5><dl id="mc-diag-compare"></dl>
      <div id="mc-diagnostics-hint" hidden></div>
    </section>`;
  const panel = new ModeConversionPanel();
  panel.render({
    nports: 4,
    split_algorithm: 'mc_nzc',
    split_algorithm_label: '混合模 NZC + 模式转换',
    comparison_label: 'IEEE 370 经典 MM-NZC',
    diagnostics: significant,
  });
  const root = document.getElementById('mc-diagnostics');
  assert.equal(root.hidden, false);
  assert.match(document.getElementById('mc-diag-thru-a').textContent, /\+2\.86 ps/);
  assert.match(document.getElementById('mc-diag-thru-a').textContent, /每个 1X 夹具\+1\.43 ps/);
  assert.match(document.getElementById('mc-diag-compare-title').textContent, /ΔSDD21 = 混合模 NZC \+ 模式转换 − IEEE 370 经典 MM-NZC/);
  assert.match(document.getElementById('mc-diag-compare').textContent, /\+1\.569 dB @ 67\.00 GHz/);
  const hint = document.getElementById('mc-diagnostics-hint');
  assert.equal(hint.hidden, false);
  assert.ok(hint.classList.contains('is-warn'));

  panel.render({ nports: 2, diagnostics: null });
  assert.equal(root.hidden, true);
});

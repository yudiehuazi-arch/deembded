/**
 * Workbench 集成测试：用真实 static/index.html + 真实接口响应样本驱动完整流程。
 *
 * 覆盖：选择文件 → 识别端口映射 → 去嵌 → 参数/图例联动 → 结果 TDR →
 * 输入组合图与输入 TDR → 缓存过期重传 → 重置。
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileStub, flush, installAppDom, stubFetch } from './helpers/dom.js';

const { DeembedApi } = await import('../../static/js/core/api.js');
const { Workbench } = await import('../../static/js/workbench.js');

const fixtures = {
  inspect: JSON.parse(readFileSync(new URL('./fixtures/inspect.json', import.meta.url), 'utf8')),
  deembed: JSON.parse(readFileSync(new URL('./fixtures/deembed.json', import.meta.url), 'utf8')),
  tdrInput: JSON.parse(readFileSync(new URL('./fixtures/tdr_input.json', import.meta.url), 'utf8')),
  tdrResult: JSON.parse(readFileSync(new URL('./fixtures/tdr_result.json', import.meta.url), 'utf8')),
};

const $ = (id) => document.getElementById(id);

/** 建立一套全新的应用实例（真实 index.html + 桩 fetch）。 */
function setup(routes = {}) {
  installAppDom();
  const stub = stubFetch({
    inspect: routes.inspect ?? fixtures.inspect,
    deembed: routes.deembed ?? fixtures.deembed,
    tdrInput: routes.tdrInput ?? fixtures.tdrInput,
    tdrResult: routes.tdrResult ?? fixtures.tdrResult,
  });
  const workbench = new Workbench({ api: new DeembedApi({ fetchImpl: stub.fetchImpl }) });
  workbench.mount();
  return { workbench, calls: stub.calls };
}

function selectThreeFiles(workbench) {
  workbench.uploads.selectFile('total', fileStub('total.s4p'));
  workbench.uploads.selectFile('thru_a', fileStub('thru_a.s4p'));
  workbench.uploads.selectFile('thru_b', fileStub('thru_b.s4p'));
}

function change(id, value) {
  const element = $(id);
  element.value = value;
  element.dispatchEvent(new window.Event('change'));
}

async function runDeembed(workbench) {
  $('btn-run').click();
  await flush();
}

test('选择三个文件后识别端口映射、渲染夹具诊断与快捷参数', async () => {
  const { workbench, calls } = setup();
  selectThreeFiles(workbench);
  await flush();

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/inspect');
  assert.ok(calls[0].form.get('total'));
  assert.equal(calls[0].form.get('port_mapping'), 'auto');

  assert.equal($('status-title').textContent, '三个文件已识别');
  assert.equal($('status-tag').textContent, 'READY');
  assert.match($('status-detail').textContent, /差分 S4P/);
  assert.equal($('map-a-outer').textContent, 'P1 (+) / P2 (−)');
  assert.equal($('map-a-split').textContent, 'P3 (+) / P4 (−)');
  assert.match($('map-note-a').textContent, /外部端 P1 \(\+\) \/ P2 \(−\)/);

  assert.equal($('input-param-thru-a').value, 'SDD21');
  assert.equal($('input-param-total').value, 'SDD21');
  const chips = [...$('quick-params-thru-a').querySelectorAll('.quick-param-chip')].map((chip) => chip.textContent);
  assert.ok(chips.includes('SDD21'));
  assert.ok(chips.includes('S11'));

  assert.equal($('fixture-stats').hidden, false);
  assert.equal($('fixture-stat-rows-a').children.length, 4);
});

test('运行去嵌后渲染指标、下载链接与图例，并校验参数输入', async () => {
  const { workbench, calls } = setup();
  selectThreeFiles(workbench);
  await flush();
  await runDeembed(workbench);

  const deembedCall = calls.find((call) => call.url === '/api/deembed');
  assert.ok(deembedCall, '应调用 /api/deembed');
  assert.equal(deembedCall.form.get('inspection_token'), fixtures.inspect.inspection_token);
  assert.equal(deembedCall.form.get('side'), 'both');
  assert.equal(deembedCall.form.get('reference_z0'), '50');

  assert.equal($('status-title').textContent, '去嵌完成');
  assert.equal($('status-tag').textContent, 'DONE');
  assert.equal($('result-panel').hidden, false);
  assert.equal($('metric-topology').textContent, '差分 S4P');
  assert.match($('metric-frequency').textContent, /GHz/);
  assert.match($('metric-points').textContent, /Z₀ 50 Ω/);
  assert.equal($('chart-params').value, 'SDD21');

  assert.equal($('download-dut').getAttribute('download'), 'DUT_deembedded.s4p');
  assert.match($('download-dut').getAttribute('href'), /^\/api\/download\/.+\/dut$/);
  assert.equal($('download-a').getAttribute('download'), 'Fixture_A_1X.s4p');

  // 默认勾选 Total + DUT 两个网络 → SDD21 两条曲线
  assert.equal($('chart-legend').children.length, 2);

  // 再叠加一个参数 → 四条曲线
  change('chart-params', 'SDD21, S11');
  $('btn-plot-params').click();
  assert.equal($('chart-legend').children.length, 4);
  assert.equal($('chart-param-error').textContent, '');

  // 参数不存在
  change('chart-params', 'S99');
  $('btn-plot-params').click();
  assert.match($('chart-param-error').textContent, /无法识别：S99/);
  assert.equal($('chart-params').getAttribute('aria-invalid'), 'true');

  // 空输入
  change('chart-params', '');
  $('btn-plot-params').click();
  assert.match($('chart-param-error').textContent, /请输入至少一个 S 参数/);

  // 快捷芯片追加参数（默认参数 SDD21 会被替换而不是拼接）
  change('chart-params', 'S11');
  $('btn-plot-params').click();
  const chip = [...$('param-chips').querySelectorAll('.param-chip')].find((item) => item.textContent === 'SCD21');
  assert.ok(chip, '参数建议芯片应包含 SCD21');
  chip.click();
  assert.equal($('chart-params').value, 'S11, SCD21');
  assert.equal($('chart-legend').children.length, 4);
});

test('差分劈半算法：默认含模式转换，切换后提示重算并随请求发送；诊断面板与对照下载可用', async () => {
  const { workbench, calls } = setup();
  selectThreeFiles(workbench);
  await flush();
  assert.equal($('split-algorithm-select').value, 'mc_nzc');
  assert.equal($('split-algorithm-select').disabled, false);
  await runDeembed(workbench);

  const first = calls.filter((call) => call.url === '/api/deembed').at(-1);
  assert.equal(first.form.get('split_algorithm'), 'mc_nzc');
  assert.match($('result-summary').textContent, /混合模 NZC \+ 模式转换/);

  // 诊断面板（示例数据无模式转换 → 差异可忽略的提示）
  assert.equal($('mc-diagnostics').hidden, false);
  assert.match($('mc-diag-thru-a').textContent, /P\/N skew/);
  assert.match($('mc-diagnostics-hint').textContent, /差异 < 0\.05 dB/);

  // 对照算法：下载按钮与网络开关（差异可忽略时默认不勾选）
  assert.equal($('download-alt').hidden, false);
  assert.equal($('download-alt').getAttribute('download'), 'DUT_deembedded_classic_nzc.s4p');
  assert.match($('download-alt').getAttribute('href'), /\/dut_alt$/);
  const altToggle = document.querySelector('#network-toggles input[data-network="dut_alt"]');
  assert.ok(altToggle, '应提供对照算法曲线开关');
  assert.equal(altToggle.checked, false);
  assert.match(altToggle.parentElement.textContent, /DUT · IEEE 370 经典 MM-NZC/);
  altToggle.checked = true;
  altToggle.dispatchEvent(new window.Event('change'));
  assert.equal($('chart-legend').children.length, 3);

  change('split-algorithm-select', 'classic_nzc');
  assert.equal($('status-tag').textContent, 'RE-RUN');
  await runDeembed(workbench);
  const second = calls.filter((call) => call.url === '/api/deembed').at(-1);
  assert.equal(second.form.get('split_algorithm'), 'classic_nzc');
});

test('结果 TDR 视图请求后端、刷新状态与图例', async () => {
  const { workbench, calls } = setup({
    tdrResult: ({ form }) => ({ ...fixtures.tdrResult, parameter: form.get('port') === '2' ? 'SDD22' : 'SDD11' }),
  });
  selectThreeFiles(workbench);
  await flush();
  await runDeembed(workbench);

  change('result-chart-view', 'tdr');
  await flush();

  const tdrCall = calls.find((call) => call.url === '/api/tdr/result');
  assert.ok(tdrCall, '应调用 /api/tdr/result');
  assert.equal(tdrCall.form.get('inspection_token'), fixtures.inspect.inspection_token);
  assert.equal(tdrCall.form.get('result_token'), fixtures.deembed.result_token);
  assert.equal(tdrCall.form.get('port'), '1');

  assert.equal($('chart-sparam-controls').hidden, true);
  assert.equal($('result-tdr-controls').hidden, false);
  assert.equal($('chart-y-label').textContent, '阻抗 (Ω)');
  assert.equal($('chart-frequency-label').textContent, '时间 (ns)');
  assert.match($('result-tdr-status').textContent, /SDD11/);
  assert.match($('result-tdr-status').textContent, /差分参考阻抗 100 Ω/);
  assert.equal($('chart-legend').children.length, 2);
  assert.match($('result-chart-subtitle').textContent, /阶跃阻抗/);

  // 切换到差分端口 2 → SDD22
  change('result-tdr-port', '2');
  await flush();
  assert.match($('result-tdr-status').textContent, /SDD22/);

  // 回到频域视图
  change('result-chart-view', 'sparam');
  await flush();
  assert.equal($('chart-sparam-controls').hidden, false);
  assert.equal($('chart-legend').children.length, 2);
});

test('输入组合图与输入 TDR 复用识别缓存', async () => {
  const { workbench, calls } = setup();
  selectThreeFiles(workbench);
  await flush();

  $('btn-generate-input-chart').click();
  await flush();

  assert.equal($('input-chart-panel').hidden, false);
  assert.match($('input-chart-title').textContent, /S 参数对比/);
  assert.equal($('input-chart-legend').children.length, 3);
  assert.match($('input-chart-subtitle').textContent, /total\.s4p/);
  assert.equal($('input-param-thru-a').getAttribute('aria-invalid'), 'false');
  assert.match($('param-note-thru-a').textContent, /已加入组合图/);

  change('input-chart-view', 'tdr');
  await flush();

  const tdrCall = calls.find((call) => call.url === '/api/tdr/input');
  assert.ok(tdrCall, '应调用 /api/tdr/input');
  assert.equal(tdrCall.form.get('slot'), 'all');
  assert.equal($('input-tdr-controls').hidden, false);
  assert.match($('input-tdr-status').textContent, /SDD11/);
  assert.match($('input-tdr-status').textContent, /A \+ Total \+ B/);
  assert.equal($('input-chart-legend').children.length, 3);

  // 关闭面板
  $('btn-close-input-chart').click();
  assert.equal($('input-chart-panel').hidden, true);
});

test('识别缓存过期（410）时自动带文件重传', async () => {
  const expired = { __status: 410, detail: '文件识别缓存已过期或输入文件缺失，请重新选择三个文件。' };
  const queue = [fixtures.inspect, expired, fixtures.inspect];
  const { workbench, calls } = setup({ inspect: () => queue.shift() ?? fixtures.inspect });

  selectThreeFiles(workbench);
  await flush();
  assert.equal(calls.length, 1);

  // 再次触发识别（模拟切换端口映射），第一次返回 410，随后应用自动重传文件
  await workbench.inspectSelectedFiles();
  await flush();

  const inspectCalls = calls.filter((call) => call.url === '/api/inspect');
  assert.equal(inspectCalls.length, 3);
  assert.equal(inspectCalls[1].form.get('inspection_token'), fixtures.inspect.inspection_token);
  assert.equal(inspectCalls[2].form.get('total'), null === null ? inspectCalls[2].form.get('total') : null);
  assert.ok(inspectCalls[2].form.get('total'), '重传请求必须携带三个文件');
  assert.equal(inspectCalls[2].form.get('inspection_token'), null);
  assert.equal($('status-title').textContent, '三个文件已识别');
});

test('识别失败时展示错误并提示重新选择文件', async () => {
  const { workbench } = setup({ inspect: { __status: 400, detail: 'S4P 端口映射设置无效。' } });
  selectThreeFiles(workbench);
  await flush();
  assert.equal($('status-title').textContent, '文件识别失败');
  assert.equal($('status-tag').textContent, 'ERROR');
  assert.match($('status-detail').textContent, /S4P 端口映射设置无效/);
  assert.match($('map-note-a').textContent, /识别失败/);
});

test('重置清空文件、面板与状态', async () => {
  const { workbench } = setup();
  selectThreeFiles(workbench);
  await flush();
  await runDeembed(workbench);
  assert.equal($('result-panel').hidden, false);

  $('btn-clear').click();
  await flush();

  assert.equal($('result-panel').hidden, true);
  assert.equal($('file-tools').hidden, true);
  assert.equal($('input-chart-panel').hidden, true);
  assert.equal($('status-title').textContent, '等待输入文件');
  assert.equal($('status-tag').textContent, 'READY');
  assert.equal($('status-thru-a').textContent.trim(), '尚未选择文件');
  assert.equal($('chart-legend').children.length, 0);
  assert.equal($('mc-diagnostics').hidden, true);
  assert.equal(workbench.state.files.total, null);
});

test('去嵌失败（无结果）时给出错误状态', async () => {
  const { workbench } = setup({ deembed: { __status: 500, detail: '内部计算失败。' } });
  selectThreeFiles(workbench);
  await flush();
  await runDeembed(workbench);

  assert.equal($('status-title').textContent, '计算失败');
  assert.match($('status-detail').textContent, /内部计算失败/);
  assert.equal($('result-panel').hidden, true);
  assert.equal($('btn-run').disabled, false, '失败后按钮必须恢复可用');
});

test('参考阻抗非法时阻止请求', async () => {
  const { workbench, calls } = setup();
  selectThreeFiles(workbench);
  await flush();
  change('z0-input', 'abc');
  await runDeembed(workbench);

  assert.equal($('status-title').textContent, '参考阻抗无效');
  assert.ok(!calls.some((call) => call.url === '/api/deembed'));
});

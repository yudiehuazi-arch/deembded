/** 入口装配测试：main.js 引导后暴露 window.rfDeembed.workbench，并完成事件绑定。 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { flush, installAppDom, stubFetch } from './helpers/dom.js';

const fixtures = {
  inspect: JSON.parse(readFileSync(new URL('./fixtures/inspect.json', import.meta.url), 'utf8')),
};

const dom = installAppDom();
const stub = stubFetch(fixtures);
dom.window.fetch = stub.fetchImpl;

await import('../../static/js/main.js');
await flush();

test('main.js 引导后暴露 workbench 实例并归位初始状态', () => {
  assert.ok(dom.window.rfDeembed?.workbench, '应挂载到 window.rfDeembed.workbench');
  assert.equal(typeof dom.window.rfDeembed.workbench.runDeembed, 'function');
  assert.equal(dom.window.document.getElementById('status-tag').textContent, 'READY');
  assert.equal(dom.window.document.getElementById('result-panel').hidden, true);
});

test('引导后的界面绑定可用：缺少文件时给出提示', async () => {
  dom.window.document.getElementById('btn-run').click();
  await flush();
  assert.equal(dom.window.document.getElementById('status-title').textContent, '还缺少输入文件');
  assert.equal(stub.calls.filter((call) => call.url === '/api/deembed').length, 0);
});

test('控制器基类强制子类实现 buildView', async () => {
  const { ChartFlowController } = await import('../../static/js/controllers/chartFlowController.js');
  const chartStub = {
    pinned: false,
    resetAxisControls() {},
    hideMarker() {},
    clearXValue() {},
    setView() {},
    draw() {},
  };
  const controller = new ChartFlowController({ chart: chartStub, legend: null, tdrControls: null });
  assert.throws(() => controller.buildView(), /必须实现 buildView/);
  assert.equal(controller.mode, 'sparam');
  assert.equal(controller.isTdr, false);
  controller.setView('tdr');
  assert.equal(controller.isTdr, true);
  assert.equal(controller.tdrRequestId, 1, '切换模式应使在途 TDR 请求失效');
});

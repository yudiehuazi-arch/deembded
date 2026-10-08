/** API 客户端测试：表单字段、错误语义与下载链接。 */

import assert from 'node:assert/strict';
import test from 'node:test';

const { ApiError, DeembedApi } = await import('../../static/js/core/api.js');

const file = (name) => new Blob([name], { type: 'text/plain' });

function jsonResponse(payload, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

function recorder(payloads) {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, form: options.body });
    const payload = payloads.shift() ?? {};
    return jsonResponse(payload, payload.__status ?? 200);
  };
  return { calls, fetchImpl };
}

test('inspect 上传三个文件并附带端口映射', async () => {
  const { calls, fetchImpl } = recorder([{ success: true, inspection_token: 'tok' }]);
  const api = new DeembedApi({ fetchImpl });
  const data = await api.inspect({
    files: { total: file('total.s4p'), thru_a: file('a.s4p'), thru_b: file('b.s4p') },
    portMapping: 'plts',
  });
  assert.equal(data.inspection_token, 'tok');
  assert.equal(calls[0].url, '/api/inspect');
  const form = calls[0].form;
  assert.equal(form.get('port_mapping'), 'plts');
  assert.ok(form.get('total'));
  assert.ok(form.get('thru_a'));
  assert.ok(form.get('thru_b'));
  assert.equal(form.get('inspection_token'), null);
});

test('inspect 复用缓存 token 时不再上传文件', async () => {
  const { calls, fetchImpl } = recorder([{ success: true }]);
  const api = new DeembedApi({ fetchImpl });
  await api.inspect({ files: null, token: 'cached-token' });
  assert.equal(calls[0].form.get('inspection_token'), 'cached-token');
  assert.equal(calls[0].form.get('total'), null);
});

test('inspect 失败时抛出带状态码的 ApiError', async () => {
  const { fetchImpl } = recorder([{ __status: 400, detail: '文件为空。' }]);
  const api = new DeembedApi({ fetchImpl });
  await assert.rejects(api.inspect({ files: null, token: 't' }), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 400);
    assert.equal(error.message, '文件为空。');
    return true;
  });
});

test('deembed 支持 token 与文件两种入口，并校验 success 标志', async () => {
  const { calls, fetchImpl } = recorder([{ result_token: 'r1' }, { success: false, detail: '计算失败。' }]);
  const api = new DeembedApi({ fetchImpl });

  await api.deembed({ token: 'inspection-token', side: 'left', portMapping: 'auto', referenceZ0: 75 });
  const form = calls[0].form;
  assert.equal(form.get('inspection_token'), 'inspection-token');
  assert.equal(form.get('side'), 'left');
  assert.equal(form.get('port_mapping'), 'auto');
  assert.equal(form.get('reference_z0'), '75');

  await assert.rejects(api.deembed({ token: 'x' }), /计算失败。/);
});

test('TDR 请求携带端口、窗函数与 DC 外推设置', async () => {
  const { calls, fetchImpl } = recorder([{ parameter: 'SDD11' }, { parameter: 'SDD11' }]);
  const api = new DeembedApi({ fetchImpl });
  const settings = { port: '1', portMapping: 'auto', referenceZ0: 50, window: 'hamming', dcMethod: 'linear', riseTimePs: '0' };

  await api.tdrInput({ inspectionToken: 'inspection', ...settings });
  assert.equal(calls[0].url, '/api/tdr/input');
  assert.equal(calls[0].form.get('slot'), 'all');
  assert.equal(calls[0].form.get('window'), 'hamming');

  await api.tdrResult({ inspectionToken: 'inspection', resultToken: 'result', ...settings });
  assert.equal(calls[1].url, '/api/tdr/result');
  assert.equal(calls[1].form.get('result_token'), 'result');
});

test('downloadUrl 对 token 做 URL 编码', () => {
  const api = new DeembedApi({ fetchImpl: async () => jsonResponse({}) });
  assert.equal(api.downloadUrl('a/b c', 'dut'), '/api/download/a%2Fb%20c/dut');
});

test('响应体不是 JSON 时回退为 HTTP 状态文案', async () => {
  const fetchImpl = async () => ({
    ok: false,
    status: 500,
    json: async () => {
      throw new Error('not json');
    },
  });
  const api = new DeembedApi({ fetchImpl });
  await assert.rejects(api.inspect({ files: null, token: 't' }), /HTTP 500/);
});

/** 核心工具：格式化、参数解析、快捷参数存储与应用状态。 */

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './helpers/dom.js';

installDom();

const { formatSize, formatScientific, splitParameterCodes, isValidParameterCode, sideLabel, formatAxisValue, formatPoints } =
  await import('../../static/js/core/format.js');
const { parseParameterInput, toggleParameterCode } = await import('../../static/js/core/params.js');
const { QuickParameterStore } = await import('../../static/js/core/storage.js');
const { WorkbenchState } = await import('../../static/js/core/state.js');
const { MAX_QUICK_PARAMETERS } = await import('../../static/js/config/constants.js');

test('formatSize 在 KB / MB 之间切换', () => {
  assert.equal(formatSize(512), '0.5 KB');
  assert.equal(formatSize(2048), '2.0 KB');
  assert.equal(formatSize(3 * 1024 * 1024), '3.00 MB');
});

test('formatScientific / formatAxisValue / formatPoints 输出稳定文案', () => {
  assert.equal(formatScientific(0), '0');
  assert.equal(formatScientific(Number.NaN), '—');
  assert.equal(formatScientific(1.23e-6), '1.23e-6');
  assert.equal(formatAxisValue(1.23456), '1.235');
  assert.equal(formatAxisValue(Number.NaN), '—');
  assert.equal(formatPoints(12345), '12,345');
  assert.equal(sideLabel('both'), '双边去嵌');
  assert.equal(sideLabel('left'), '仅去除左夹具 A');
  assert.equal(sideLabel('right'), '仅去除右夹具 B');
  assert.equal(sideLabel('unknown'), 'unknown');
});

test('splitParameterCodes 规范化大小写与分隔符', () => {
  assert.deepEqual(splitParameterCodes('s21, s11 ，SDD21'), ['S21', 'S11', 'SDD21']);
  assert.deepEqual(splitParameterCodes('S21 s11;S12'), ['S21', 'S11', 'S12']);
  assert.deepEqual(splitParameterCodes(''), []);
});

test('isValidParameterCode 只接受 Sij 与混合模代码', () => {
  assert.ok(isValidParameterCode('S21'));
  assert.ok(isValidParameterCode('S44'));
  assert.ok(isValidParameterCode('SDD21'));
  assert.ok(isValidParameterCode('SCD12'));
  assert.ok(!isValidParameterCode('S55'));
  assert.ok(!isValidParameterCode('XYZ'));
  assert.ok(!isValidParameterCode('SDD31'));
});

test('parseParameterInput 校验数量与可用性', () => {
  const available = ['S11', 'S21', 'S12', 'S22'];
  assert.deepEqual(parseParameterInput('S21, S11', available), { codes: ['S21', 'S11'] });
  assert.match(parseParameterInput('', available).error, /至少/);
  assert.match(parseParameterInput('S99', available).error, /不支持/);
  const nine = ['S11', 'S12', 'S13', 'S14', 'S21', 'S22', 'S23', 'S24', 'S31'].join(', ');
  assert.match(parseParameterInput(nine, available).error, /最多/);
});

test('toggleParameterCode 增删参数并保护曲线数量上限', () => {
  assert.deepEqual(toggleParameterCode('S21', 'S11', 8), { value: 'S21, S11', overflow: false });
  assert.deepEqual(toggleParameterCode('S21, S11', 'S21', 8), { value: 'S11', overflow: false });
  assert.deepEqual(toggleParameterCode('', 'SDD21', 8), { value: 'SDD21', overflow: false });
  const eight = 'S11, S12, S21, S22, SDD11, SDD21, SDD22, SCC11';
  const overflow = toggleParameterCode(eight, 'SCC21', 8);
  assert.equal(overflow.overflow, true);
  assert.equal(overflow.value, eight);
});

test('QuickParameterStore 去重、限长并忽略损坏数据', () => {
  const store = new QuickParameterStore();
  store.add('sdd21');
  assert.deepEqual(store.codes, ['SDD21']);
  store.add('SDD21');
  assert.deepEqual(store.codes, ['SDD21']);
  assert.ok(store.has('SDD21'));
  assert.ok(!store.isFull);
  store.remove('SDD21');
  assert.deepEqual(store.codes, []);

  const broken = { getItem: () => '{"not":"an array"}', setItem: () => {} };
  assert.deepEqual(new QuickParameterStore({ storage: broken }).codes, []);

  const thrower = {
    getItem: () => {
      throw new Error('blocked');
    },
    setItem: () => {
      throw new Error('blocked');
    },
  };
  const safe = new QuickParameterStore({ storage: thrower });
  assert.doesNotThrow(() => safe.add('S21'), '存储不可用时不应抛错');
  assert.deepEqual(safe.codes, ['S21'], '存储不可用时仍保留本次会话内的改动');
  assert.doesNotThrow(() => safe.remove('S21'));
});

test('QuickParameterStore 按上限截断历史数据', () => {
  const many = Array.from({ length: MAX_QUICK_PARAMETERS + 5 }, () => 'S21');
  const storage = { getItem: () => JSON.stringify(many), setItem: () => {} };
  assert.equal(new QuickParameterStore({ storage }).codes.length, 1);
});

test('WorkbenchState 维护文件、识别结果与竞态代次', () => {
  const state = new WorkbenchState({ quickParameters: null });
  assert.ok(!state.allFilesSelected());
  state.files.total = { name: 'total.s4p' };
  state.files.thru_a = { name: 'a.s4p' };
  state.files.thru_b = { name: 'b.s4p' };
  assert.ok(state.allFilesSelected());

  state.inspection = { inspection_token: 'token' };
  state.calculation = { result_token: 'result' };
  state.setFile('total', { name: 'total2.s4p' });
  assert.equal(state.inspection, null);
  assert.equal(state.calculation, null);

  const first = state.nextInspectionGeneration();
  const second = state.nextInspectionGeneration();
  assert.equal(second, first + 1);

  state.calculation = { result_token: 'r' };
  state.reset();
  assert.equal(state.calculation, null);
  assert.equal(state.mappingRecalcNeeded, false);
  assert.ok(!state.allFilesSelected());
});

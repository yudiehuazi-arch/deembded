/**
 * InputChartController —— 输入网络对照图表（A / Total / B 叠加）。
 *
 * 数据来源是 ``/api/inspect`` 返回的三个输入网络预览：频域下把三条曲线插值
 * 到共同频段，时域下请求 ``/api/tdr/input`` 得到三条阶跃阻抗曲线。
 */

import { SLOT_UI } from '../config/constants.js';
import { $ } from '../core/dom.js';
import { parseParameterInput } from '../core/params.js';
import { ChartPanel } from '../charts/chartPanel.js';
import { buildInputSparamDisplay, buildInputTdrTraces } from '../charts/series.js';
import { sliceTdrDisplay } from '../charts/tdrSlice.js';
import { ChartLegend } from '../ui/legends.js';
import { renderHoverCard } from '../ui/readouts.js';
import { TdrControls } from '../ui/tdrControls.js';
import { ChartFlowController } from './chartFlowController.js';

export class InputChartController extends ChartFlowController {
  /**
   * @param {Object} options
   * @param {import('../core/api.js').DeembedApi} options.api
   * @param {import('../core/state.js').WorkbenchState} options.state
   * @param {(kind: string, title: string, detail: string, tag?: string) => void} options.report 状态栏上报
   * @param {() => string} options.readPortMapping
   * @param {() => number|string} options.readReferenceZ0
   */
  constructor({ api, state, report, readPortMapping, readReferenceZ0 }) {
    const panel = $('input-chart-panel');
    const chart = new ChartPanel({
      canvas: $('input-chart-canvas'),
      wrap: $('input-chart-wrap'),
      marker: $('input-chart-x-marker'),
      markerLabel: $('input-chart-x-marker-label'),
      points: $('input-chart-point-markers'),
      readout: $('input-chart-hover-readout'),
      xValueInput: $('input-chart-x-value'),
      xUnitLabel: $('input-chart-x-unit'),
      yMinInput: $('input-chart-y-min'),
      yMaxInput: $('input-chart-y-max'),
      yApplyButton: $('btn-input-y-apply'),
      yAutoButton: $('btn-input-y-auto'),
      xLocateButton: $('btn-input-x-locate'),
      statusElement: $('input-chart-axis-status'),
      pointClassName: 'input-chart-point-marker',
      readoutRenderer: renderHoverCard,
    });

    super({
      chart,
      legend: new ChartLegend({ legendId: 'input-chart-legend' }),
      tdrControls: new TdrControls('input'),
      panel,
      statusElement: $('input-tdr-status'),
      viewSelectId: 'input-chart-view',
    });

    this.api = api;
    this.state = state;
    this.report = report;
    this.readPortMapping = readPortMapping;
    this.readReferenceZ0 = readReferenceZ0;
    this.items = null;
    this.display = null;

    chart.isInteractable = () => this.hasData && this.isPanelVisible;
  }

  get hasData() {
    return Boolean(this.items?.length && this.display);
  }

  isAvailable() {
    return this.hasData;
  }

  // ------------------------------------------------------------------ 装配
  attach() {
    this.chart.attach();
    this.tdrControls.bind({
      onSettingsChanged: () => {
        if (this.isTdr) this.loadTdr();
      },
      onWindowChanged: () => {
        if (this.isTdr) this.draw();
      },
    });
    const view = $(this.viewSelectId);
    view?.addEventListener('change', () => this.setView(view.value));
    $('btn-generate-input-chart')?.addEventListener('click', () => this.showCombined());
    $('btn-close-input-chart')?.addEventListener('click', () => this.close());
  }

  close() {
    this.hidePanel();
    this.invalidateTdr();
    this.chart.hideMarker(true);
  }

  /** 丢弃当前输入图数据（重新选择文件或重新识别时调用）。 */
  invalidate({ hidePanel = true } = {}) {
    this.items = null;
    this.display = null;
    this.invalidateTdr();
    if (hidePanel) this.hidePanel();
  }

  /** TDR 设置变化时按需重新请求（供 Workbench 在 Z₀ 变化时调用）。 */
  reloadTdrIfActive() {
    if (this.isTdr) this.loadTdr();
  }

  // -------------------------------------------------------------- 组合图表
  /** 读取三个参数输入框，生成组合 S 参数图。 */
  showCombined() {
    const previews = this.state.inspection?.file_previews;
    if (!previews) {
      this.report('error', '尚未完成文件识别', '请等待三个 Touchstone 文件识别完成，再生成组合 S 参数或 TDR 图。');
      return;
    }

    const items = [];
    for (const [slot, ui] of Object.entries(SLOT_UI)) {
      const field = $(ui.inputId);
      const note = $(ui.noteId);
      const raw = field?.value.trim() || '';
      field?.setAttribute('aria-invalid', 'false');
      note?.classList.remove('is-error');
      if (!raw) {
        if (note) note.textContent = '留空，组合图中不绘制';
        continue;
      }
      const preview = previews[slot];
      const parsed = parseParameterInput(raw, Object.keys(preview?.series || {}));
      if (parsed.error) {
        field?.setAttribute('aria-invalid', 'true');
        if (note) {
          note.textContent = parsed.error;
          note.classList.add('is-error');
        }
        return;
      }
      items.push({ slot, preview, codes: parsed.codes, label: ui.chartLabel });
      if (note) note.textContent = `${parsed.codes.join(', ')} · ${preview.freq_ghz.length.toLocaleString('en-US')} 点 · 已加入组合图`;
    }

    if (!items.length) {
      this.report('error', '没有可绘制的参数', '请至少在 A、Total、B 其中一栏输入一个有效的 S 参数。');
      return;
    }
    const display = buildInputSparamDisplay(items);
    if (!display) {
      this.report('error', '频段没有重叠', '这几条输入曲线无法在共同频段中叠加，请检查文件的频率范围。');
      return;
    }

    this.items = items;
    this.display = display;
    this.mode = 'sparam';
    this.invalidateTdr();
    this.syncSelect();
    this.chart.resetAxisControls();
    this.setHidden('input-tdr-controls', true);
    this.setHidden('input-tdr-status', true);
    this.chart.hideMarker(true);

    this.setTitle();
    this.setHidden('input-chart-axis-label', false);
    this.setText('input-chart-axis-label', '频率 (GHz)');
    this.setText('input-chart-y-label', '幅度 (dB)');
    this.legend.renderInputTraces(display.traces);
    this.showPanel();
    requestAnimationFrame(() => this.draw());
    this.panel?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // ------------------------------------------------------------------ 渲染
  applyModeUi() {
    const isTdr = this.isTdr;
    this.setHidden('input-tdr-controls', !isTdr);
    this.setHidden('input-tdr-status', !isTdr);
    this.setText('input-chart-y-label', isTdr ? '阻抗 (Ω)' : '幅度 (dB)');
    this.setText('input-chart-axis-label', isTdr ? '时间 (ns)' : '频率 (GHz)');
    if (isTdr) this.setHidden('input-tdr-status', false);
  }

  refresh() {
    if (this.isTdr) {
      this.draw();
      return;
    }
    this.legend.renderInputTraces(this.display.traces);
    this.setTitle();
    this.draw();
  }

  setTitle() {
    const names = this.items.map((item) => SLOT_UI[item.slot].label).join(' + ');
    this.setText('input-chart-title', this.isTdr ? 'TDR 阶跃阻抗 · 2X Thru A + Total + 2X Thru B' : `${names} · S 参数对比`);
    this.setText(
      'input-chart-subtitle',
      this.isTdr
        ? `${this.names()} · ${this.tdrControls.parameterName(this.state.inspection?.nports)} · 三个输入网络叠加`
        : `${this.summaryText()} · ${this.frequencyRangeText(this.display.freq_ghz)}`,
    );
  }

  buildView() {
    if (this.isTdr) {
      if (!this.tdrData) return { xValues: [], xUnit: 'ns', yUnit: 'Ω', xDecimals: 3, traces: [] };
      const display = sliceTdrDisplay(this.tdrData, this.tdrControls.readTimeWindow());
      return {
        xValues: display.time_ns,
        xUnit: 'ns',
        yUnit: 'Ω',
        xDecimals: 3,
        traces: buildInputTdrTraces(display, this.tdrData.parameter),
      };
    }
    if (!this.display) return { xValues: [], xUnit: 'GHz', yUnit: 'dB', traces: [] };
    return {
      xValues: this.display.freq_ghz,
      xUnit: 'GHz',
      yUnit: 'dB',
      xDecimals: 2,
      traces: this.display.traces,
    };
  }

  // ------------------------------------------------------------------- TDR
  async loadTdr() {
    if (!this.hasData || !this.isTdr) return;
    const requestId = this.beginTdrRequest();
    this.legend.renderInputTdr(this.tdrControls.parameterName(this.state.inspection?.nports));
    this.tdrControls.updatePortOptions(this.state.inspection?.nports);
    this.showStatus('正在计算 A、Total、B 三条时域阶跃响应…');
    this.setTitle();
    this.draw();

    const inspectionToken = this.state.inspection?.inspection_token;
    if (!inspectionToken) {
      this.showStatus('输入网络缓存已过期，请重新识别三个文件后再生成 TDR。');
      this.draw();
      return;
    }

    const settings = this.tdrControls.readSettings({
      portMapping: this.readPortMapping(),
      referenceZ0: this.readReferenceZ0(),
    });

    try {
      const data = await this.api.tdrInput({ inspectionToken, slot: 'all', ...settings });
      if (!this.isCurrentTdrRequest(requestId)) return;
      this.tdrData = data;
      const referenceMode = this.state.inspection?.nports === 4 ? '差分' : '单端';
      this.showStatus(
        `${data.parameter} · ${referenceMode}参考阻抗 ${Number(data.reference_ohm).toFixed(0)} Ω · 原生 Δt ${Number(
          data.sample_step_ps,
        ).toFixed(2)} ps · A + Total + B`,
      );
      this.setText(
        'input-chart-subtitle',
        `${this.names()} · ${data.parameter} · ${data.window} 窗 · ${
          data.dc_method === 'linear' ? '线性 DC 外推' : '首点延拓'
        } · 上升时间 ${Number(data.rise_time_ps).toFixed(0)} ps`,
      );
      this.legend.renderInputTdr(data.parameter);
      this.draw();
    } catch (error) {
      if (!this.isCurrentTdrRequest(requestId)) return;
      this.tdrData = null;
      this.showStatus(`TDR 生成失败：${error.message}`);
      this.draw();
    }
  }

  // ------------------------------------------------------------------ 文案
  summaryText() {
    return this.items
      .map((item) => `${SLOT_UI[item.slot].label}: ${this.state.files[item.slot]?.name || '—'} (${item.codes.join(', ')})`)
      .join('  |  ');
  }

  names() {
    return ['thru_a', 'total', 'thru_b']
      .map((slot) => `${SLOT_UI[slot].chartLabel}: ${this.state.files[slot]?.name || '—'}`)
      .join('  |  ');
  }

  frequencyRangeText(freqGhz) {
    if (!freqGhz?.length) return '—';
    return `${Number(freqGhz[0]).toFixed(3)}–${Number(freqGhz[freqGhz.length - 1]).toFixed(3)} GHz`;
  }

  /** 重置为初始状态（清空按钮）。 */
  reset() {
    this.items = null;
    this.display = null;
    this.mode = 'sparam';
    this.invalidateTdr();
    this.syncSelect();
    this.chart.shutdown();
    this.legend.clear();
    this.hidePanel();
    this.setHidden('input-tdr-controls', true);
    this.setHidden('input-tdr-status', true);
  }
}

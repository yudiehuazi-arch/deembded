/**
 * ResultChartController —— 去嵌结果图表（参数对比图 + 结果 TDR）。
 *
 * 与 :class:`InputChartController` 共享 :class:`ChartFlowController` 的
 * 模式切换与竞态保护，差异在于数据来自 ``/api/deembed`` 与
 * ``/api/tdr/result``，并且频域曲线由“参数 × 网络”组合而成。
 */

import { MAX_CHART_PARAMETERS } from '../config/constants.js';
import { $, setHidden } from '../core/dom.js';
import { splitParameterCodes } from '../core/format.js';
import { ChartPanel } from '../charts/chartPanel.js';
import { buildResultSparamTraces, buildResultTdrTraces } from '../charts/series.js';
import { sliceTdrDisplay } from '../charts/tdrSlice.js';
import { ChartLegend } from '../ui/legends.js';
import { renderTooltip } from '../ui/readouts.js';
import { TdrControls } from '../ui/tdrControls.js';
import { ChartFlowController } from './chartFlowController.js';

export class ResultChartController extends ChartFlowController {
  /**
   * @param {Object} options
   * @param {import('../core/api.js').DeembedApi} options.api
   * @param {import('../core/state.js').WorkbenchState} options.state
   * @param {() => string[]} options.readNetworkKeys 已勾选的对比网络
   */
  constructor({ api, state, readNetworkKeys }) {
    const panel = $('result-panel');
    const canvas = $('chart-canvas');
    const chart = new ChartPanel({
      canvas,
      wrap: canvas?.parentElement || canvas,
      points: $('result-chart-points'),
      marker: $('result-chart-crosshair'),
      readout: $('chart-tooltip'),
      xValueInput: $('result-chart-x-value'),
      xUnitLabel: $('result-chart-x-unit'),
      yMinInput: $('result-chart-y-min'),
      yMaxInput: $('result-chart-y-max'),
      yApplyButton: $('btn-result-y-apply'),
      yAutoButton: $('btn-result-y-auto'),
      xLocateButton: $('btn-result-x-locate'),
      statusElement: $('result-chart-axis-status'),
      pointClassName: 'result-chart-point-marker',
      readoutRenderer: renderTooltip,
    });

    super({
      chart,
      legend: new ChartLegend({ legendId: 'chart-legend' }),
      tdrControls: new TdrControls('result'),
      panel,
      statusElement: $('result-tdr-status'),
      viewSelectId: 'result-chart-view',
    });

    this.api = api;
    this.state = state;
    this.readNetworkKeys = readNetworkKeys;
    this.parameters = ['S21'];

    chart.isInteractable = () => Boolean(this.state.calculation) && this.isPanelVisible;
  }

  isAvailable() {
    return Boolean(this.state.calculation);
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
    $('btn-plot-params')?.addEventListener('click', () => this.applyParameters());
    $('chart-params')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        this.applyParameters();
      }
    });
  }

  /** 新结果到达：复位到频域视图并刷新图例。 */
  update(parameters) {
    this.mode = 'sparam';
    this.parameters = parameters;
    this.invalidateTdr();
    this.syncSelect();
    this.chart.hideMarker(true);
    this.chart.resetAxisControls();
    setHidden($('result-tdr-controls'), true);
    setHidden($('result-tdr-status'), true);
    setHidden($('chart-sparam-controls'), false);
    setHidden($('param-chips'), false);
    this.setText('result-chart-kicker', 'FREQUENCY RESPONSE');
    this.setText('result-chart-title', '自定义 S 参数幅度图');
    this.setText('result-chart-subtitle', '输入矩阵参数名，可用逗号分隔多个参数。');
    this.setText('chart-y-label', '幅度 (dB)');
    this.setText('chart-frequency-label', '频率 (GHz)');
    this.tdrControls.updatePortOptions(this.state.calculation?.nports);
    this.refresh();
    requestAnimationFrame(() => this.draw());
  }

  /** 网格开关变化：只重绘，不重新请求。 */
  onNetworkSelectionChanged() {
    this.refresh();
  }

  // ------------------------------------------------------------------ 参数
  /** 校验并应用 ``chart-params`` 输入框。 */
  applyParameters() {
    if (!this.state.calculation) return;
    const field = $('chart-params');
    const errorElement = $('chart-param-error');
    const requested = splitParameterCodes(field?.value || '');
    const available = Object.keys(this.state.calculation.chart.series);

    const fail = (message) => {
      field?.setAttribute('aria-invalid', 'true');
      if (errorElement) errorElement.textContent = message;
    };

    if (!requested.length) {
      fail('请输入至少一个 S 参数，例如 S21 或 SDD21。');
      return;
    }
    if (requested.length > MAX_CHART_PARAMETERS) {
      fail(`为保证曲线可读，每次最多绘制 ${MAX_CHART_PARAMETERS} 个参数。`);
      return;
    }
    const invalid = requested.filter((code) => !available.includes(code));
    if (invalid.length) {
      const hint =
        this.state.calculation.nports === 4
          ? '支持 Sij 与 SDD/SCC/SCD/SDC 混合模参数。'
          : '当前 S2P 支持 S11、S12、S21、S22。';
      fail(`无法识别：${invalid.join(', ')}。${hint}`);
      return;
    }
    field?.setAttribute('aria-invalid', 'false');
    if (errorElement) errorElement.textContent = '';
    this.parameters = requested;
    this.refresh();
  }

  /** 参数建议芯片：默认参数直接替换，否则追加。 */
  appendParameter(code) {
    const field = $('chart-params');
    if (!field) return;
    const current = field.value.trim();
    const normalized = current.toUpperCase();
    field.value = !current || normalized === 'S21' || normalized === 'SDD21' ? code : `${current}, ${code}`;
    this.applyParameters();
  }

  // ------------------------------------------------------------------ 渲染
  applyModeUi() {
    const isTdr = this.isTdr;
    this.setText('result-chart-x-unit', isTdr ? 'ns' : 'GHz');
    this.setHidden('chart-sparam-controls', isTdr);
    this.setHidden('param-chips', isTdr);
    this.setHidden('result-tdr-controls', !isTdr);
    this.setHidden('result-tdr-status', !isTdr);
    this.setText('chart-y-label', isTdr ? '阻抗 (Ω)' : '幅度 (dB)');
    this.setText('chart-frequency-label', isTdr ? '时间 (ns)' : '频率 (GHz)');
    this.setText('result-chart-kicker', isTdr ? 'TIME DOMAIN REFLECTOMETRY' : 'FREQUENCY RESPONSE');
    this.setText('result-chart-title', isTdr ? 'TDR 阶跃阻抗图' : '自定义 S 参数幅度图');
    this.setText(
      'result-chart-subtitle',
      isTdr ? '根据所选反射端口和 TDR 设置重新计算。' : '输入矩阵参数名，可用逗号分隔多个参数。',
    );
    if (isTdr) this.tdrControls.updatePortOptions(this.state.calculation?.nports);
  }

  refresh() {
    this.legend.render({
      calculation: this.state.calculation,
      activeParameters: this.parameters,
      networkKeys: this.readNetworkKeys(),
      mode: this.mode,
      tdrData: this.tdrData,
    });
    this.draw();
  }

  buildView() {
    const calculation = this.state.calculation;
    if (!calculation) return { xValues: [], xUnit: 'GHz', yUnit: 'dB', traces: [] };

    if (this.isTdr) {
      if (!this.tdrData) return { xValues: [], xUnit: 'ns', yUnit: 'Ω', xDecimals: 3, traces: [] };
      const display = sliceTdrDisplay(this.tdrData, this.tdrControls.readTimeWindow());
      const keys = this.readNetworkKeys().filter((key) => display.series?.[key]);
      return {
        xValues: display.time_ns,
        xUnit: 'ns',
        yUnit: 'Ω',
        xDecimals: 3,
        traces: buildResultTdrTraces(display, keys, this.tdrData.parameter, calculation),
      };
    }

    return {
      xValues: calculation.chart.freq_ghz,
      xUnit: 'GHz',
      yUnit: 'dB',
      xDecimals: 2,
      traces: buildResultSparamTraces(calculation, this.parameters, this.readNetworkKeys()),
    };
  }

  // ------------------------------------------------------------------- TDR
  async loadTdr() {
    if (!this.isAvailable() || !this.isTdr) return;
    const requestId = this.beginTdrRequest();
    this.refresh();
    this.showStatus('正在从复数 S 参数计算时域阶跃响应…');

    const inspectionToken = this.state.inspection?.inspection_token;
    const resultToken = this.state.calculation.result_token;
    if (!inspectionToken || !resultToken) {
      this.showStatus(
        !inspectionToken
          ? '输入网络缓存已过期，请重新识别三个文件后再生成结果 TDR。'
          : '本次结果未缓存复数网络数据，请重新运行去嵌后再试。',
      );
      this.draw();
      return;
    }

    const settings = this.tdrControls.readSettings({
      portMapping: this.state.calculation.port_mapping || 'auto',
      referenceZ0: this.state.calculation.reference_z0 || 50,
    });

    try {
      const data = await this.api.tdrResult({ inspectionToken, resultToken, ...settings });
      if (!this.isCurrentTdrRequest(requestId)) return;
      this.tdrData = data;
      const mode = this.state.calculation.nports === 4 ? '差分' : '单端';
      this.showStatus(
        `${data.parameter} · ${mode}参考阻抗 ${Number(data.reference_ohm).toFixed(0)} Ω · 原生 Δt ${Number(
          data.sample_step_ps,
        ).toFixed(2)} ps · ${data.time_ns.length.toLocaleString('en-US')} 显示点`,
      );
      this.setText(
        'result-chart-subtitle',
        `阶跃阻抗 · ${data.parameter} · DC ${data.dc_method === 'linear' ? '线性外推' : '首点延拓'} · ${
          data.window
        } 窗 · 上升时间 ${Number(data.rise_time_ps).toFixed(0)} ps`,
      );
      this.refresh();
    } catch (error) {
      if (!this.isCurrentTdrRequest(requestId)) return;
      this.tdrData = null;
      this.showStatus(`TDR 生成失败：${error.message}`);
      this.draw();
    }
  }

  /** 重置为初始状态（清空按钮）。 */
  reset() {
    this.parameters = ['S21'];
    this.mode = 'sparam';
    this.invalidateTdr();
    this.syncSelect();
    this.chart.shutdown();
    this.legend.clear();
    this.hidePanel();
  }
}

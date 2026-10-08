/**
 * ChartFlowController —— 图表流程控制器基类。
 *
 * 输入图表（A / Total / B 叠加）与结果图表（去嵌对比）共享同一套交互流程：
 *
 * * 视图模式（S 参数 / TDR）切换与控件显隐；
 * * TDR 请求的竞态保护（旧的响应必须被丢弃）；
 * * 标记线、Y 轴范围与图例的刷新时机；
 * * 面板可用性判断（未识别文件 / 未计算时不响应交互）。
 *
 * 子类只需要实现三处差异：
 * ``buildView()``（取哪份数据）、``loadTdr()``（请求哪个接口）、
 * ``refresh()``（频域模式下图例与文案如何渲染）。
 */

import { $, setHidden } from '../core/dom.js';

export class ChartFlowController {
  /**
   * @param {Object} options
   * @param {import('../charts/chartPanel.js').ChartPanel} options.chart 画布交互控制器
   * @param {import('../ui/legends.js').ChartLegend} options.legend 图例渲染器
   * @param {import('../ui/tdrControls.js').TdrControls} options.tdrControls TDR 设置读取器
   * @param {HTMLElement|null} options.panel 面板容器（用于显隐与可用性判断）
   * @param {HTMLElement|null} options.statusElement TDR 状态提示元素
   * @param {string|null} options.viewSelectId 视图切换下拉框 id
   */
  constructor({ chart, legend, tdrControls, panel = null, statusElement = null, viewSelectId = null }) {
    this.chart = chart;
    this.legend = legend;
    this.tdrControls = tdrControls;
    this.panel = panel;
    this.statusElement = statusElement;
    this.viewSelectId = viewSelectId;

    this.mode = 'sparam';
    this.tdrData = null;
    this.tdrRequestId = 0;
  }

  get isTdr() {
    return this.mode === 'tdr';
  }

  /** 面板是否可以交互 / 绘制。子类覆写。 */
  isAvailable() {
    return true;
  }

  // ------------------------------------------------------------------ 模板
  /** 切换视图模式：统一处理竞态失效、坐标轴复位与视图分派。 */
  setView(mode) {
    if (!this.isAvailable()) return;
    const next = mode === 'tdr' ? 'tdr' : 'sparam';
    const changed = next !== this.mode;
    this.mode = next;
    this.invalidateTdr();
    if (changed) this.chart.resetAxisControls();
    this.chart.hideMarker(true);
    this.syncSelect();
    this.applyModeUi();
    if (next === 'tdr') this.loadTdr();
    else this.refresh();
  }

  /** 模式相关的文案与控件显隐。子类覆写。 */
  applyModeUi() {}

  /** 频域模式下刷新图例/标题并重绘。子类覆写。 */
  refresh() {
    this.draw();
  }

  /** 子类实现：把当前数据转换成 renderer 需要的视图。 */
  buildView() {
    throw new Error(`${this.constructor.name} 必须实现 buildView()`);
  }

  /** 时域模式下拉取数据。子类覆写。 */
  loadTdr() {}

  // ------------------------------------------------------------------ 请求
  /** 开始一次 TDR 请求：递增代次、丢弃旧数据、清空标记与 X 输入框。 */
  beginTdrRequest() {
    this.tdrRequestId += 1;
    this.tdrData = null;
    this.chart.pinned = false;
    this.chart.hideMarker(true);
    this.chart.clearXValue();
    return this.tdrRequestId;
  }

  /** 响应是否仍然有效（竞态保护）。 */
  isCurrentTdrRequest(requestId) {
    return requestId === this.tdrRequestId;
  }

  /** 使进行中的 TDR 请求失效（切换文件、重置时调用）。 */
  invalidateTdr() {
    this.tdrRequestId += 1;
    this.tdrData = null;
  }

  // ------------------------------------------------------------------ 绘制
  draw() {
    if (!this.isAvailable()) return;
    this.chart.setView(this.buildView());
    this.chart.draw();
  }

  hidePanel() {
    if (this.panel) this.panel.hidden = true;
  }

  showPanel() {
    if (this.panel) this.panel.hidden = false;
  }

  get isPanelVisible() {
    return Boolean(this.panel) && !this.panel.hidden;
  }

  syncSelect() {
    if (!this.viewSelectId) return;
    const select = $(this.viewSelectId);
    if (select) select.value = this.mode;
  }

  // ------------------------------------------------------------------ 提示
  showStatus(text) {
    if (!this.statusElement) return;
    this.statusElement.hidden = false;
    this.statusElement.textContent = text;
  }

  hideStatus() {
    if (this.statusElement) this.statusElement.hidden = true;
  }

  setText(id, text) {
    const element = $(id);
    if (element) element.textContent = text;
  }

  setHidden(id, hidden) {
    setHidden($(id), hidden);
  }
}

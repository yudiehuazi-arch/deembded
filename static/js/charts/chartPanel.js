/**
 * ChartPanel —— 输入图表与结果图表共用的交互控制器。
 *
 * 职责：
 *  * 维护当前视图（横轴数据 + 曲线集合）与 Y 轴范围；
 *  * 调用 renderer 绘制；
 *  * 处理光标竖线 / 数据点圆点 / 读数卡片；
 *  * 处理 Y 轴手填范围与 X 标记定位控件。
 *
 * 差异部分（圆点样式、读数卡片布局、单位与小数位）通过构造参数注入，
 * 因此两个面板共用同一份逻辑，避免此前 ~700 行重复实现。
 */

import { CHART_PADDING } from '../config/constants.js';
import { fractionForXValue, indexPositionForFraction, interpolateAt, plotGeometry, pointerFraction, pointerYFraction } from './geometry.js';
import { drawLineChart } from './renderer.js';
import { chartScaleFromValues, chartScaleWithLimits, parseAxisBound } from './scale.js';

const EMPTY_VIEW = { xValues: [], xUnit: 'GHz', yUnit: 'dB', xDecimals: 2, traces: [] };

export class ChartPanel {
  constructor({
    canvas,
    wrap,
    marker = null,
    markerLabel = null,
    points = null,
    readout = null,
    xValueInput,
    xUnitLabel = null,
    yMinInput,
    yMaxInput,
    yApplyButton,
    yAutoButton,
    xLocateButton,
    statusElement,
    pointClassName = 'chart-point-marker',
    readoutRenderer = null,
    isInteractable = () => true,
    onViewChange = null,
  }) {
    this.elements = {
      canvas,
      wrap,
      marker,
      markerLabel,
      points,
      readout,
      xValueInput,
      xUnitLabel,
      yMinInput,
      yMaxInput,
      yApplyButton,
      yAutoButton,
      xLocateButton,
      statusElement,
    };
    this.pointClassName = pointClassName;
    this.readoutRenderer = readoutRenderer;
    this.isInteractable = isInteractable;
    this.onViewChange = onViewChange;

    this.view = { ...EMPTY_VIEW };
    this.yLimits = { min: null, max: null };
    this.hoverFraction = null;
    this.hoverYFraction = 0.25;
    this.pinned = false;
  }

  // ------------------------------------------------------------------ 视图
  setView(view) {
    this.view = { ...EMPTY_VIEW, ...view };
  }

  get xUnit() {
    return this.view.xUnit || 'GHz';
  }

  get yUnit() {
    return this.view.yUnit || 'dB';
  }

  get xValues() {
    return this.view.xValues || [];
  }

  draw() {
    const { canvas } = this.elements;
    drawLineChart(canvas, this.view.xValues, this.view.traces, {
      xDecimals: this.view.xDecimals,
      yMin: this.yLimits.min,
      yMax: this.yLimits.max,
    });
    if (this.hoverFraction !== null) this.positionMarker(this.hoverFraction, this.hoverYFraction);
  }

  // ------------------------------------------------------------------ 标记
  /** 清空 X 标记输入框（切换视图/数据时调用）。 */
  clearXValue() {
    if (this.elements.xValueInput) this.elements.xValueInput.value = '';
  }

  hideMarker(force = false) {
    if (this.pinned && !force) return;
    this.pinned = false;
    this.hoverFraction = null;
    const { marker, points, readout } = this.elements;
    if (marker) marker.hidden = true;
    if (points) points.innerHTML = '';
    if (readout) readout.hidden = true;
  }

  markerElements() {
    const { marker, points, readout } = this.elements;
    if (!marker || !points) return null;
    return { marker, points, readout };
  }

  positionMarker(fraction, yFraction = this.hoverYFraction) {
    const geometry = plotGeometry(this.elements.canvas);
    const elements = this.markerElements();
    if (!elements || geometry.plotWidth <= 0 || geometry.plotHeight <= 0) return;

    const normalized = Math.max(0, Math.min(1, fraction));
    this.hoverFraction = normalized;
    this.hoverYFraction = Math.max(0, Math.min(1, yFraction));

    const indexPosition = indexPositionForFraction(this.xValues.length, normalized);
    const xValue = interpolateAt(this.xValues, indexPosition);
    const markerX = geometry.plotLeft + normalized * geometry.plotWidth;

    if (this.elements.xValueInput && Number.isFinite(xValue)) {
      this.elements.xValueInput.value = xValue.toFixed(6);
    }
    if (this.elements.markerLabel) {
      this.elements.markerLabel.textContent = `${xValue.toFixed(this.view.xDecimals ?? 3)} ${this.xUnit}`;
    }
    elements.marker.style.left = `${markerX}px`;
    elements.marker.hidden = false;

    const rows = this.view.traces.map((trace) => {
      const value = interpolateAt(trace.values, indexPosition);
      return { label: trace.label, color: trace.color, value };
    });
    const scale = chartScaleWithLimits(this.view.traces.flatMap((trace) => trace.values), this.yLimits);

    elements.points.innerHTML = '';
    rows.forEach((row) => {
      if (!Number.isFinite(row.value) || !scale) return;
      const dot = document.createElement('span');
      dot.className = this.pointClassName;
      dot.style.left = `${markerX}px`;
      dot.style.top = `${geometry.plotTop + ((scale.yMax - row.value) / (scale.yMax - scale.yMin)) * geometry.plotHeight}px`;
      dot.style.backgroundColor = row.color;
      dot.title = `${row.label}: ${row.value.toFixed(2)} ${this.yUnit}`;
      elements.points.appendChild(dot);
    });

    if (this.readoutRenderer && elements.readout) {
      this.readoutRenderer({
        container: elements.readout,
        xText: `${xValue.toFixed(this.view.xDecimals === 3 ? 4 : 3)} ${this.xUnit}`,
        rows: rows.map((row) => ({ ...row, text: Number.isFinite(row.value) ? `${row.value.toFixed(2)} ${this.yUnit}` : '—' })),
        markerX,
        yFraction: this.hoverYFraction,
        wrap: this.elements.wrap || this.elements.canvas,
        markerLabel: this.view.traces.length ? this.view.traces[0].label : '',
      });
    }
    if (this.onViewChange) this.onViewChange();
  }

  // ---------------------------------------------------------------- 轴控件
  setStatus(message, isError = false) {
    const status = this.elements.statusElement;
    if (!status) return;
    status.textContent = message;
    status.classList.toggle('is-error', isError);
  }

  yAxisValues() {
    return this.view.traces.flatMap((trace) => trace.values);
  }

  applyYRange() {
    const minResult = parseAxisBound(this.elements.yMinInput?.value);
    const maxResult = parseAxisBound(this.elements.yMaxInput?.value);
    if (minResult.error || maxResult.error) {
      this.setStatus(minResult.error || maxResult.error, true);
      return;
    }
    const automatic = chartScaleFromValues(this.yAxisValues());
    if (!automatic) {
      this.setStatus('当前图表没有可用曲线。', true);
      return;
    }
    const actualMin = minResult.value ?? automatic.yMin;
    const actualMax = maxResult.value ?? automatic.yMax;
    if (actualMin >= actualMax) {
      this.setStatus('Y 轴最小值必须小于最大值。', true);
      return;
    }
    this.yLimits = { min: minResult.value, max: maxResult.value };
    this.setStatus(`Y 轴范围已应用：${actualMin}–${actualMax} ${this.yUnit}`);
    this.draw();
  }

  resetYRange(announce = true) {
    if (this.elements.yMinInput) this.elements.yMinInput.value = '';
    if (this.elements.yMaxInput) this.elements.yMaxInput.value = '';
    this.yLimits = { min: null, max: null };
    if (announce) this.setStatus('Y 轴已恢复自动缩放。');
    this.draw();
  }

  resetAxisControls() {
    this.yLimits = { min: null, max: null };
    if (this.elements.yMinInput) this.elements.yMinInput.value = '';
    if (this.elements.yMaxInput) this.elements.yMaxInput.value = '';
    if (this.elements.xValueInput) this.elements.xValueInput.value = '';
    if (this.elements.xUnitLabel) this.elements.xUnitLabel.textContent = this.xUnit;
    this.pinned = false;
    this.setStatus('Y 轴留空时自动缩放；可输入 X 值并定位标记线。');
  }

  locateXMarker() {
    const field = this.elements.xValueInput;
    if (!field) return;
    const raw = field.value.trim();
    if (!raw) {
      this.pinned = false;
      this.hideMarker(true);
      this.setStatus('X 标记线已清除。');
      return;
    }
    const target = Number(raw);
    if (!Number.isFinite(target)) {
      this.setStatus('请输入有效的 X 标记值。', true);
      return;
    }
    const fraction = fractionForXValue(this.xValues, target);
    if (fraction === null) {
      const first = this.xValues.length ? Number(this.xValues[0]) : NaN;
      const last = this.xValues.length ? Number(this.xValues[this.xValues.length - 1]) : NaN;
      const range =
        Number.isFinite(first) && Number.isFinite(last)
          ? `当前显示范围为 ${first.toFixed(4)}–${last.toFixed(4)} ${this.xUnit}。`
          : '请先等待图表数据生成。';
      this.setStatus(`该 X 值不在当前显示范围内。${range}`, true);
      return;
    }
    if (this.elements.xUnitLabel) this.elements.xUnitLabel.textContent = this.xUnit;
    this.pinned = true;
    this.positionMarker(fraction);
    this.setStatus(`X 标记线已定位：${target.toFixed(4)} ${this.xUnit}`);
  }

  // ------------------------------------------------------------------ 事件
  attachPointer() {
    const target = this.elements.wrap || this.elements.canvas;
    if (!target) return;
    target.addEventListener('pointermove', (event) => {
      if (!this.isInteractable()) return;
      if (this.elements.readout?.contains(event.target)) return;
      this.pinned = false;
      const fraction = pointerFraction(event, this.elements.canvas);
      if (fraction === null) {
        this.hideMarker();
        return;
      }
      this.positionMarker(fraction, pointerYFraction(event, this.elements.canvas));
    });
    target.addEventListener('pointerleave', () => this.hideMarker());
  }

  attachAxisControls() {
    this.elements.yApplyButton?.addEventListener('click', () => this.applyYRange());
    this.elements.yAutoButton?.addEventListener('click', () => this.resetYRange());
    this.elements.xLocateButton?.addEventListener('click', () => this.locateXMarker());
    this.elements.xValueInput?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        this.locateXMarker();
      }
    });
    [this.elements.yMinInput, this.elements.yMaxInput].forEach((input) =>
      input?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          this.applyYRange();
        }
      }),
    );
  }

  attach() {
    this.attachPointer();
    this.attachAxisControls();
  }

  /** 面板关闭/复位时调用：清空 Y 轴范围与标记。 */
  shutdown() {
    this.resetAxisControls();
    this.hideMarker(true);
    this.view = { ...EMPTY_VIEW };
  }

  get padding() {
    return CHART_PADDING;
  }
}

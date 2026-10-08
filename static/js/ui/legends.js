/** 图表图例渲染（输入图与结果图）。 */

import {
  INPUT_TDR_COLORS,
  INPUT_TDR_NETWORK_LABELS,
  INPUT_TDR_NETWORK_ORDER,
  NETWORK_DASH,
  NETWORK_DOT_COLORS,
  NETWORK_LABELS,
  PARAMETER_COLORS,
} from '../config/constants.js';
import { $, clearChildren, createElement } from '../core/dom.js';

export class ChartLegend {
  constructor({ legendId, networkColors = NETWORK_DOT_COLORS, networkLabels = NETWORK_LABELS }) {
    this.element = $(legendId);
    this.networkColors = networkColors;
    this.networkLabels = networkLabels;
  }

  clear() {
    clearChildren(this.element);
  }

  appendSwatch(container, { color, dashed = false, text }) {
    const item = createElement('span');
    const swatch = createElement('i');
    swatch.style.borderTopColor = color;
    swatch.style.borderTopStyle = dashed ? 'dashed' : 'solid';
    item.append(swatch, document.createTextNode(text));
    container.appendChild(item);
  }

  /** 结果图图例：S 参数模式按“参数 × 网络”，TDR 模式按网络。 */
  render({ calculation, activeParameters, networkKeys, mode, tdrData }) {
    if (!this.element) return;
    this.clear();
    if (!calculation) return;

    if (mode === 'tdr') {
      networkKeys.forEach((key) => {
        if (!tdrData?.series?.[key]) return;
        this.appendSwatch(this.element, {
          color: this.networkColors[key],
          dashed: (NETWORK_DASH[key] || []).length > 0,
          text: `${this.networkLabels[key]} · ${tdrData.parameter} · ${Number(tdrData.reference_ohm).toFixed(0)} Ω`,
        });
      });
      return;
    }

    activeParameters.forEach((parameter, parameterIndex) => {
      const color = PARAMETER_COLORS[parameterIndex % PARAMETER_COLORS.length];
      networkKeys.forEach((key) => {
        this.appendSwatch(this.element, {
          color,
          dashed: key !== 'dut',
          text: `${parameter} · ${this.networkLabels[key]}`,
        });
      });
    });
  }

  /** 输入图图例：S 参数模式使用曲线自身的标签与线型。 */
  renderInputTraces(traces) {
    if (!this.element) return;
    this.clear();
    this.element.hidden = false;
    traces.forEach((trace) =>
      this.appendSwatch(this.element, {
        color: trace.color,
        dashed: (trace.dash || []).length > 0,
        text: trace.label,
      }),
    );
  }

  /** 输入图图例：TDR 模式按固定网络顺序。 */
  renderInputTdr(parameter) {
    if (!this.element) return;
    this.clear();
    this.element.hidden = false;
    INPUT_TDR_NETWORK_ORDER.forEach((key) =>
      this.appendSwatch(this.element, {
        color: INPUT_TDR_COLORS[key],
        dashed: (NETWORK_DASH[key] || []).length > 0,
        text: `${INPUT_TDR_NETWORK_LABELS[key]} · ${parameter}`,
      }),
    );
  }
}

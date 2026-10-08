/**
 * 差分模式转换诊断面板：2X Thru / DUT 的 P/N skew、模式转换强度，
 * 以及两种劈半算法（含 / 不含模式转换）得到的 DUT SDD21 差值。
 *
 * 目的：与 PLTS AFR 结果比对时，快速判断差异是否来自夹具模式转换
 * （PLTS 2019+ 的 AFR 夹具模型包含模式转换，经典 IEEE 370 MM-NZC 不含）。
 */

import { $, clearChildren, createElement, setHidden } from '../core/dom.js';
import { formatSigned } from '../core/format.js';

/** 两种算法 SDD21 差值低于该值（dB）时视为模式转换影响可忽略 */
export const NEGLIGIBLE_DELTA_DB = 0.05;
/** |skew| 低于该值（ps）时不判断极性 */
export const SIGNIFICANT_SKEW_PS = 0.2;

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

/** skew 文案：数值 + 哪条线更长。 */
export function formatSkew(skewPs) {
  if (!finite(skewPs)) return '—';
  if (Math.abs(skewPs) < 0.005) return '≈ 0 ps';
  return `${formatSigned(skewPs, 2)} ps（${skewPs > 0 ? 'P' : 'N'} 线较长）`;
}

/**
 * 根据诊断数据生成解读文本（纯函数，便于单元测试）。
 * @returns {{level: 'info'|'warn', messages: string[]}}
 */
export function describeModeConversion(diagnostics, { primaryAlgorithm = 'mc_nzc' } = {}) {
  const messages = [];
  if (!diagnostics) return { level: 'info', messages };
  const comparison = diagnostics.comparison;
  const maxDelta = comparison?.max_delta_db;
  let level = 'info';

  if (finite(maxDelta)) {
    if (Math.abs(maxDelta) < NEGLIGIBLE_DELTA_DB) {
      messages.push(
        `两种劈半算法的 SDD21 差异 < ${NEGLIGIBLE_DELTA_DB} dB：夹具模式转换对本组数据影响很小。若与 PLTS 仍有明显差异，请优先核对 PLTS 的 Deskew、Calibration Reference Z0、带通 / 门限设置以及文件端口映射。`,
      );
    } else {
      level = 'warn';
      // 主算法 − 对照算法；换算成 “含模式转换 − 经典” 的符号
      const mcMinusClassic = primaryAlgorithm === 'mc_nzc' ? maxDelta : -maxDelta;
      const direction = mcMinusClassic > 0 ? '偏低（损耗偏大）' : '偏高（损耗偏小）';
      messages.push(
        `夹具模式转换对 SDD21 的影响最大约 ${Math.abs(maxDelta).toFixed(2)} dB（${Number(comparison.max_delta_ghz).toFixed(2)} GHz）：忽略模式转换的经典 MM-NZC 结果在该处${direction}。PLTS 2019 及以后版本的 AFR 夹具模型包含模式转换，与 PLTS 对比时请使用“混合模 NZC + 模式转换”。`,
      );
    }
  }

  const fixtureSkews = [diagnostics.thru_a?.skew_ps, diagnostics.thru_b?.skew_ps].filter(finite);
  const dutSkew = diagnostics.dut?.skew_ps;
  if (fixtureSkews.length && finite(dutSkew) && Math.abs(dutSkew) >= SIGNIFICANT_SKEW_PS) {
    const fixtureSum = fixtureSkews.reduce((sum, value) => sum + value, 0);
    if (Math.abs(fixtureSum) >= SIGNIFICANT_SKEW_PS && Math.sign(fixtureSum) === Math.sign(dutSkew)) {
      messages.push('夹具与 DUT 的 P/N skew 同向：忽略夹具模式转换会让 DUT 的 SDD21 随频率增大而偏低。');
    }
  }
  if (finite(dutSkew) && Math.abs(dutSkew) >= SIGNIFICANT_SKEW_PS) {
    messages.push(
      `DUT 自身约有 ${Math.abs(dutSkew).toFixed(2)} ps 的 P/N skew。若 PLTS 启用了 Deskew（“2X Thru and Fixtured DUT”），PLTS 会额外去掉这部分 skew，SDD21 会比任何纯去嵌结果都高。`,
    );
  }
  return { level, messages };
}

export class ModeConversionPanel {
  constructor({ rootId = 'mc-diagnostics' } = {}) {
    this.rootId = rootId;
  }

  get root() {
    return $(this.rootId);
  }

  reset() {
    setHidden(this.root, true);
  }

  appendRow(container, label, value, { emphasis = false } = {}) {
    if (!container) return;
    const row = createElement('div', { className: `mc-diag-row${emphasis ? ' is-emphasis' : ''}` });
    row.append(createElement('dt', { text: label }), createElement('dd', { text: value }));
    container.appendChild(row);
  }

  renderPath(id, path, { twoX = false } = {}) {
    const container = $(id);
    clearChildren(container);
    if (!container) return;
    this.appendRow(container, 'P/N skew', formatSkew(path?.skew_ps));
    if (twoX && finite(path?.skew_ps)) {
      this.appendRow(container, '≈ 每个 1X 夹具', `${formatSigned(path.skew_ps / 2, 2)} ps`);
    }
    this.appendRow(
      container,
      '模式转换 max |SCD21|,|SDC21|',
      finite(path?.max_conversion_db) ? `${path.max_conversion_db.toFixed(1)} dB` : '—',
    );
  }

  renderComparison(comparison) {
    const container = $('mc-diag-compare');
    clearChildren(container);
    const title = $('mc-diag-compare-title');
    if (!comparison) {
      if (title) title.textContent = '算法对照 ΔSDD21';
      this.appendRow(container, '对照结果', '—');
      return;
    }
    if (title) title.textContent = `ΔSDD21 = ${comparison.primary_label} − ${comparison.alternative_label}`;
    (comparison.checkpoints || []).forEach((point) => {
      this.appendRow(container, `@ ${Number(point.freq_ghz).toFixed(2)} GHz`, `${formatSigned(point.delta_db, 3)} dB`);
    });
    this.appendRow(
      container,
      '最大 |Δ|',
      finite(comparison.max_delta_db)
        ? `${formatSigned(comparison.max_delta_db, 3)} dB @ ${Number(comparison.max_delta_ghz).toFixed(2)} GHz`
        : '—',
      { emphasis: true },
    );
  }

  /** 应用 /api/deembed 结果；单端或无诊断数据时隐藏面板。 */
  render(calculation) {
    const root = this.root;
    if (!root) return;
    const diagnostics = calculation?.diagnostics;
    if (!diagnostics || calculation?.nports !== 4) {
      setHidden(root, true);
      return;
    }
    this.renderPath('mc-diag-thru-a', diagnostics.thru_a, { twoX: true });
    this.renderPath('mc-diag-thru-b', diagnostics.thru_b, { twoX: true });
    this.renderPath('mc-diag-dut', diagnostics.dut);
    this.renderComparison(diagnostics.comparison);

    const note = $('mc-diagnostics-note');
    if (note) note.textContent = `当前算法：${calculation.split_algorithm_label || '—'}；对照曲线：${calculation.comparison_label || '—'}`;

    const { level, messages } = describeModeConversion(diagnostics, { primaryAlgorithm: calculation.split_algorithm });
    const hint = $('mc-diagnostics-hint');
    if (hint) {
      clearChildren(hint);
      messages.forEach((message) => hint.appendChild(createElement('p', { text: message })));
      hint.classList.toggle('is-warn', level === 'warn');
      setHidden(hint, messages.length === 0);
    }
    setHidden(root, false);
  }
}

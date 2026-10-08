/** 端口映射面板与 2X Thru 夹具诊断卡片。 */

import { SLOT_UI } from '../config/constants.js';
import { $, clearChildren, createElement } from '../core/dom.js';

const MAPPING_IDS = ['map-kind-a', 'map-kind-total', 'map-kind-b'];
const LEFT_PORT_IDS = ['map-a-outer', 'map-total-left', 'map-b-split'];
const RIGHT_PORT_IDS = ['map-a-split', 'map-total-right', 'map-b-outer'];
const NOTE_IDS = ['map-note-a', 'map-note-total', 'map-note-b'];
const MAX_LISTED_CROSSINGS = 8;

export class MappingPanel {
  constructor({ onDefaultParametersChanged } = {}) {
    this.onDefaultParametersChanged = onDefaultParametersChanged;
    this.statsPanel = $('fixture-stats');
    this.rowsA = $('fixture-stat-rows-a');
    this.rowsB = $('fixture-stat-rows-b');
  }

  setLoading() {
    MAPPING_IDS.forEach((id) => setTextById(id, '识别中…'));
    [...LEFT_PORT_IDS, ...RIGHT_PORT_IDS].forEach((id) => setTextById(id, '读取端口'));
    NOTE_IDS.forEach((id) => setTextById(id, '正在识别 Touchstone 端口映射…'));
  }

  renderFailure(message) {
    NOTE_IDS.forEach((id) => setTextById(id, `识别失败：${message}`));
  }

  /** 渲染端口映射关系（同时更新各文件默认参数与提示文案）。 */
  render(data) {
    const leftPorts = Array.isArray(data.left_ports) ? data.left_ports.join(' / ') : 'P1';
    const rightPorts = Array.isArray(data.right_ports) ? data.right_ports.join(' / ') : 'P2';
    const convention = data.nports === 2 ? 'S2P · 单端' : data.detected_mapping === 'plts' ? 'S4P · PLTS 交叉' : 'S4P · 标准顺序';

    const select = $('port-map-select');
    if (select) select.disabled = data.nports === 2;

    MAPPING_IDS.forEach((id) => setTextById(id, convention));
    setTextById('map-a-outer', leftPorts);
    setTextById('map-a-split', rightPorts);
    setTextById('map-total-left', leftPorts);
    setTextById('map-total-right', rightPorts);
    setTextById('map-b-split', leftPorts);
    setTextById('map-b-outer', rightPorts);
    setTextById('map-note-a', `外部端 ${leftPorts} → 劈半面 ${rightPorts}；取 side 1 提取左夹具`);
    setTextById('map-note-total', `Total 左侧 ${leftPorts} → 1X A → DUT → 1X B → 右侧 ${rightPorts}`);
    setTextById('map-note-b', `劈半面 ${leftPorts} → 外部端 ${rightPorts}；取 side 2 并翻转为 DUT → 外部方向`);

    const defaultParam = data.nports === 4 ? 'SDD21' : 'S21';
    const note =
      data.nports === 4 ? '支持 S11–S44 及 SDD/SCC/SCD/SDC11、12、21、22' : '支持 S11、S12、S21、S22';
    Object.values(SLOT_UI).forEach((ui) => {
      const input = $(ui.inputId);
      if (!input) return;
      const current = input.value.trim().toUpperCase();
      if (data.nports === 4 && ['S21', ''].includes(current)) input.value = defaultParam;
      if (data.nports === 2 && /^(SDD|SCC|SCD|SDC)/.test(current)) input.value = defaultParam;
      input.placeholder = defaultParam;
      input.setAttribute('aria-invalid', 'false');
      const noteElement = $(ui.noteId);
      if (noteElement) {
        noteElement.textContent = note;
        noteElement.classList.remove('is-error');
      }
    });
    this.onDefaultParametersChanged?.(data);
  }

  /** 渲染 2X Thru A/B 的差分诊断（仅 4 端口）。 */
  renderFixtureStatistics(statistics, nports) {
    if (!this.statsPanel) return;
    if (nports !== 4 || !statistics?.thru_a || !statistics?.thru_b) {
      this.statsPanel.hidden = true;
      return;
    }
    this.renderFixtureStatRows(this.rowsA, statistics.thru_a);
    this.renderFixtureStatRows(this.rowsB, statistics.thru_b);
    this.statsPanel.hidden = false;
  }

  renderFixtureStatRows(container, rules) {
    if (!container) return;
    clearChildren(container);
    (rules || []).forEach((rule) => {
      const points = (rule.points_ghz || []).map((freq) => ({ start: Number(freq), end: Number(freq), range: false }));
      const ranges = (rule.ranges_ghz || []).map(([start, end]) => ({ start: Number(start), end: Number(end), range: true }));
      const items = [...points, ...ranges]
        .filter((item) => Number.isFinite(item.start) && Number.isFinite(item.end))
        .sort((a, b) => a.start - b.start);

      const row = createElement('div', { className: 'fixture-stat-row' });
      row.append(
        createElement('span', { className: 'fixture-stat-label', text: rule.label }),
        createElement('strong', {
          className: 'fixture-stat-count',
          text: `${points.length} 个交点${ranges.length ? ` · ${ranges.length} 段重合` : ''}`,
        }),
      );

      const formatItem = (item) =>
        item.range ? `${item.start.toFixed(3)}–${item.end.toFixed(3)} GHz（连续）` : `${item.start.toFixed(3)} GHz`;
      row.appendChild(
        createElement('small', {
          className: 'fixture-stat-values',
          text: items.length ? items.slice(0, MAX_LISTED_CROSSINGS).map(formatItem).join('、') : '未找到交点',
        }),
      );

      if (items.length > MAX_LISTED_CROSSINGS) {
        const details = createElement('details', { className: 'fixture-stat-details' });
        details.append(
          createElement('summary', { text: `查看全部 ${items.length} 个交点 / 区间` }),
          createElement('small', { text: items.map(formatItem).join('、') }),
        );
        row.appendChild(details);
      }
      container.appendChild(row);
    });
  }
}

function setTextById(id, text) {
  const element = $(id);
  if (element) element.textContent = text;
}

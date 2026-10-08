/** 结果面板：指标卡片、下载按钮、网络开关与参数芯片。 */

import { DEFAULT_RESULT_NETWORKS, MAX_CHART_PARAMETERS, NETWORK_DOT_COLORS, NETWORK_LABELS } from '../config/constants.js';
import { $, clearChildren, createElement, setHidden } from '../core/dom.js';
import { formatScientific, networkLabel, sideLabel } from '../core/format.js';
import { ModeConversionPanel, NEGLIGIBLE_DELTA_DB } from './modeConversionPanel.js';

/** 结果中实际存在的网络键（优先使用接口给出的 network_keys）。 */
export function availableNetworkKeys(calculation) {
  const declared = calculation?.chart?.network_keys;
  if (Array.isArray(declared) && declared.length) return declared;
  const keys = new Set();
  Object.values(calculation?.chart?.series || {}).forEach((networks) => Object.keys(networks || {}).forEach((key) => keys.add(key)));
  return [...keys];
}

/** 对照算法曲线仅在两种算法差异明显时默认勾选，避免重叠曲线干扰阅读。 */
export function defaultNetworkChecked(key, calculation) {
  if (!DEFAULT_RESULT_NETWORKS.includes(key)) return false;
  if (key !== 'dut_alt') return true;
  const delta = calculation?.diagnostics?.comparison?.max_delta_db;
  return Number.isFinite(delta) && Math.abs(delta) >= NEGLIGIBLE_DELTA_DB;
}

export class ResultSummaryPanel {
  constructor({ state, onDownload, onSelectionChanged, onParameterChip }) {
    this.state = state;
    this.onDownload = onDownload;
    this.onSelectionChanged = onSelectionChanged;
    this.onParameterChip = onParameterChip;
    this.modeConversion = new ModeConversionPanel();
  }

  setDownloadStatus(message, isError = false) {
    const status = $('download-status');
    if (!status) return;
    status.textContent = message;
    status.classList.toggle('is-error', isError);
  }

  /** 应用 /api/deembed 返回结果（指标、下载链接、默认参数）。 */
  render(data) {
    const extension = data.nports === 4 ? 's4p' : 's2p';
    const downloads = [
      ['download-dut', 'dut', `DUT_deembedded.${extension}`],
      ['download-a', 'fix_a', `Fixture_A_1X.${extension}`],
      ['download-b', 'fix_b', `Fixture_B_1X.${extension}`],
    ];
    const altLink = $('download-alt');
    if (data.comparison_algorithm) {
      downloads.push(['download-alt', 'dut_alt', `DUT_deembedded_${data.comparison_algorithm}.${extension}`]);
      const label = altLink?.querySelector('b');
      if (label) label.textContent = `DUT · ${data.comparison_label || '对照算法'}`;
    }
    setHidden(altLink, !data.comparison_algorithm);
    downloads.forEach(([id, networkKey, filename]) => {
      const link = $(id);
      if (!link) return;
      link.download = filename;
      link.href = data.result_token ? this.downloadUrl(data.result_token, networkKey) : '#';
      const small = link.querySelector('small');
      if (small) small.textContent = `.${extension}`;
      link.dataset.networkKey = networkKey;
      link.dataset.filename = filename;
    });

    const setText = (id, text) => {
      const element = $(id);
      if (element) element.textContent = text;
    };
    setText('metric-topology', data.topology);
    setText('metric-frequency', `${data.frequency_start_ghz.toFixed(3)}–${data.frequency_stop_ghz.toFixed(3)} GHz`);
    setText('metric-points', `${data.points.toLocaleString('en-US')} 个共同频点 · Z₀ ${data.reference_z0} Ω`);
    setText(
      'result-summary',
      `${sideLabel(data.side)}${data.port_mapping ? ` · ${data.port_mapping === 'plts' ? 'PLTS 交叉映射' : '标准顺序映射'}` : ''}${
        data.split_algorithm_label ? ` · ${data.split_algorithm_label}` : ''
      }`,
    );

    const quality = data.quality || {};
    const passCard = $('quality-card');
    const recipCard = $('reciprocity-card');
    [passCard, recipCard].forEach((card) => card?.classList.remove('quality-pass', 'quality-warn', 'quality-fail'));
    passCard?.classList.add(quality.passivity_pass ? 'quality-pass' : 'quality-fail');
    recipCard?.classList.add(quality.reciprocity_pass ? 'quality-pass' : 'quality-warn');
    setText(
      'metric-passivity',
      Number.isFinite(quality.max_singular_value) ? `σmax ${quality.max_singular_value.toFixed(4)}` : '—',
    );
    setText('metric-passivity-note', quality.passivity_pass ? 'PASS · ≤ 1.005 容差' : 'CHECK · 高于无源性容差');
    setText('metric-reciprocity', formatScientific(quality.reciprocity_error));
    const recipNote = document.querySelector('#reciprocity-card small');
    if (recipNote) recipNote.textContent = quality.reciprocity_pass ? 'PASS · max |Sij − Sji|' : 'CHECK · max |Sij − Sji|';

    const initial = data.nports === 4 ? 'SDD21' : 'S21';
    const field = $('chart-params');
    if (field) {
      field.value = initial;
      field.setAttribute('aria-invalid', 'false');
    }
    const error = $('chart-param-error');
    if (error) error.textContent = '';

    this.buildParameterChips(data.nports);
    this.buildNetworkToggles(data);
    this.modeConversion.render(data);
    return initial;
  }

  buildNetworkToggles(calculation = this.state?.calculation) {
    const container = $('network-toggles');
    if (!container) return;
    clearChildren(container);
    const available = new Set(availableNetworkKeys(calculation));
    Object.keys(NETWORK_LABELS).forEach((key) => {
      if (available.size && !available.has(key)) return;
      const wrapper = createElement('label', { className: 'network-toggle' });
      const input = createElement('input', { attrs: { type: 'checkbox' } });
      input.dataset.network = key;
      input.checked = defaultNetworkChecked(key, calculation);
      const dot = createElement('i', { className: 'network-color' });
      dot.style.background = NETWORK_DOT_COLORS[key];
      wrapper.append(input, dot, document.createTextNode(networkLabel(key, calculation)));
      input.addEventListener('change', () => this.onSelectionChanged?.());
      container.appendChild(wrapper);
    });
  }

  buildParameterChips(nports) {
    const container = $('param-chips');
    if (!container) return;
    const suggestions = nports === 2 ? ['S21', 'S11', 'S12', 'S22'] : ['SDD21', 'SDD11', 'SCD21', 'SCC21', 'S21'];
    clearChildren(container);
    suggestions.slice(0, MAX_CHART_PARAMETERS).forEach((code) => {
      const button = createElement('button', { className: 'param-chip', text: code, attrs: { type: 'button' } });
      button.addEventListener('click', () => this.onParameterChip?.(code));
      container.appendChild(button);
    });
  }

  selectedNetworkKeys() {
    return [...document.querySelectorAll('#network-toggles input[data-network]:checked')].map((input) => input.dataset.network);
  }

  attachDownloads() {
    ['download-dut', 'download-a', 'download-b', 'download-alt'].forEach((id) => {
      const link = $(id);
      link?.addEventListener('click', (event) => this.handleDownload(event, link.dataset.networkKey, link.dataset.filename));
    });
  }

  handleDownload(event, networkKey, filename) {
    const calculation = this.state.calculation;
    if (!calculation) {
      event.preventDefault();
      this.setDownloadStatus('没有可下载的计算结果。', true);
      return;
    }
    if (!calculation.result_token) {
      event.preventDefault();
      const inline = calculation[`${networkKey}_touchstone`];
      if (inline) {
        this.onDownload?.(filename, inline);
        this.setDownloadStatus(`已请求下载 ${filename}`);
        return;
      }
      this.setDownloadStatus('本次结果的临时下载缓存已过期，请重新运行去嵌。', true);
      return;
    }
    // 直接让 <a download> 触发下载，保持用户手势内的附件请求。
    this.setDownloadStatus(`已请求下载 ${filename}`);
  }

  downloadUrl(token, networkKey) {
    return this.onDownloadUrl ? this.onDownloadUrl(token, networkKey) : `/api/download/${encodeURIComponent(token)}/${networkKey}`;
  }
}

/** 用隐藏的 <a> 触发内联文本下载（缓存过期时的兜底路径）。 */
export function saveTextBlob(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

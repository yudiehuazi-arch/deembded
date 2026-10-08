/**
 * Workbench —— 应用组合根（Composition Root）。
 *
 * 只做三件事：
 * 1. 创建并连接状态、接口客户端与各视图控制器；
 * 2. 编排“选择文件 → 识别 → 去嵌 → 展示结果”的主流程；
 * 3. 把跨模块的界面反馈汇总到状态栏。
 *
 * 具体图表的绘制与请求细节由 :class:`InputChartController` /
 * :class:`ResultChartController` 负责，端口映射、快捷参数与结果摘要
 * 各自封装在对应的面板类里。
 */

import { DEFAULT_SPLIT_ALGORITHM, SLOT_UI } from './config/constants.js';
import { ApiError, DeembedApi } from './core/api.js';
import { $, setHidden } from './core/dom.js';
import { WorkbenchState } from './core/state.js';
import { InputChartController } from './controllers/inputChartController.js';
import { ResultChartController } from './controllers/resultChartController.js';
import { MappingPanel } from './ui/mappingPanel.js';
import { QuickParameterController } from './ui/quickParams.js';
import { ResultSummaryPanel, saveTextBlob } from './ui/resultSummary.js';
import { StatusPanel } from './ui/statusPanel.js';
import { UploadPanel } from './ui/uploadPanel.js';

export class Workbench {
  constructor({ api = new DeembedApi(), state = new WorkbenchState() } = {}) {
    this.api = api;
    this.state = state;
    this.status = new StatusPanel();
    this.resultPanel = $('result-panel');
    this.fileTools = $('file-tools');
    this.runButton = $('btn-run');

    this.uploads = new UploadPanel({
      onFileSelected: (slot, file) => this.handleFileSelected(slot, file),
      onInvalidFile: (file) =>
        this.status.set('error', '文件格式不支持', `${file.name} 不是 Touchstone 文件。请使用 .s2p 或 .s4p 格式。`),
    });

    this.mapping = new MappingPanel({ onDefaultParametersChanged: (data) => this.refreshParameterWidgets(data) });

    this.quickParams = new QuickParameterController({
      state: this.state,
      onFieldChanged: (slot, options) => {
        if (options?.submit) this.inputChart.showCombined();
        else this.mapping.renderFixtureStatistics(this.state.inspection?.fixture_statistics, this.state.inspection?.nports);
      },
    });

    this.summary = new ResultSummaryPanel({
      state: this.state,
      onDownload: (filename, text) => saveTextBlob(filename, text),
      onDownloadUrl: (token, key) => this.api.downloadUrl(token, key),
      onSelectionChanged: () => this.resultChart.onNetworkSelectionChanged(),
      onParameterChip: (code) => this.resultChart.appendParameter(code),
    });

    this.inputChart = new InputChartController({
      api: this.api,
      state: this.state,
      report: (kind, title, detail, tag) => this.status.set(kind, title, detail, tag),
      readPortMapping: () => $('port-map-select')?.value || 'auto',
      readReferenceZ0: () => $('z0-input')?.value || '50',
    });

    this.resultChart = new ResultChartController({
      api: this.api,
      state: this.state,
      readNetworkKeys: () => this.summary.selectedNetworkKeys(),
    });
  }

  // ------------------------------------------------------------------ 装配
  mount() {
    this.uploads.attach();
    this.quickParams.attach();
    this.summary.attachDownloads();
    this.inputChart.attach();
    this.resultChart.attach();

    $('btn-run')?.addEventListener('click', () => this.runDeembed());
    $('btn-clear')?.addEventListener('click', () => this.clearAll());
    $('port-map-select')?.addEventListener('change', () => this.onPortMappingChanged());
    $('side-select')?.addEventListener('change', () =>
      this.notifySettingChanged('去嵌范围已更改', '请重新运行去嵌，以更新 DUT 结果和下载文件。'),
    );
    $('z0-input')?.addEventListener('change', () => {
      this.notifySettingChanged('参考阻抗已更改', '请重新运行去嵌，以按新的 Z₀ 重新归一化并计算。');
      this.inputChart.reloadTdrIfActive();
    });
    $('split-algorithm-select')?.addEventListener('change', () =>
      this.notifySettingChanged('差分劈半算法已更改', '请重新运行去嵌；另一种算法的结果会作为对照曲线保留在结果图中。'),
    );
    window.addEventListener('resize', () => {
      this.resultChart.draw();
      this.inputChart.draw();
    });

    this.status.set('ready', '等待输入文件', '选择 Total、2X Thru A 与 2X Thru B 后，即可运行计算。', 'READY');
  }

  // -------------------------------------------------------------- 文件识别
  handleFileSelected(slot, file) {
    this.state.setFile(slot, file);
    this.inputChart.invalidate();
    this.resultChart.invalidateTdr();
    setHidden(this.resultPanel, true);

    if (this.state.allFilesSelected()) {
      setHidden(this.fileTools, false);
      this.mapping.setLoading();
      this.inspectSelectedFiles();
      return;
    }
    setHidden(this.fileTools, true);
    this.status.set('ready', `${SLOT_UI[slot].label} 已载入`, '继续添加另外两个 Touchstone 文件。', 'INPUT');
  }

  async inspectSelectedFiles() {
    if (!this.state.allFilesSelected()) return;
    const generation = this.state.nextInspectionGeneration();
    const cachedToken = this.state.inspection?.inspection_token;
    this.state.inspection = null;
    this.inputChart.invalidate();
    this.mapping.setLoading();
    if (!this.state.calculationBusy) {
      this.status.set(
        'busy',
        '正在识别端口映射',
        cachedToken ? '复用已解析网络数据，快速刷新端口映射。' : '读取三份 Touchstone 的端口数与共同频段。',
        'INSPECT',
      );
    }

    try {
      const data = await this.inspectWithFallback(cachedToken);
      if (generation !== this.state.inspectionGeneration) return;
      this.state.inspection = data;
      this.mapping.render(data);
      this.syncSplitAlgorithmControl(data.nports);
      if (this.state.calculationBusy) return;
      if (this.state.mappingRecalcNeeded && this.state.calculation) {
        this.status.set('ready', '映射图已更新', '当前去嵌结果仍使用旧端口映射，请重新运行计算。', 'RE-RUN');
      } else {
        this.status.set(
          'ready',
          '三个文件已识别',
          `${data.topology} · ${data.mapping_label} · 共同频段 ${data.frequency_start_ghz.toFixed(3)}–${data.frequency_stop_ghz.toFixed(3)} GHz`,
          'READY',
        );
      }
    } catch (error) {
      if (generation !== this.state.inspectionGeneration) return;
      this.mapping.renderFailure(error.message);
      if (!this.state.calculationBusy) {
        this.status.set('error', '文件识别失败', error.message || '无法读取这些 Touchstone 文件，请检查格式和端口数。');
      }
    }
  }

  /** 识别请求：缓存 token 过期（410）时自动带原文件重传一次。 */
  async inspectWithFallback(cachedToken) {
    const portMapping = $('port-map-select')?.value || 'auto';
    try {
      return await this.api.inspect({ files: this.state.files, portMapping, token: cachedToken });
    } catch (error) {
      if (error instanceof ApiError && error.status === 410 && cachedToken) {
        return this.api.inspect({ files: this.state.files, portMapping, token: null });
      }
      throw error;
    }
  }

  refreshParameterWidgets(data) {
    const nports = data?.nports ?? this.state.inspection?.nports ?? 2;
    const previews = data?.file_previews || this.state.inspection?.file_previews;
    const statistics = data?.fixture_statistics ?? this.state.inspection?.fixture_statistics ?? null;
    this.quickParams.render(nports, previews);
    this.mapping.renderFixtureStatistics(statistics, nports);
  }

  // -------------------------------------------------------------- 去嵌计算
  async runDeembed() {
    if (!this.state.allFilesSelected()) {
      this.status.set('error', '还缺少输入文件', '请分别添加 Total、2X Thru A 与 2X Thru B。');
      return;
    }
    const referenceZ0 = Number($('z0-input')?.value);
    if (!Number.isFinite(referenceZ0) || referenceZ0 <= 0) {
      this.status.set('error', '参考阻抗无效', '请输入大于 0 的 Z₀ 数值。');
      return;
    }

    const cachedToken = this.state.inspection?.inspection_token || null;
    const side = $('side-select')?.value || 'both';
    const portMapping = $('port-map-select')?.value || 'auto';
    const splitAlgorithm = this.readSplitAlgorithm();

    this.setBusy(true);
    this.status.set(
      'busy',
      '正在劈半并去嵌',
      cachedToken ? '复用已识别的网络数据，直接提取夹具并计算 DUT S 参数。' : '对齐共同频段、提取左右 1X 夹具并计算 DUT S 参数。',
      'RUNNING',
    );

    try {
      const data = await this.deembedWithFallback({ cachedToken, side, portMapping, referenceZ0, splitAlgorithm });
      this.updateResults(data);
      this.status.set('success', '去嵌完成', `${data.message} · ${data.points.toLocaleString('en-US')} 个共同频点。`, 'DONE');
    } catch (error) {
      this.status.set('error', '计算失败', error.message || '服务器暂时不可用，请检查文件后重试。');
    } finally {
      this.setBusy(false);
    }
  }

  async deembedWithFallback({ cachedToken, side, portMapping, referenceZ0, splitAlgorithm = DEFAULT_SPLIT_ALGORITHM }) {
    try {
      return await this.api.deembed({ token: cachedToken, side, portMapping, referenceZ0, splitAlgorithm });
    } catch (error) {
      if (error instanceof ApiError && error.status === 410 && cachedToken) {
        return this.api.deembed({ files: this.state.files, side, portMapping, referenceZ0, splitAlgorithm });
      }
      throw error;
    }
  }

  readSplitAlgorithm() {
    return $('split-algorithm-select')?.value || DEFAULT_SPLIT_ALGORITHM;
  }

  /** 劈半算法只影响差分 S4P；单端 S2P 时禁用选择框。 */
  syncSplitAlgorithmControl(nports) {
    const select = $('split-algorithm-select');
    if (!select) return;
    const singleEnded = nports === 2;
    select.disabled = singleEnded;
    select.title = singleEnded ? '单端 S2P 始终使用 IEEE 370 SE-NZC 劈半' : '';
  }

  setBusy(busy) {
    this.state.calculationBusy = busy;
    if (!this.runButton) return;
    this.runButton.disabled = busy;
    const label = this.runButton.querySelector('span:last-child');
    if (label) label.textContent = busy ? '计算中…' : '开始去嵌';
  }

  /** 去嵌结果 → 摘要面板 + 结果图表 + 端口映射回填。 */
  updateResults(data) {
    this.state.calculation = data;
    this.state.mappingRecalcNeeded = false;
    this.summary.setDownloadStatus('');

    const initialParameter = this.summary.render(data);
    const mappingInfo = {
      nports: data.nports,
      topology: data.topology,
      detected_mapping: data.port_mapping || 'single-ended',
      left_ports: data.left_ports,
      right_ports: data.right_ports,
      mapping_label: data.mapping_label,
      frequency_start_ghz: data.frequency_start_ghz,
      frequency_stop_ghz: data.frequency_stop_ghz,
      points: data.points,
    };
    this.state.inspection = { ...(this.state.inspection || {}), ...mappingInfo };
    this.mapping.render(mappingInfo);

    this.resultChart.update([initialParameter]);
    setHidden(this.resultPanel, false);
    this.resultChart.draw();
  }

  // ---------------------------------------------------------------- 其它
  onPortMappingChanged() {
    const hasCalculatedDiff = Boolean(this.state.calculation && this.state.calculation.nports === 4);
    if (hasCalculatedDiff) this.state.mappingRecalcNeeded = true;
    if (this.state.allFilesSelected()) this.inspectSelectedFiles();
    if (hasCalculatedDiff) {
      this.status.set('ready', '端口映射已切换', '映射关系与输入图表将刷新；当前去嵌结果仍使用旧映射，请重新运行计算。', 'RE-RUN');
    }
  }

  notifySettingChanged(title, detail) {
    if (this.state.calculation && !this.state.calculationBusy) this.status.set('ready', title, detail, 'RE-RUN');
  }

  clearAll() {
    this.state.reset();
    this.uploads.clearAll();
    Object.values(SLOT_UI).forEach((ui) => {
      const input = $(ui.inputId);
      if (input) {
        input.value = 'S21';
        input.setAttribute('aria-invalid', 'false');
      }
    });
    this.inputChart.reset();
    this.resultChart.reset();
    this.summary.modeConversion.reset();
    this.syncSplitAlgorithmControl(null);
    setHidden(this.resultPanel, true);
    setHidden(this.fileTools, true);
    this.summary.setDownloadStatus('');
    this.status.set('ready', '等待输入文件', '选择 Total、2X Thru A 与 2X Thru B 后，即可运行计算。', 'READY');
  }
}

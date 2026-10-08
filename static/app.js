const fileInputs = {
  thru_a: document.getElementById('file-thru-a'),
  total: document.getElementById('file-total'),
  thru_b: document.getElementById('file-thru-b'),
};
const files = { thru_a: null, total: null, thru_b: null };
let calculation = null;
let lastInspection = null;
let activeParameters = ['S21'];
let inputChartState = null;
let inspectionGeneration = 0;
let calculationBusy = false;
let mappingRecalcNeeded = false;

const statusPanel = document.getElementById('status-panel');
const statusTitle = document.getElementById('status-title');
const statusDetail = document.getElementById('status-detail');
const statusTag = document.getElementById('status-tag');
const runButton = document.getElementById('btn-run');
const resultPanel = document.getElementById('result-panel');
const canvas = document.getElementById('chart-canvas');
const inputCanvas = document.getElementById('input-chart-canvas');
const tooltip = document.getElementById('chart-tooltip');
const resultChartCrosshair = document.getElementById('result-chart-crosshair');
const resultChartPoints = document.getElementById('result-chart-points');
const resultChartView = document.getElementById('result-chart-view');
const resultTdrControls = document.getElementById('result-tdr-controls');
let resultChartMode = 'sparam';
let resultTdrData = null;
let resultTdrRequestId = 0;
let resultChartHoverFraction = null;
let resultChartHoverYFraction = 0.25;
let resultChartMarkerPinned = false;
let resultChartYLimits = { min: null, max: null };
const fileTools = document.getElementById('file-tools');
const inputChartPanel = document.getElementById('input-chart-panel');
const inputChartView = document.getElementById('input-chart-view');
const inputTdrControls = document.getElementById('input-tdr-controls');
let inputChartMode = 'sparam';
let inputTdrData = null;
let inputTdrRequestId = 0;
const inputChartWrap = document.getElementById('input-chart-wrap');
const inputChartXMarker = document.getElementById('input-chart-x-marker');
const inputChartXMarkerLabel = document.getElementById('input-chart-x-marker-label');
const inputChartPointMarkers = document.getElementById('input-chart-point-markers');
const inputChartHoverReadout = document.getElementById('input-chart-hover-readout');
const fixtureStatsPanel = document.getElementById('fixture-stats');
let inputChartHoverFraction = null;
let inputChartHoverYFraction = 0.25;
let inputChartMarkerPinned = false;
let inputChartYLimits = { min: null, max: null };

const slotUi = {
  thru_a: { statusId: 'status-thru-a', cardId: 'card-thru-a', label: '2X Thru A', inputId: 'input-param-thru-a', noteId: 'param-note-thru-a', chartLabel: '2X Thru A' },
  total: { statusId: 'status-total', cardId: 'card-total', label: 'Total', inputId: 'input-param-total', noteId: 'param-note-total', chartLabel: 'Total Network' },
  thru_b: { statusId: 'status-thru-b', cardId: 'card-thru-b', label: '2X Thru B', inputId: 'input-param-thru-b', noteId: 'param-note-thru-b', chartLabel: '2X Thru B' },
};
const networkLabels = { total: 'Total', dut: 'DUT 去嵌', fix_a: '1X A', fix_b: '1X B', thru_a: '2X A', thru_b: '2X B' };
const networkDash = { total: [6, 4], dut: [], fix_a: [2, 3], fix_b: [8, 3, 2, 3], thru_a: [4, 2], thru_b: [1, 4] };
const parameterColors = ['#54e1d2', '#f3b55f', '#7aaeff', '#e987ba', '#bd93f9', '#a3e635', '#ff8e6b', '#5bc0eb'];
const networkColorDots = { total: '#91a5b8', dut: '#54e1d2', fix_a: '#67c98f', fix_b: '#f3b55f', thru_a: '#7aaeff', thru_b: '#e987ba' };
const inputTdrColors = { total: '#7aaeff', thru_a: '#54e1d2', thru_b: '#f3b55f' };
const inputTdrNetworkOrder = ['thru_a', 'total', 'thru_b'];
const inputTdrNetworkLabels = { thru_a: '2X Thru A', total: 'Total', thru_b: '2X Thru B' };
const inputParameterDashes = [[], [6, 3], [2, 3], [8, 3, 2, 3], [1, 3], [6, 2, 1, 2], [9, 2], [3, 1]];
const MAX_CHART_PARAMETERS = 8;
const QUICK_PARAM_STORAGE_KEY = 'rf-deembed-custom-quick-parameters-v1';
const defaultQuickParameters = {
  2: ['S11', 'S21', 'S12', 'S22'],
  4: ['SDD11', 'SDD21', 'SCD21', 'SCC21', 'SDC21', 'S11', 'S21'],
};
let customQuickParameters = loadSavedQuickParameters();

function setStatus(kind, title, detail, tag) {
  statusPanel.classList.remove('status-error', 'status-success', 'is-busy');
  if (kind === 'error') statusPanel.classList.add('status-error');
  if (kind === 'success') statusPanel.classList.add('status-success');
  if (kind === 'busy') statusPanel.classList.add('is-busy');
  statusTitle.textContent = title;
  statusDetail.textContent = detail;
  statusTag.textContent = tag || (kind === 'busy' ? 'RUNNING' : kind === 'success' ? 'DONE' : kind === 'error' ? 'ERROR' : 'READY');
}
function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}
function formatScientific(value) {
  if (!Number.isFinite(value)) return '—';
  return value === 0 ? '0' : value.toExponential(2);
}
function sideLabel(side) {
  return ({ both: '双边去嵌', left: '仅去除左夹具 A', right: '仅去除右夹具 B' })[side] || side;
}
function loadSavedQuickParameters() {
  try {
    const value = JSON.parse(localStorage.getItem(QUICK_PARAM_STORAGE_KEY) || '[]');
    if (!Array.isArray(value)) return [];
    return [...new Set(value.map((item) => String(item).trim().toUpperCase()).filter((item) => /^(?:S[1-4][1-4]|S(?:DD|CC|CD|DC)(?:11|12|21|22))$/.test(item)))].slice(0, 32);
  } catch (_) {
    return [];
  }
}
function saveQuickParameters() {
  try { localStorage.setItem(QUICK_PARAM_STORAGE_KEY, JSON.stringify(customQuickParameters)); } catch (_) { /* Storage can be unavailable in private or sandboxed contexts. */ }
}
function splitParameterCodes(value) {
  return [...new Set(String(value || '').toUpperCase().split(/[\s,;，；]+/).map((code) => code.trim()).filter(Boolean))];
}
function quickParamSlug(slot) { return slot.replaceAll('_', '-'); }
function setQuickCustomMessage(slot, message, isError = false) {
  const messageElement = document.getElementById(`quick-custom-message-${quickParamSlug(slot)}`);
  if (!messageElement) return;
  messageElement.textContent = message;
  messageElement.classList.toggle('is-error', isError);
}

function setFile(slot, file) {
  if (!file) return;
  if (!/\.(s2p|s4p|snp|ts|txt)$/i.test(file.name)) {
    setStatus('error', '文件格式不支持', `${file.name} 不是 Touchstone 文件。请使用 .s2p 或 .s4p 格式。`);
    return;
  }
  files[slot] = file;
  calculation = null;
  mappingRecalcNeeded = false;
  lastInspection = null;
  inputChartState = null;
  inputTdrRequestId++; inputTdrData = null; resultTdrRequestId++; resultTdrData = null;
  resultPanel.hidden = true;
  inputChartPanel.hidden = true;
  const ui = slotUi[slot];
  const status = document.getElementById(ui.statusId);
  status.querySelector('.file-status-text').textContent = `${file.name} · ${formatSize(file.size)}`;
  document.getElementById(ui.cardId).classList.add('has-file');
  if (Object.values(files).every(Boolean)) {
    fileTools.hidden = false;
    setMappingLoading();
    inspectSelectedFiles();
  } else {
    fileTools.hidden = true;
    setStatus('ready', `${ui.label} 已载入`, '继续添加另外两个 Touchstone 文件。', 'INPUT');
  }
}

function setMappingLoading() {
  ['map-kind-a', 'map-kind-total', 'map-kind-b'].forEach((id) => { document.getElementById(id).textContent = '识别中…'; });
  ['map-a-outer', 'map-total-left', 'map-b-split'].forEach((id) => { document.getElementById(id).textContent = '读取端口'; });
  ['map-a-split', 'map-total-right', 'map-b-outer'].forEach((id) => { document.getElementById(id).textContent = '读取端口'; });
  ['map-note-a', 'map-note-total', 'map-note-b'].forEach((id) => { document.getElementById(id).textContent = '正在识别 Touchstone 端口映射…'; });
}

Object.entries(fileInputs).forEach(([slot, input]) => input.addEventListener('change', (event) => setFile(slot, event.target.files?.[0])));
document.querySelectorAll('.choose-file-btn').forEach((button) => button.addEventListener('click', () => document.getElementById(button.dataset.for).click()));
document.querySelectorAll('.upload-card').forEach((card) => {
  card.addEventListener('dragover', (event) => { event.preventDefault(); card.classList.add('drag-over'); });
  card.addEventListener('dragleave', (event) => { if (!card.contains(event.relatedTarget)) card.classList.remove('drag-over'); });
  card.addEventListener('drop', (event) => { event.preventDefault(); card.classList.remove('drag-over'); setFile(card.dataset.slot, event.dataTransfer?.files?.[0]); });
});

function renderFileMapping(data) {
  const leftPorts = Array.isArray(data.left_ports) ? data.left_ports.join(' / ') : 'P1';
  const rightPorts = Array.isArray(data.right_ports) ? data.right_ports.join(' / ') : 'P2';
  const convention = data.nports === 2 ? 'S2P · 单端' : (data.detected_mapping === 'plts' ? 'S4P · PLTS 交叉' : 'S4P · 标准顺序');
  document.getElementById('port-map-select').disabled = data.nports === 2;
  ['map-kind-a', 'map-kind-total', 'map-kind-b'].forEach((id) => { document.getElementById(id).textContent = convention; });
  document.getElementById('map-a-outer').textContent = leftPorts;
  document.getElementById('map-a-split').textContent = rightPorts;
  document.getElementById('map-total-left').textContent = leftPorts;
  document.getElementById('map-total-right').textContent = rightPorts;
  document.getElementById('map-b-split').textContent = leftPorts;
  document.getElementById('map-b-outer').textContent = rightPorts;
  document.getElementById('map-note-a').textContent = `外部端 ${leftPorts} → 劈半面 ${rightPorts}；取 side 1 提取左夹具`;
  document.getElementById('map-note-total').textContent = `Total 左侧 ${leftPorts} → 1X A → DUT → 1X B → 右侧 ${rightPorts}`;
  document.getElementById('map-note-b').textContent = `劈半面 ${leftPorts} → 外部端 ${rightPorts}；取 side 2 并翻转为 DUT → 外部方向`;
  const defaultParam = data.nports === 4 ? 'SDD21' : 'S21';
  const note = data.nports === 4
    ? '支持 S11–S44 及 SDD/SCC/SCD/SDC11、12、21、22'
    : '支持 S11、S12、S21、S22';
  Object.values(slotUi).forEach((ui) => {
    const input = document.getElementById(ui.inputId);
    if (data.nports === 4 && ['S21', ''].includes(input.value.trim().toUpperCase())) input.value = defaultParam;
    if (data.nports === 2 && /^(SDD|SCC|SCD|SDC)/i.test(input.value.trim())) input.value = defaultParam;
    input.placeholder = defaultParam;
    const noteEl = document.getElementById(ui.noteId);
    noteEl.textContent = note;
    noteEl.classList.remove('is-error');
    input.setAttribute('aria-invalid', 'false');
  });
  renderQuickParameterButtons(data.nports, data.file_previews || lastInspection?.file_previews);
  renderFixtureStatistics(data.fixture_statistics || lastInspection?.fixture_statistics, data.nports);
}

function renderFixtureStatistics(statistics, nports) {
  const panel = fixtureStatsPanel;
  const rowsA = document.getElementById('fixture-stat-rows-a');
  const rowsB = document.getElementById('fixture-stat-rows-b');
  if (!panel || !rowsA || !rowsB) return;
  if (nports !== 4 || !statistics?.thru_a || !statistics?.thru_b) {
    panel.hidden = true;
    return;
  }
  renderFixtureStatRows(rowsA, statistics.thru_a);
  renderFixtureStatRows(rowsB, statistics.thru_b);
  panel.hidden = false;
}
function renderFixtureStatRows(container, rules) {
  container.innerHTML = '';
  rules.forEach((rule) => {
    const points = (rule.points_ghz || []).map((freq) => ({ start: Number(freq), end: Number(freq), range: false }));
    const ranges = (rule.ranges_ghz || []).map(([start, end]) => ({ start: Number(start), end: Number(end), range: true }));
    const items = [...points, ...ranges].filter((item) => Number.isFinite(item.start) && Number.isFinite(item.end)).sort((a, b) => a.start - b.start);
    const row = document.createElement('div'); row.className = 'fixture-stat-row';
    const label = document.createElement('span'); label.className = 'fixture-stat-label'; label.textContent = rule.label;
    const count = document.createElement('strong'); count.className = 'fixture-stat-count';
    count.textContent = `${points.length} 个交点${ranges.length ? ` · ${ranges.length} 段重合` : ''}`;
    row.append(label, count);
    const formatItem = (item) => item.range
      ? `${item.start.toFixed(3)}–${item.end.toFixed(3)} GHz（连续）`
      : `${item.start.toFixed(3)} GHz`;
    const summary = document.createElement('small'); summary.className = 'fixture-stat-values';
    summary.textContent = items.length ? items.slice(0, 8).map(formatItem).join('、') : '未找到交点';
    row.appendChild(summary);
    if (items.length > 8) {
      const details = document.createElement('details'); details.className = 'fixture-stat-details';
      const summaryAll = document.createElement('summary'); summaryAll.textContent = `查看全部 ${items.length} 个交点 / 区间`;
      const fullList = document.createElement('small'); fullList.textContent = items.map(formatItem).join('、');
      details.append(summaryAll, fullList); row.appendChild(details);
    }
    container.appendChild(row);
  });
}

function renderQuickParameterButtons(nports, previews = lastInspection?.file_previews) {
  const presets = defaultQuickParameters[nports] || [];
  Object.entries(slotUi).forEach(([slot, ui]) => {
    const container = document.getElementById(`quick-params-${quickParamSlug(slot)}`);
    const field = document.getElementById(ui.inputId);
    if (!container || !field) return;
    container.innerHTML = '';
    const available = new Set(Object.keys(previews?.[slot]?.series || {}));
    const codes = [...new Set([...presets, ...customQuickParameters])].filter((code) => available.has(code));
    const selected = new Set(splitParameterCodes(field.value));
    codes.forEach((code) => {
      const isCustom = customQuickParameters.includes(code) && !presets.includes(code);
      const wrapper = isCustom ? document.createElement('span') : container;
      if (isCustom) wrapper.className = 'quick-param-custom';
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = `quick-param-chip${selected.has(code) ? ' is-active' : ''}`;
      chip.dataset.quickParam = code;
      chip.setAttribute('aria-pressed', String(selected.has(code)));
      chip.title = selected.has(code) ? '点击移除该参数' : '点击添加该参数';
      chip.textContent = code;
      chip.addEventListener('click', () => toggleInputParameter(slot, code));
      wrapper.appendChild(chip);
      if (isCustom) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'quick-param-remove';
        remove.textContent = '×';
        remove.title = `移除自定义快捷项 ${code}`;
        remove.setAttribute('aria-label', `移除自定义快捷项 ${code}`);
        remove.addEventListener('click', () => removeCustomQuickParameter(slot, code));
        wrapper.appendChild(remove);
        container.appendChild(wrapper);
      }
    });
  });
}
function updateQuickParameterSelection(slot) {
  const container = document.getElementById(`quick-params-${quickParamSlug(slot)}`);
  const field = document.getElementById(slotUi[slot]?.inputId);
  if (!container || !field) return;
  const selected = new Set(splitParameterCodes(field.value));
  container.querySelectorAll('.quick-param-chip').forEach((chip) => {
    const active = selected.has(chip.dataset.quickParam);
    chip.classList.toggle('is-active', active);
    chip.setAttribute('aria-pressed', String(active));
    chip.title = active ? '点击移除该参数' : '点击添加该参数';
  });
}
function toggleInputParameter(slot, code) {
  const ui = slotUi[slot];
  const field = document.getElementById(ui?.inputId);
  if (!field) return;
  const codes = splitParameterCodes(field.value);
  const existingIndex = codes.indexOf(code);
  if (existingIndex >= 0) codes.splice(existingIndex, 1);
  else {
    if (codes.length >= MAX_CHART_PARAMETERS) {
      const note = document.getElementById(ui.noteId);
      if (note) { note.textContent = `每张图最多绘制 ${MAX_CHART_PARAMETERS} 条曲线；请先移除一项。`; note.classList.add('is-error'); }
      return;
    }
    codes.push(code);
  }
  field.value = codes.join(', ');
  field.setAttribute('aria-invalid', 'false');
  const note = document.getElementById(ui.noteId);
  if (note) note.classList.remove('is-error');
  field.dispatchEvent(new Event('input', { bubbles: true }));
}
function toggleCustomQuickEditor(slot) {
  const slug = quickParamSlug(slot);
  const editor = document.getElementById(`quick-custom-editor-${slug}`);
  const field = document.getElementById(`quick-custom-input-${slug}`);
  const toggle = document.querySelector(`.quick-custom-toggle[data-custom-slot="${slot}"]`);
  if (!editor) return;
  editor.hidden = !editor.hidden;
  if (toggle) toggle.setAttribute('aria-expanded', String(!editor.hidden));
  setQuickCustomMessage(slot, '');
  if (!editor.hidden) field?.focus();
}
function addCustomQuickParameter(slot) {
  const slug = quickParamSlug(slot);
  const field = document.getElementById(`quick-custom-input-${slug}`);
  if (!field) return;
  const code = field.value.trim().toUpperCase();
  if (!code) { setQuickCustomMessage(slot, '请输入一个 S 参数，例如 SDD21。', true); return; }
  if (!/^(?:S[1-4][1-4]|S(?:DD|CC|CD|DC)(?:11|12|21|22))$/.test(code)) {
    setQuickCustomMessage(slot, '格式无效，例如 S43、SDD21 或 SCD21。', true); return;
  }
  const available = new Set(Object.keys(lastInspection?.file_previews?.[slot]?.series || {}));
  if (!available.has(code)) { setQuickCustomMessage(slot, `当前文件不支持 ${code}。`, true); return; }
  if ((defaultQuickParameters[lastInspection?.nports] || []).includes(code)) {
    setQuickCustomMessage(slot, `${code} 已在默认快捷项中。`); return;
  }
  if (customQuickParameters.includes(code)) {
    setQuickCustomMessage(slot, `${code} 已存在于自定义快捷项中。`); return;
  }
  if (customQuickParameters.length >= 32) { setQuickCustomMessage(slot, '自定义快捷项最多保存 32 个。', true); return; }
  customQuickParameters.push(code);
  saveQuickParameters();
  renderQuickParameterButtons(lastInspection?.nports, lastInspection?.file_previews);
  field.value = '';
  setQuickCustomMessage(slot, `${code} 已添加；点击快捷项即可加入或移出图表。`);
}
function removeCustomQuickParameter(slot, code) {
  customQuickParameters = customQuickParameters.filter((item) => item !== code);
  saveQuickParameters();
  renderQuickParameterButtons(lastInspection?.nports, lastInspection?.file_previews);
  setQuickCustomMessage(slot, `${code} 已从快捷项中移除。`);
}

async function inspectSelectedFiles() {
  if (!Object.values(files).every(Boolean)) return;
  const generation = ++inspectionGeneration;
  const cachedToken = lastInspection?.inspection_token;
  lastInspection = null;
  inputChartState = null;
  inputTdrRequestId++; inputTdrData = null;
  inputChartPanel.hidden = true;
  setMappingLoading();
  if (!calculationBusy) setStatus('busy', '正在识别端口映射', cachedToken ? '复用已解析网络数据，快速刷新端口映射。' : '读取三份 Touchstone 的端口数与共同频段。', 'INSPECT');
  const buildForm = (reuseCache) => {
    const form = new FormData();
    if (reuseCache && cachedToken) form.append('inspection_token', cachedToken);
    else {
      form.append('total', files.total, files.total.name);
      form.append('thru_a', files.thru_a, files.thru_a.name);
      form.append('thru_b', files.thru_b, files.thru_b.name);
    }
    form.append('port_mapping', document.getElementById('port-map-select').value);
    return form;
  };
  try {
    let response = await fetch('/api/inspect', { method: 'POST', body: buildForm(Boolean(cachedToken)) });
    if (response.status === 410 && cachedToken) {
      response = await fetch('/api/inspect', { method: 'POST', body: buildForm(false) });
    }
    const data = await response.json().catch(() => ({}));
    if (generation !== inspectionGeneration) return;
    if (!response.ok) throw new Error(data.detail || `服务器返回 HTTP ${response.status}`);
    lastInspection = data;
    renderFileMapping(data);
    if (!calculationBusy) {
      if (mappingRecalcNeeded && calculation) setStatus('ready', '映射图已更新', '当前去嵌结果仍使用旧端口映射，请重新运行计算。', 'RE-RUN');
      else setStatus('ready', '三个文件已识别', `${data.topology} · ${data.mapping_label} · 共同频段 ${data.frequency_start_ghz.toFixed(3)}–${data.frequency_stop_ghz.toFixed(3)} GHz`, 'READY');
    }
  } catch (error) {
    if (generation !== inspectionGeneration) return;
    ['map-note-a', 'map-note-total', 'map-note-b'].forEach((id) => { document.getElementById(id).textContent = `识别失败：${error.message}`; });
    if (!calculationBusy) setStatus('error', '文件识别失败', error.message || '无法读取这些 Touchstone 文件，请检查格式和端口数。');
  }
}

function updateResults(data) {
  calculation = data;
  hideResultChartMarker(true);
  resultTdrRequestId++;
  resultTdrData = null;
  resultChartMode = 'sparam';
  resetResultChartAxisControls();
  setDownloadStatus('');
  if (resultChartView) resultChartView.value = 'sparam';
  resultTdrControls.hidden = true;
  document.getElementById('result-tdr-status').hidden = true;
  document.getElementById('chart-sparam-controls').hidden = false;
  document.getElementById('param-chips').hidden = false;
  document.getElementById('result-chart-kicker').textContent = 'FREQUENCY RESPONSE';
  document.getElementById('result-chart-title').textContent = '自定义 S 参数幅度图';
  document.getElementById('result-chart-subtitle').textContent = '输入矩阵参数名，可用逗号分隔多个参数。';
  document.getElementById('chart-y-label').textContent = '幅度 (dB)';
  document.getElementById('chart-frequency-label').textContent = '频率 (GHz)';
  mappingRecalcNeeded = false;
  const extension = data.nports === 4 ? 's4p' : 's2p';
  const downloads = [
    ['download-dut', 'dut', `DUT_deembedded.${extension}`],
    ['download-a', 'fix_a', `Fixture_A_1X.${extension}`],
    ['download-b', 'fix_b', `Fixture_B_1X.${extension}`],
  ];
  downloads.forEach(([id, networkKey, filename]) => {
    const link = document.getElementById(id);
    link.download = filename;
    link.href = data.result_token
      ? `/api/download/${encodeURIComponent(data.result_token)}/${networkKey}`
      : '#';
    link.querySelector('small').textContent = `.${extension}`;
  });
  document.getElementById('metric-topology').textContent = data.topology;
  document.getElementById('metric-frequency').textContent = `${data.frequency_start_ghz.toFixed(3)}–${data.frequency_stop_ghz.toFixed(3)} GHz`;
  document.getElementById('metric-points').textContent = `${data.points.toLocaleString()} 个共同频点 · Z₀ ${data.reference_z0} Ω`;
  document.getElementById('result-summary').textContent = `${sideLabel(data.side)}${data.port_mapping ? ` · ${data.port_mapping === 'plts' ? 'PLTS 交叉映射' : '标准顺序映射'}` : ''}`;

  const quality = data.quality || {};
  const passCard = document.getElementById('quality-card');
  const recipCard = document.getElementById('reciprocity-card');
  passCard.classList.remove('quality-pass', 'quality-warn', 'quality-fail');
  recipCard.classList.remove('quality-pass', 'quality-warn', 'quality-fail');
  passCard.classList.add(quality.passivity_pass ? 'quality-pass' : 'quality-fail');
  recipCard.classList.add(quality.reciprocity_pass ? 'quality-pass' : 'quality-warn');
  document.getElementById('metric-passivity').textContent = Number.isFinite(quality.max_singular_value) ? `σmax ${quality.max_singular_value.toFixed(4)}` : '—';
  document.getElementById('metric-passivity-note').textContent = quality.passivity_pass ? 'PASS · ≤ 1.005 容差' : 'CHECK · 高于无源性容差';
  document.getElementById('metric-reciprocity').textContent = formatScientific(quality.reciprocity_error);
  document.querySelector('#reciprocity-card small').textContent = quality.reciprocity_pass ? 'PASS · max |Sij − Sji|' : 'CHECK · max |Sij − Sji|';

  const initial = data.nports === 4 ? 'SDD21' : 'S21';
  activeParameters = [initial];
  document.getElementById('chart-params').value = initial;
  document.getElementById('chart-params').setAttribute('aria-invalid', 'false');
  document.getElementById('chart-param-error').textContent = '';
  buildParameterChips(data.nports);
  buildNetworkToggles();
  renderChartLegend();
  const mappingInfo = {
    nports: data.nports, topology: data.topology, detected_mapping: data.port_mapping || 'single-ended',
    left_ports: data.left_ports, right_ports: data.right_ports, mapping_label: data.mapping_label,
    frequency_start_ghz: data.frequency_start_ghz, frequency_stop_ghz: data.frequency_stop_ghz, points: data.points,
  };
  lastInspection = { ...(lastInspection || {}), ...mappingInfo };
  renderFileMapping(mappingInfo);
  resultPanel.hidden = false;
  requestAnimationFrame(drawResultChart);
}

function buildNetworkToggles() {
  const container = document.getElementById('network-toggles');
  if (!container) return;
  container.innerHTML = '';
  Object.entries(networkLabels).forEach(([key, label]) => {
    const wrapper = document.createElement('label');
    wrapper.className = 'network-toggle';
    const checked = key === 'total' || key === 'dut';
    wrapper.innerHTML = `<input type="checkbox" data-network="${key}" ${checked ? 'checked' : ''}><i class="network-color" style="background:${networkColorDots[key]}"></i>${label}`;
    wrapper.querySelector('input').addEventListener('change', () => { renderChartLegend(); drawResultChart(); });
    container.appendChild(wrapper);
  });
}
function buildParameterChips(nports) {
  const container = document.getElementById('param-chips');
  if (!container) return;
  const suggestions = nports === 2 ? ['S21', 'S11', 'S12', 'S22'] : ['SDD21', 'SDD11', 'SCD21', 'SCC21', 'S21'];
  container.innerHTML = '';
  suggestions.forEach((code) => {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'param-chip'; button.textContent = code;
    button.addEventListener('click', () => {
      const field = document.getElementById('chart-params');
      const current = field.value.trim();
      field.value = !current || current.toUpperCase() === 'S21' || current.toUpperCase() === 'SDD21' ? code : `${current}, ${code}`;
      applyParameters();
    });
    container.appendChild(button);
  });
}

async function runDeembed() {
  if (!files.total || !files.thru_a || !files.thru_b) {
    setStatus('error', '还缺少输入文件', '请分别添加 Total、2X Thru A 与 2X Thru B。');
    return;
  }
  const z0 = Number(document.getElementById('z0-input').value);
  if (!Number.isFinite(z0) || z0 <= 0) { setStatus('error', '参考阻抗无效', '请输入大于 0 的 Z₀ 数值。'); return; }
  const buildForm = (includeFiles) => {
    const form = new FormData();
    if (includeFiles) {
      form.append('total', files.total, files.total.name);
      form.append('thru_a', files.thru_a, files.thru_a.name);
      form.append('thru_b', files.thru_b, files.thru_b.name);
    } else if (lastInspection?.inspection_token) {
      form.append('inspection_token', lastInspection.inspection_token);
    }
    form.append('side', document.getElementById('side-select').value);
    form.append('port_mapping', document.getElementById('port-map-select').value);
    form.append('reference_z0', String(z0));
    return form;
  };
  const hasInspectionCache = Boolean(lastInspection?.inspection_token);
  calculationBusy = true;
  runButton.disabled = true;
  runButton.querySelector('span:last-child').textContent = '计算中…';
  setStatus('busy', '正在劈半并去嵌', hasInspectionCache ? '复用已识别的网络数据，直接提取夹具并计算 DUT S 参数。' : '对齐共同频段、提取左右 1X 夹具并计算 DUT S 参数。', 'RUNNING');
  try {
    let response = await fetch('/api/deembed', { method: 'POST', body: buildForm(!hasInspectionCache) });
    if (response.status === 410 && hasInspectionCache) {
      response = await fetch('/api/deembed', { method: 'POST', body: buildForm(true) });
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.message || `服务器返回 HTTP ${response.status}`);
    if (!data.success) throw new Error(data.detail || data.message || '计算未成功完成。');
    updateResults(data);
    setStatus('success', '去嵌完成', `${data.message} · ${data.points.toLocaleString()} 个共同频点。`, 'DONE');
  } catch (error) {
    setStatus('error', '计算失败', error.message || '服务器暂时不可用，请检查文件后重试。');
  } finally {
    calculationBusy = false;
    runButton.disabled = false;
    runButton.querySelector('span:last-child').textContent = '开始去嵌';
  }
}
runButton.addEventListener('click', runDeembed);

function saveBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename;
  document.body.appendChild(anchor); anchor.click(); anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function setDownloadStatus(message, isError = false) {
  const status = document.getElementById('download-status');
  status.textContent = message;
  status.classList.toggle('is-error', isError);
}
function downloadResultNetwork(networkKey, filename, event) {
  if (!calculation) {
    event.preventDefault(); setDownloadStatus('没有可下载的计算结果。', true); return;
  }
  if (!calculation.result_token) {
    event.preventDefault();
    const inline = calculation[`${networkKey}_touchstone`];
    if (inline) {
      try {
        saveBlob(filename, new Blob([inline], { type: 'text/plain;charset=utf-8' }));
        setDownloadStatus(`已请求下载 ${filename}`);
      } catch (error) { setDownloadStatus(`下载启动失败：${error.message}`, true); }
      return;
    }
    setDownloadStatus('本次结果的临时下载缓存已过期，请重新运行去嵌。', true);
    return;
  }
  // Let the clicked anchor perform the download directly from the attachment endpoint.
  // This keeps the action inside the user's gesture; fetch-then-Blob downloads can be blocked.
  setDownloadStatus(`已请求下载 ${filename}`);
}
document.getElementById('download-dut').addEventListener('click', (event) => downloadResultNetwork('dut', `DUT_deembedded.s${calculation?.nports || 2}p`, event));
document.getElementById('download-a').addEventListener('click', (event) => downloadResultNetwork('fix_a', `Fixture_A_1X.s${calculation?.nports || 2}p`, event));
document.getElementById('download-b').addEventListener('click', (event) => downloadResultNetwork('fix_b', `Fixture_B_1X.s${calculation?.nports || 2}p`, event));

function selectedNetworkKeys() { return [...document.querySelectorAll('#network-toggles input[data-network]:checked')].map((input) => input.dataset.network); }
function renderChartLegend() {
  const legend = document.getElementById('chart-legend');
  if (!legend) return;
  if (!calculation) { legend.innerHTML = ''; return; }
  const keys = selectedNetworkKeys(); legend.innerHTML = '';
  if (resultChartMode === 'tdr') {
    keys.forEach((networkKey) => {
      if (!resultTdrData?.series?.[networkKey]) return;
      const item = document.createElement('span'); item.className = 'chart-legend-item';
      const swatch = document.createElement('i'); swatch.className = 'chart-legend-swatch'; swatch.style.borderTopColor = networkColorDots[networkKey];
      item.append(swatch, document.createTextNode(`${networkLabels[networkKey]} · ${resultTdrData.parameter} · ${resultTdrData.reference_ohm.toFixed(0)} Ω`)); legend.appendChild(item);
    });
    return;
  }
  activeParameters.forEach((parameter, parameterIndex) => {
    const color = parameterColors[parameterIndex % parameterColors.length];
    keys.forEach((networkKey) => {
      const item = document.createElement('span'); item.className = 'chart-legend-item';
      const swatch = document.createElement('i'); swatch.className = `chart-legend-swatch${networkKey === 'dut' ? '' : ' dashed'}`; swatch.style.borderTopColor = color;
      item.append(swatch, document.createTextNode(`${parameter} · ${networkLabels[networkKey]}`)); legend.appendChild(item);
    });
  });
}
function applyParameters() {
  if (!calculation) return;
  const field = document.getElementById('chart-params'); const error = document.getElementById('chart-param-error');
  const requested = splitParameterCodes(field.value);
  const available = new Set(Object.keys(calculation.chart.series));
  if (!requested.length) { field.setAttribute('aria-invalid', 'true'); error.textContent = '请输入至少一个 S 参数，例如 S21 或 SDD21。'; return; }
  if (requested.length > MAX_CHART_PARAMETERS) { field.setAttribute('aria-invalid', 'true'); error.textContent = `为保证曲线可读，每次最多绘制 ${MAX_CHART_PARAMETERS} 个参数。`; return; }
  const invalid = requested.filter((code) => !available.has(code));
  if (invalid.length) {
    field.setAttribute('aria-invalid', 'true');
    error.textContent = `无法识别：${invalid.join(', ')}。${calculation.nports === 4 ? '支持 Sij 与 SDD/SCC/SCD/SDC 混合模参数。' : '当前 S2P 支持 S11、S12、S21、S22。'}`;
    return;
  }
  field.setAttribute('aria-invalid', 'false'); error.textContent = ''; activeParameters = requested; renderChartLegend(); drawResultChart();
}
document.getElementById('btn-plot-params').addEventListener('click', applyParameters);
document.getElementById('chart-params').addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); applyParameters(); } });

function chartScaleFromValues(values) {
  const finiteValues = values.filter(Number.isFinite);
  if (!finiteValues.length) return null;
  let yMin = Math.min(...finiteValues), yMax = Math.max(...finiteValues);
  if (Math.abs(yMax - yMin) < 1) { yMax += 1; yMin -= 1; }
  const margin = (yMax - yMin) * .11;
  yMin = Math.floor((yMin - margin) / 5) * 5;
  yMax = Math.ceil((yMax + margin) / 5) * 5;
  if (yMax <= yMin) yMax = yMin + 5;
  return { yMin, yMax };
}
function chartScaleWithLimits(values, limits = {}) {
  const automatic = chartScaleFromValues(values);
  if (!automatic) return null;
  const yMin = Number.isFinite(limits.min) ? limits.min : automatic.yMin;
  const yMax = Number.isFinite(limits.max) ? limits.max : automatic.yMax;
  return yMax > yMin ? { yMin, yMax } : null;
}
function fractionForXAxisValue(values, target) {
  if (!values?.length || !Number.isFinite(target)) return null;
  if (values.length === 1) return target === Number(values[0]) ? 0 : null;
  const first = Number(values[0]), last = Number(values[values.length - 1]);
  if (!Number.isFinite(first) || !Number.isFinite(last) || target < first || target > last) return null;
  let low = 0, high = values.length - 1;
  while (high - low > 1) {
    const mid = (low + high) >> 1;
    if (Number(values[mid]) < target) low = mid; else high = mid;
  }
  const x0 = Number(values[low]), x1 = Number(values[high]);
  const indexPosition = x1 === x0 ? low : low + (target - x0) / (x1 - x0);
  return indexPosition / (values.length - 1);
}
function drawLineChart(targetCanvas, freq, traces, options = {}) {
  if (!targetCanvas) return;
  const rect = targetCanvas.getBoundingClientRect(); if (rect.width < 10 || rect.height < 10) return;
  if (!freq?.length) {
    const ratio = Math.max(1, window.devicePixelRatio || 1);
    targetCanvas.width = Math.round(rect.width * ratio); targetCanvas.height = Math.round(rect.height * ratio);
    const emptyContext = targetCanvas.getContext('2d'); emptyContext.setTransform(ratio, 0, 0, ratio, 0, 0); emptyContext.clearRect(0, 0, rect.width, rect.height);
    return;
  }
  const ratio = Math.max(1, window.devicePixelRatio || 1);
  targetCanvas.width = Math.round(rect.width * ratio); targetCanvas.height = Math.round(rect.height * ratio);
  const ctx = targetCanvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, rect.width, rect.height);
  const width = rect.width, height = rect.height, pad = { left: 53, right: 16, top: 14, bottom: 30 };
  const plotW = Math.max(20, width - pad.left - pad.right), plotH = Math.max(20, height - pad.top - pad.bottom);
  const scale = chartScaleWithLimits(traces.flatMap((trace) => trace.values), { min: options.yMin, max: options.yMax }); if (!scale) return;
  const { yMin, yMax } = scale;
  const xAt = (i) => pad.left + (freq.length <= 1 ? 0 : i / (freq.length - 1)) * plotW;
  const yAt = (value) => pad.top + (yMax - value) / (yMax - yMin) * plotH;
  ctx.font = '10px Inter, system-ui, sans-serif'; ctx.textBaseline = 'middle';
  for (let tick = 0; tick <= 5; tick++) {
    const value = yMax - (yMax - yMin) * tick / 5, y = pad.top + plotH * tick / 5;
    ctx.strokeStyle = 'rgba(126,151,174,.14)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
    ctx.fillStyle = '#718399'; ctx.textAlign = 'right'; ctx.fillText(value.toFixed(0), pad.left - 9, y);
  }
  const xTicks = Math.min(5, Math.max(2, freq.length - 1));
  for (let tick = 0; tick <= xTicks; tick++) {
    const x = pad.left + plotW * tick / xTicks, index = Math.round((freq.length - 1) * tick / xTicks), f = freq[index];
    ctx.strokeStyle = 'rgba(126,151,174,.1)'; ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, pad.top + plotH); ctx.stroke();
    ctx.fillStyle = '#718399'; ctx.textAlign = tick === 0 ? 'left' : tick === xTicks ? 'right' : 'center'; ctx.fillText(Number(f).toFixed(options.xDecimals ?? 2), x, height - 11);
  }
  ctx.strokeStyle = 'rgba(148,163,184,.25)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(pad.left, pad.top); ctx.lineTo(pad.left, pad.top + plotH); ctx.lineTo(width - pad.right, pad.top + plotH); ctx.stroke();
  traces.forEach((trace) => {
    ctx.beginPath(); ctx.strokeStyle = trace.color; ctx.globalAlpha = trace.alpha ?? 1; ctx.lineWidth = trace.width || 1.8; ctx.setLineDash(trace.dash || []);
    let started = false; const count = Math.min(freq.length, trace.values.length);
    for (let i = 0; i < count; i++) {
      const value = trace.values[i]; if (!Number.isFinite(value)) { started = false; continue; }
      const x = xAt(i), y = yAt(value); if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    }
    ctx.stroke();
  });
  ctx.globalAlpha = 1; ctx.setLineDash([]); ctx.textAlign = 'left';
}

function sliceTdrDisplay(data, startId, endId, pointLimitId = null) {
  if (!data?.time_ns?.length) return { time_ns: [], series: {} };
  const time = data.time_ns;
  const startText = document.getElementById(startId)?.value ?? '0';
  const endText = document.getElementById(endId)?.value ?? '';
  const parsedStart = startText.trim() === '' ? 0 : Number(startText);
  const parsedEnd = endText.trim() === '' ? time[time.length - 1] : Number(endText);
  const start = Number.isFinite(parsedStart) ? Math.max(time[0], parsedStart) : time[0];
  const end = Number.isFinite(parsedEnd) ? Math.min(time[time.length - 1], parsedEnd) : time[time.length - 1];
  const indices = [];
  if (end >= start) {
    for (let i = 0; i < time.length; i++) if (time[i] >= start && time[i] <= end) indices.push(i);
  }
  const sourceSeries = data.series || { input: data.impedance_ohm || [] };
  const pointLimit = Math.max(2, Number.parseInt(document.getElementById(pointLimitId)?.value || '6000', 10) || 6000);
  let plottedIndices = indices;
  if (indices.length > pointLimit) {
    plottedIndices = Array.from({ length: pointLimit }, (_, i) => indices[Math.round(i * (indices.length - 1) / (pointLimit - 1))]);
  }
  const series = {};
  Object.entries(sourceSeries).forEach(([key, values]) => { series[key] = plottedIndices.map((i) => values[i]); });
  return { time_ns: plottedIndices.map((i) => time[i]), series };
}
function drawResultTdrChart() {
  if (!calculation || resultPanel.hidden) return;
  if (!resultTdrData) { drawLineChart(canvas, [], []); return; }
  const keys = selectedNetworkKeys().filter((key) => resultTdrData.series?.[key]);
  const display = sliceTdrDisplay({ time_ns: resultTdrData.time_ns, series: resultTdrData.series }, 'result-tdr-time-start', 'result-tdr-time-end', 'result-tdr-display-points');
  const traces = keys.map((key) => ({ values: display.series[key] || [], color: networkColorDots[key], dash: networkDash[key] || [], width: key === 'dut' ? 2.2 : 1.6, alpha: key === 'dut' ? 1 : .82 }));
  drawLineChart(canvas, display.time_ns, traces, { xDecimals: 3, yMin: resultChartYLimits.min, yMax: resultChartYLimits.max });
  if (resultChartHoverFraction !== null) positionResultTdrMarker(resultChartHoverFraction, resultChartHoverYFraction);
}
function drawResultChart() {
  if (!calculation || resultPanel.hidden) return;
  if (resultChartMode === 'tdr') { drawResultTdrChart(); return; }
  const freq = calculation.chart.freq_ghz, networks = selectedNetworkKeys(), traces = [];
  activeParameters.forEach((parameter, parameterIndex) => {
    const color = parameterColors[parameterIndex % parameterColors.length];
    networks.forEach((networkKey) => {
      const values = calculation.chart.series[parameter]?.[networkKey];
      if (values) traces.push({ values, color, dash: networkDash[networkKey] || [], width: networkKey === 'dut' ? 2.2 : 1.45, alpha: networkKey === 'dut' ? 1 : .78 });
    });
  });
  drawLineChart(canvas, freq, traces, { yMin: resultChartYLimits.min, yMax: resultChartYLimits.max });
  if (resultChartHoverFraction !== null) positionResultChartMarker(resultChartHoverFraction, resultChartHoverYFraction);
}

async function loadResultTdr() {
  if (!calculation || resultChartMode !== 'tdr') return;
  const requestId = ++resultTdrRequestId;
  resultTdrData = null;
  document.getElementById('result-chart-x-value').value = '';
  resultChartMarkerPinned = false;
  hideResultChartMarker(true);
  renderChartLegend();
  const status = document.getElementById('result-tdr-status');
  status.hidden = false; status.textContent = '正在从复数 S 参数计算时域阶跃响应…';
  const inspectionToken = lastInspection?.inspection_token;
  if (!inspectionToken || !calculation.result_token) {
    status.textContent = !inspectionToken ? '输入网络缓存已过期，请重新识别三个文件后再生成结果 TDR。' : '本次结果未缓存复数网络数据，请重新运行去嵌后再试。';
    drawResultChart();
    return;
  }
  const form = new FormData();
  form.append('inspection_token', inspectionToken);
  form.append('result_token', calculation.result_token);
  form.append('port', document.getElementById('result-tdr-port').value);
  form.append('port_mapping', calculation.port_mapping || 'auto');
  form.append('reference_z0', String(calculation.reference_z0 || 50));
  form.append('window', document.getElementById('result-tdr-window').value);
  form.append('dc_method', document.getElementById('result-tdr-dc').value);
  form.append('rise_time_ps', document.getElementById('result-tdr-rise').value || '0');
  try {
    const response = await fetch('/api/tdr/result', { method: 'POST', body: form });
    const data = await response.json().catch(() => ({}));
    if (requestId !== resultTdrRequestId) return;
    if (!response.ok) throw new Error(data.detail || `服务器返回 HTTP ${response.status}`);
    resultTdrData = data;
    const mode = calculation.nports === 4 ? '差分' : '单端';
    const statusText = `${data.parameter} · ${mode}参考阻抗 ${Number(data.reference_ohm).toFixed(0)} Ω · 原生 Δt ${Number(data.sample_step_ps).toFixed(2)} ps · ${data.time_ns.length.toLocaleString()} 显示点`;
    status.textContent = statusText;
    document.getElementById('result-chart-subtitle').textContent = `阶跃阻抗 · ${data.parameter} · DC ${data.dc_method === 'linear' ? '线性外推' : '首点延拓'} · ${data.window} 窗 · 上升时间 ${Number(data.rise_time_ps).toFixed(0)} ps`;
    renderChartLegend(); drawResultChart();
  } catch (error) {
    if (requestId !== resultTdrRequestId) return;
    resultTdrData = null; status.textContent = `TDR 生成失败：${error.message}`; drawResultChart();
  }
}
function setResultChartView(mode) {
  if (!calculation) return;
  const nextMode = mode === 'tdr' ? 'tdr' : 'sparam';
  const modeChanged = nextMode !== resultChartMode;
  resultChartMode = nextMode;
  if (modeChanged) resetResultChartAxisControls();
  hideResultChartMarker(true);
  document.getElementById('result-chart-x-unit').textContent = resultChartMode === 'tdr' ? 'ns' : 'GHz';
  const isTdr = resultChartMode === 'tdr';
  document.getElementById('chart-sparam-controls').hidden = isTdr;
  document.getElementById('param-chips').hidden = isTdr;
  resultTdrControls.hidden = !isTdr;
  document.getElementById('result-tdr-status').hidden = !isTdr;
  document.getElementById('chart-y-label').textContent = isTdr ? '阻抗 (Ω)' : '幅度 (dB)';
  document.getElementById('chart-frequency-label').textContent = isTdr ? '时间 (ns)' : '频率 (GHz)';
  document.getElementById('result-chart-kicker').textContent = isTdr ? 'TIME DOMAIN REFLECTOMETRY' : 'FREQUENCY RESPONSE';
  document.getElementById('result-chart-title').textContent = isTdr ? 'TDR 阶跃阻抗图' : '自定义 S 参数幅度图';
  if (!isTdr) {
    document.getElementById('result-chart-subtitle').textContent = '输入矩阵参数名，可用逗号分隔多个参数。';
    document.getElementById('result-tdr-status').hidden = true;
    renderChartLegend(); drawResultChart();
    return;
  }
  const port = document.getElementById('result-tdr-port');
  port.options[0].textContent = calculation.nports === 4 ? '差分端口 1 · SDD11' : '单端端口 1 · S11';
  port.options[1].textContent = calculation.nports === 4 ? '差分端口 2 · SDD22' : '单端端口 2 · S22';
  document.getElementById('result-chart-subtitle').textContent = '根据所选反射端口和 TDR 设置重新计算。';
  loadResultTdr();
}
resultChartView.addEventListener('change', () => setResultChartView(resultChartView.value));
['result-tdr-port', 'result-tdr-dc', 'result-tdr-window', 'result-tdr-rise'].forEach((id) => {
  document.getElementById(id).addEventListener('change', () => { if (resultChartMode === 'tdr') loadResultTdr(); });
});
['result-tdr-time-start', 'result-tdr-time-end', 'result-tdr-display-points'].forEach((id) => {
  document.getElementById(id).addEventListener('input', () => { if (resultChartMode === 'tdr') drawResultChart(); });
});

function parseParameterInput(value, available) {
  const codes = splitParameterCodes(value);
  if (!codes.length) return { error: '请输入至少一个参数，例如 S11。' };
  if (codes.length > MAX_CHART_PARAMETERS) return { error: `每张图最多生成 ${MAX_CHART_PARAMETERS} 条参数曲线。` };
  const invalid = codes.filter((code) => !available.includes(code));
  if (invalid.length) return { error: `不支持：${invalid.join(', ')}。请检查 S 参数代码。` };
  return { codes };
}

function buildInputSparamDisplay(items) {
  const start = Math.max(...items.map((item) => Number(item.preview.freq_ghz[0])));
  const stop = Math.min(...items.map((item) => Number(item.preview.freq_ghz[item.preview.freq_ghz.length - 1])));
  if (!Number.isFinite(start) || !Number.isFinite(stop) || stop <= start) return null;
  const count = Math.max(8, Math.min(600, ...items.map((item) => item.preview.freq_ghz.length)));
  const freq_ghz = Array.from({ length: count }, (_, index) => start + (stop - start) * index / (count - 1));
  const traces = [];
  items.forEach((item) => item.codes.forEach((code, parameterIndex) => {
    const sourceFreq = item.preview.freq_ghz;
    const sourceValues = item.preview.series[code] || [];
    let cursor = 0;
    const values = freq_ghz.map((frequency) => {
      while (cursor + 1 < sourceFreq.length && Number(sourceFreq[cursor + 1]) < frequency) cursor++;
      const x0 = Number(sourceFreq[cursor]), x1 = Number(sourceFreq[Math.min(cursor + 1, sourceFreq.length - 1)]);
      const y0 = Number(sourceValues[cursor]), y1 = Number(sourceValues[Math.min(cursor + 1, sourceValues.length - 1)]);
      if (frequency < x0 || frequency > x1 && cursor + 1 >= sourceFreq.length) return NaN;
      if (x1 === x0) return Number.isFinite(y0) ? y0 : NaN;
      return Number.isFinite(y0) && Number.isFinite(y1) ? y0 + (y1 - y0) * ((frequency - x0) / (x1 - x0)) : NaN;
    });
    const label = `${slotUi[item.slot].label} · ${code}`;
    traces.push({ slot: item.slot, code, label, values, color: inputTdrColors[item.slot], dash: inputParameterDashes[parameterIndex % inputParameterDashes.length] || [], width: 1.9 });
  }));
  return { freq_ghz, traces };
}
function renderInputSparamLegend() {
  const legend = document.getElementById('input-chart-legend');
  if (!legend || !inputChartState) return;
  legend.innerHTML = ''; legend.hidden = false;
  inputChartState.display.traces.forEach((trace) => {
    const item = document.createElement('span');
    const swatch = document.createElement('i');
    swatch.style.borderTopColor = trace.color;
    swatch.style.borderTopStyle = trace.dash.length ? 'dashed' : 'solid';
    item.append(swatch, document.createTextNode(trace.label)); legend.appendChild(item);
  });
}
function renderInputTdrLegend(parameter) {
  const legend = document.getElementById('input-chart-legend');
  if (!legend) return;
  legend.innerHTML = ''; legend.hidden = false;
  inputTdrNetworkOrder.forEach((key) => {
    const item = document.createElement('span');
    const swatch = document.createElement('i');
    swatch.style.borderTopColor = inputTdrColors[key];
    swatch.style.borderTopStyle = networkDash[key]?.length ? 'dashed' : 'solid';
    item.append(swatch, document.createTextNode(`${inputTdrNetworkLabels[key]} · ${parameter}`));
    legend.appendChild(item);
  });
}
function showCombinedInputChart() {
  const previews = lastInspection?.file_previews;
  if (!previews) {
    setStatus('error', '尚未完成文件识别', '请等待三个 Touchstone 文件识别完成，再生成组合 S 参数或 TDR 图。'); return;
  }
  const items = [];
  for (const [slot, ui] of Object.entries(slotUi)) {
    const field = document.getElementById(ui.inputId);
    const note = document.getElementById(ui.noteId);
    const raw = field.value.trim();
    field.setAttribute('aria-invalid', 'false'); note.classList.remove('is-error');
    if (!raw) { note.textContent = '留空，组合图中不绘制'; continue; }
    const preview = previews[slot];
    const parsed = parseParameterInput(raw, Object.keys(preview?.series || {}));
    if (parsed.error) {
      field.setAttribute('aria-invalid', 'true'); note.textContent = parsed.error; note.classList.add('is-error'); return;
    }
    const item = { slot, preview, codes: parsed.codes, title: ui.chartLabel };
    items.push(item);
    note.textContent = `${parsed.codes.join(', ')} · ${preview.freq_ghz.length.toLocaleString()} 点 · 已加入组合图`;
  }
  if (!items.length) {
    setStatus('error', '没有可绘制的参数', '请至少在 A、Total、B 其中一栏输入一个有效的 S 参数。'); return;
  }
  const display = buildInputSparamDisplay(items);
  if (!display) {
    setStatus('error', '频段没有重叠', '这几条输入曲线无法在共同频段中叠加，请检查文件的频率范围。'); return;
  }
  inputChartState = { items, display };
  inputTdrRequestId++; inputTdrData = null; inputChartMode = 'sparam'; inputChartView.value = 'sparam';
  resetInputChartAxisControls();
  inputTdrControls.hidden = true; document.getElementById('input-tdr-status').hidden = true;
  document.getElementById('input-chart-title').textContent = `${items.map((item) => slotUi[item.slot].label).join(' + ')} · S 参数对比`;
  const summary = items.map((item) => `${slotUi[item.slot].label}: ${files[item.slot].name} (${item.codes.join(', ')})`).join('  |  ');
  document.getElementById('input-chart-subtitle').textContent = `${summary} · ${display.freq_ghz[0].toFixed(3)}–${display.freq_ghz[display.freq_ghz.length - 1].toFixed(3)} GHz`;
  document.getElementById('input-chart-axis-label').textContent = '频率 (GHz)';
  document.getElementById('input-chart-y-label').textContent = '幅度 (dB)';
  renderInputSparamLegend();
  hideInputChartMarker(true);
  inputChartPanel.hidden = false;
  requestAnimationFrame(drawInputChart);
  inputChartPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function setInputChartView(mode) {
  if (!inputChartState) return;
  const nextMode = mode === 'tdr' ? 'tdr' : 'sparam';
  const modeChanged = nextMode !== inputChartMode;
  inputChartMode = nextMode;
  inputTdrRequestId++;
  if (modeChanged) resetInputChartAxisControls();
  hideInputChartMarker(true);
  const isTdr = inputChartMode === 'tdr';
  const status = document.getElementById('input-tdr-status');
  inputTdrControls.hidden = !isTdr;
  status.hidden = !isTdr;
  document.getElementById('input-chart-y-label').textContent = isTdr ? '阻抗 (Ω)' : '幅度 (dB)';
  document.getElementById('input-chart-axis-label').textContent = isTdr ? '时间 (ns)' : '频率 (GHz)';
  const legend = document.getElementById('input-chart-legend');
  if (!isTdr) {
    renderInputSparamLegend();
    document.getElementById('input-chart-title').textContent = `${inputChartState.items.map((item) => slotUi[item.slot].label).join(' + ')} · S 参数对比`;
    const summary = inputChartState.items.map((item) => `${slotUi[item.slot].label}: ${files[item.slot].name} (${item.codes.join(', ')})`).join('  |  ');
    document.getElementById('input-chart-subtitle').textContent = `${summary} · ${inputChartState.display.freq_ghz[0].toFixed(3)}–${inputChartState.display.freq_ghz[inputChartState.display.freq_ghz.length - 1].toFixed(3)} GHz`;
    requestAnimationFrame(drawInputChart);
    return;
  }
  const port = document.getElementById('input-tdr-port');
  port.options[0].textContent = lastInspection?.nports === 4 ? '差分端口 1 · SDD11' : '单端端口 1 · S11';
  port.options[1].textContent = lastInspection?.nports === 4 ? '差分端口 2 · SDD22' : '单端端口 2 · S22';
  const parameter = lastInspection?.nports === 4
    ? (port.value === '2' ? 'SDD22' : 'SDD11')
    : (port.value === '2' ? 'S22' : 'S11');
  document.getElementById('input-chart-title').textContent = 'TDR 阶跃阻抗 · 2X Thru A + Total + 2X Thru B';
  const summary = inputTdrNetworkOrder.map((key) => `${inputTdrNetworkLabels[key]}: ${files[key].name}`).join('  |  ');
  document.getElementById('input-chart-subtitle').textContent = `${summary} · ${parameter} · 三个输入网络叠加`;
  renderInputTdrLegend(parameter);
  status.textContent = '正在计算 A、Total、B 三条时域阶跃响应…';
  loadInputTdr();
}
async function loadInputTdr() {
  if (!inputChartState || inputChartMode !== 'tdr') return;
  const requestId = ++inputTdrRequestId;
  inputTdrData = null;
  document.getElementById('input-chart-x-value').value = '';
  inputChartMarkerPinned = false;
  hideInputChartMarker(true);
  const status = document.getElementById('input-tdr-status');
  status.hidden = false; status.textContent = '正在计算 A、Total、B 三条时域阶跃响应…';
  const inspectionToken = lastInspection?.inspection_token;
  if (!inspectionToken) { status.textContent = '输入网络缓存已过期，请重新识别三个文件后再生成 TDR。'; drawInputChart(); return; }
  const form = new FormData();
  form.append('inspection_token', inspectionToken);
  form.append('slot', 'all');
  form.append('port', document.getElementById('input-tdr-port').value);
  form.append('port_mapping', document.getElementById('port-map-select').value);
  form.append('reference_z0', document.getElementById('z0-input').value || '50');
  form.append('window', document.getElementById('input-tdr-window').value);
  form.append('dc_method', document.getElementById('input-tdr-dc').value);
  form.append('rise_time_ps', document.getElementById('input-tdr-rise').value || '0');
  try {
    const response = await fetch('/api/tdr/input', { method: 'POST', body: form });
    const data = await response.json().catch(() => ({}));
    if (requestId !== inputTdrRequestId) return;
    if (!response.ok) throw new Error(data.detail || `服务器返回 HTTP ${response.status}`);
    inputTdrData = data;
    const refMode = lastInspection?.nports === 4 ? '差分' : '单端';
    status.textContent = `${data.parameter} · ${refMode}参考阻抗 ${Number(data.reference_ohm).toFixed(0)} Ω · 原生 Δt ${Number(data.sample_step_ps).toFixed(2)} ps · A + Total + B`;
    document.getElementById('input-chart-title').textContent = 'TDR 阶跃阻抗 · 2X Thru A + Total + 2X Thru B';
    const summary = inputTdrNetworkOrder.map((key) => `${inputTdrNetworkLabels[key]}: ${files[key].name}`).join('  |  ');
    document.getElementById('input-chart-subtitle').textContent = `${summary} · ${data.parameter} · ${data.window} 窗 · ${data.dc_method === 'linear' ? '线性 DC 外推' : '首点延拓'} · 上升时间 ${Number(data.rise_time_ps).toFixed(0)} ps`;
    renderInputTdrLegend(data.parameter);
    drawInputChart();
  } catch (error) {
    if (requestId !== inputTdrRequestId) return;
    inputTdrData = null; status.textContent = `TDR 生成失败：${error.message}`; drawInputChart();
  }
}
inputChartView.addEventListener('change', () => setInputChartView(inputChartView.value));
['input-tdr-port', 'input-tdr-dc', 'input-tdr-window', 'input-tdr-rise'].forEach((id) => {
  document.getElementById(id).addEventListener('change', () => { if (inputChartMode === 'tdr') loadInputTdr(); });
});
['input-tdr-time-start', 'input-tdr-time-end', 'input-tdr-display-points'].forEach((id) => {
  document.getElementById(id).addEventListener('input', () => { if (inputChartMode === 'tdr') drawInputChart(); });
});
function hideInputChartMarker(force = false) {
  if (inputChartMarkerPinned && !force) return;
  inputChartMarkerPinned = false;
  inputChartHoverFraction = null;
  if (inputChartXMarker) inputChartXMarker.hidden = true;
  if (inputChartHoverReadout) inputChartHoverReadout.hidden = true;
  if (inputChartPointMarkers) inputChartPointMarkers.innerHTML = '';
}
function interpolatedSeriesValue(values, indexPosition) {
  if (!values?.length) return NaN;
  const index = Math.floor(indexPosition);
  const nextIndex = Math.min(values.length - 1, index + 1);
  const rawFirst = values[index], rawSecond = values[nextIndex];
  const first = rawFirst == null || rawFirst === '' ? NaN : Number(rawFirst);
  const second = rawSecond == null || rawSecond === '' ? NaN : Number(rawSecond);
  if (index === nextIndex) return Number.isFinite(first) ? first : NaN;
  if (!Number.isFinite(first) || !Number.isFinite(second)) return NaN;
  return first + (second - first) * (indexPosition - index);
}
function positionInputChartMarker(fraction, yFraction = inputChartHoverYFraction) {
  if (!inputChartState || !inputChartXMarker || !inputChartXMarkerLabel || !inputCanvas) return;
  const rect = inputCanvas.getBoundingClientRect();
  const plotLeft = 53, plotRight = 16, plotTop = 14, plotBottom = 30;
  const plotWidth = rect.width - plotLeft - plotRight, plotHeight = rect.height - plotTop - plotBottom;
  if (plotWidth <= 0 || plotHeight <= 0) return;
  const normalized = Math.max(0, Math.min(1, fraction));
  inputChartHoverFraction = normalized;
  inputChartHoverYFraction = Math.max(0, Math.min(1, yFraction));
  const freq = inputChartState.display.freq_ghz;
  const indexPosition = normalized * Math.max(0, freq.length - 1);
  const frequency = interpolatedSeriesValue(freq, indexPosition);
  const xValueField = document.getElementById('input-chart-x-value');
  if (xValueField && Number.isFinite(frequency)) xValueField.value = frequency.toFixed(6);
  const markerX = plotLeft + normalized * plotWidth;
  inputChartXMarker.style.left = `${markerX}px`;
  inputChartXMarkerLabel.textContent = `${frequency.toFixed(3)} GHz`;
  inputChartXMarker.hidden = false;

  const traces = inputChartState.display.traces;
  const scale = chartScaleWithLimits(traces.flatMap((trace) => trace.values), inputChartYLimits);
  const markerValues = traces.map((trace) => ({ ...trace, value: interpolatedSeriesValue(trace.values, indexPosition) }));
  if (inputChartPointMarkers) {
    inputChartPointMarkers.innerHTML = '';
    markerValues.forEach((item) => {
      if (!Number.isFinite(item.value) || !scale) return;
      const dot = document.createElement('span'); dot.className = 'input-chart-point-marker';
      dot.style.left = `${markerX}px`;
      dot.style.top = `${plotTop + (scale.yMax - item.value) / (scale.yMax - scale.yMin) * plotHeight}px`;
      dot.style.backgroundColor = item.color; dot.title = `${item.label}: ${item.value.toFixed(2)} dB`;
      inputChartPointMarkers.appendChild(dot);
    });
  }
  if (!inputChartHoverReadout) return;
  inputChartHoverReadout.innerHTML = '';
  const frequencyLine = document.createElement('div'); frequencyLine.className = 'input-chart-hover-frequency';
  frequencyLine.textContent = `${frequency.toFixed(3)} GHz`; inputChartHoverReadout.appendChild(frequencyLine);
  markerValues.forEach((item) => {
    const row = document.createElement('div'); row.className = 'input-chart-hover-row';
    const name = document.createElement('span'); name.className = 'input-chart-hover-param';
    const swatch = document.createElement('i'); swatch.className = 'input-chart-hover-swatch'; swatch.style.backgroundColor = item.color;
    const code = document.createElement('span'); code.textContent = item.label;
    name.append(swatch, code);
    const value = document.createElement('b'); value.className = 'input-chart-hover-value';
    value.textContent = Number.isFinite(item.value) ? `${item.value.toFixed(2)} dB` : '—';
    row.append(name, value); inputChartHoverReadout.appendChild(row);
  });
  inputChartHoverReadout.hidden = false;
  const wrapRect = (inputChartWrap || inputCanvas).getBoundingClientRect();
  const readoutWidth = Math.min(230, Math.max(150, wrapRect.width * .5));
  inputChartHoverReadout.style.width = `${readoutWidth}px`;
  const left = markerX < wrapRect.width / 2 ? markerX + 12 : markerX - readoutWidth - 12;
  const boundedLeft = Math.max(5, Math.min(wrapRect.width - readoutWidth - 5, left));
  const readoutHeight = inputChartHoverReadout.getBoundingClientRect().height || 50 + markerValues.length * 14;
  const topFromPointer = inputChartHoverYFraction * wrapRect.height + 10;
  const boundedTop = Math.max(5, Math.min(wrapRect.height - readoutHeight - 5, topFromPointer));
  inputChartHoverReadout.style.left = `${boundedLeft}px`;
  inputChartHoverReadout.style.top = `${boundedTop}px`;
}
function updateInputChartMarker(event) {
  if (!inputChartState || inputChartPanel.hidden) return;
  const rect = inputCanvas.getBoundingClientRect();
  const plotWidth = rect.width - 53 - 16;
  const offsetX = event.clientX - rect.left - 53;
  if (plotWidth <= 0 || offsetX < 0 || offsetX > plotWidth) {
    hideInputChartMarker();
    return;
  }
  const yFraction = rect.height > 0 ? (event.clientY - rect.top) / rect.height : .25;
  positionInputChartMarker(offsetX / plotWidth, yFraction);
}
function inputTdrDisplay() {
  if (!inputTdrData) return { time_ns: [], series: {} };
  return sliceTdrDisplay(inputTdrData, 'input-tdr-time-start', 'input-tdr-time-end', 'input-tdr-display-points');
}
function inputTdrTraces(display) {
  return inputTdrNetworkOrder
    .filter((key) => display.series?.[key])
    .map((key) => ({
      key,
      label: `${inputTdrNetworkLabels[key]} · ${inputTdrData.parameter}`,
      values: display.series[key],
      color: inputTdrColors[key],
      dash: networkDash[key] || [],
      width: key === 'total' ? 2.1 : 1.8,
    }));
}
function drawInputTdrChart() {
  if (!inputTdrData) { drawLineChart(inputCanvas, [], []); return; }
  const display = inputTdrDisplay();
  drawLineChart(inputCanvas, display.time_ns, inputTdrTraces(display), { xDecimals: 3, yMin: inputChartYLimits.min, yMax: inputChartYLimits.max });
  if (inputChartHoverFraction !== null) positionInputTdrMarker(inputChartHoverFraction, inputChartHoverYFraction);
}
function positionInputTdrMarker(fraction, yFraction = inputChartHoverYFraction) {
  if (!inputTdrData || !inputChartState || !inputChartXMarker || !inputChartXMarkerLabel || !inputCanvas) return;
  const display = inputTdrDisplay();
  const traces = inputTdrTraces(display);
  if (!display.time_ns.length || !traces.length) { hideInputChartMarker(); return; }
  const rect = inputCanvas.getBoundingClientRect();
  const plotLeft = 53, plotRight = 16, plotTop = 14, plotBottom = 30;
  const plotWidth = rect.width - plotLeft - plotRight, plotHeight = rect.height - plotTop - plotBottom;
  if (plotWidth <= 0 || plotHeight <= 0) return;
  const normalized = Math.max(0, Math.min(1, fraction));
  inputChartHoverFraction = normalized; inputChartHoverYFraction = Math.max(0, Math.min(1, yFraction));
  const indexPosition = normalized * Math.max(0, display.time_ns.length - 1);
  const time = interpolatedSeriesValue(display.time_ns, indexPosition);
  const xValueField = document.getElementById('input-chart-x-value');
  if (xValueField && Number.isFinite(time)) xValueField.value = time.toFixed(6);
  const markerX = plotLeft + normalized * plotWidth;
  inputChartXMarker.style.left = `${markerX}px`;
  inputChartXMarkerLabel.textContent = `${time.toFixed(4)} ns`;
  inputChartXMarker.hidden = false;
  const markerValues = traces.map((trace) => ({ ...trace, value: interpolatedSeriesValue(trace.values, indexPosition) }));
  const scale = chartScaleWithLimits(markerValues.map((item) => item.value), inputChartYLimits);
  if (inputChartPointMarkers) {
    inputChartPointMarkers.innerHTML = '';
    markerValues.forEach((item) => {
      if (!scale || !Number.isFinite(item.value)) return;
      const dot = document.createElement('span'); dot.className = 'input-chart-point-marker';
      dot.style.left = `${markerX}px`;
      dot.style.top = `${plotTop + (scale.yMax - item.value) / (scale.yMax - scale.yMin) * plotHeight}px`;
      dot.style.backgroundColor = item.color;
      dot.title = `${item.label}: ${item.value.toFixed(2)} Ω`;
      inputChartPointMarkers.appendChild(dot);
    });
  }
  if (!inputChartHoverReadout) return;
  inputChartHoverReadout.innerHTML = '';
  const timeLine = document.createElement('div'); timeLine.className = 'input-chart-hover-frequency';
  timeLine.textContent = `${time.toFixed(4)} ns`; inputChartHoverReadout.appendChild(timeLine);
  markerValues.forEach((item) => {
    const row = document.createElement('div'); row.className = 'input-chart-hover-row';
    const name = document.createElement('span'); name.className = 'input-chart-hover-param';
    const swatch = document.createElement('i'); swatch.className = 'input-chart-hover-swatch'; swatch.style.backgroundColor = item.color;
    const code = document.createElement('span'); code.textContent = item.label;
    name.append(swatch, code);
    const valueNode = document.createElement('b'); valueNode.className = 'input-chart-hover-value';
    valueNode.textContent = Number.isFinite(item.value) ? `${item.value.toFixed(2)} Ω` : '—';
    row.append(name, valueNode); inputChartHoverReadout.appendChild(row);
  });
  inputChartHoverReadout.hidden = false;
  const wrapRect = inputChartWrap.getBoundingClientRect();
  const readoutWidth = Math.min(280, Math.max(190, wrapRect.width * .52)); inputChartHoverReadout.style.width = `${readoutWidth}px`;
  const left = markerX < wrapRect.width / 2 ? markerX + 12 : markerX - readoutWidth - 12;
  inputChartHoverReadout.style.left = `${Math.max(5, Math.min(wrapRect.width - readoutWidth - 5, left))}px`;
  const readoutHeight = inputChartHoverReadout.getBoundingClientRect().height || 50 + markerValues.length * 14;
  const top = inputChartHoverYFraction * wrapRect.height + 10;
  inputChartHoverReadout.style.top = `${Math.max(5, Math.min(wrapRect.height - readoutHeight - 5, top))}px`;
}
function updateInputTdrMarker(event) {
  if (!inputChartState || inputChartPanel.hidden || !inputTdrData) return;
  const rect = inputCanvas.getBoundingClientRect(); const plotWidth = rect.width - 53 - 16;
  const offsetX = event.clientX - rect.left - 53;
  if (plotWidth <= 0 || offsetX < 0 || offsetX > plotWidth) { hideInputChartMarker(); return; }
  const yFraction = rect.height > 0 ? (event.clientY - rect.top) / rect.height : .25;
  positionInputTdrMarker(offsetX / plotWidth, yFraction);
}
inputChartWrap.addEventListener('pointermove', (event) => {
  if (inputChartHoverReadout?.contains(event.target)) return;
  inputChartMarkerPinned = false;
  if (inputChartMode === 'tdr') updateInputTdrMarker(event); else updateInputChartMarker(event);
});
inputChartWrap.addEventListener('pointerleave', () => hideInputChartMarker());

document.getElementById('btn-generate-input-chart').addEventListener('click', showCombinedInputChart);
document.querySelectorAll('.quick-custom-toggle').forEach((button) => button.addEventListener('click', () => toggleCustomQuickEditor(button.dataset.customSlot)));
document.querySelectorAll('.quick-custom-add').forEach((button) => button.addEventListener('click', () => addCustomQuickParameter(button.dataset.customSlot)));
Object.entries(slotUi).forEach(([slot, ui]) => {
  const field = document.getElementById(ui.inputId);
  field.addEventListener('input', () => updateQuickParameterSelection(slot));
  field.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') { event.preventDefault(); showCombinedInputChart(); }
  });
  const customField = document.getElementById(`quick-custom-input-${quickParamSlug(slot)}`);
  customField.addEventListener('input', () => setQuickCustomMessage(slot, ''));
  customField.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') { event.preventDefault(); addCustomQuickParameter(slot); }
  });
});
function drawInputChart() {
  if (!inputChartState || inputChartPanel.hidden) return;
  if (inputChartMode === 'tdr') { drawInputTdrChart(); return; }
  const traces = inputChartState.display.traces;
  drawLineChart(inputCanvas, inputChartState.display.freq_ghz, traces, { yMin: inputChartYLimits.min, yMax: inputChartYLimits.max });
  if (inputChartHoverFraction !== null) positionInputChartMarker(inputChartHoverFraction, inputChartHoverYFraction);
}
function inputChartYAxisValues() {
  if (inputChartMode === 'tdr') return inputTdrTraces(inputTdrDisplay()).flatMap((trace) => trace.values);
  return inputChartState?.display?.traces?.flatMap((trace) => trace.values) || [];
}
function resultChartYAxisValues() {
  if (resultChartMode === 'tdr') {
    if (!resultTdrData) return [];
    const display = sliceTdrDisplay({ time_ns: resultTdrData.time_ns, series: resultTdrData.series }, 'result-tdr-time-start', 'result-tdr-time-end', 'result-tdr-display-points');
    return selectedNetworkKeys().flatMap((key) => display.series[key] || []);
  }
  if (!calculation) return [];
  const values = [];
  activeParameters.forEach((parameter) => selectedNetworkKeys().forEach((key) => {
    const series = calculation.chart.series[parameter]?.[key];
    if (series) values.push(...series);
  }));
  return values;
}
function parseAxisBound(id) {
  const raw = document.getElementById(id).value.trim();
  if (!raw) return { value: null };
  const value = Number(raw);
  return Number.isFinite(value) ? { value } : { error: '请输入有效的有限数值，或留空使用自动范围。' };
}
function setAxisControlStatus(id, message, isError = false) {
  const status = document.getElementById(id);
  status.textContent = message;
  status.classList.toggle('is-error', isError);
}
function applyYAxisRange(kind) {
  const isInput = kind === 'input';
  const minId = `${kind}-chart-y-min`, maxId = `${kind}-chart-y-max`;
  const statusId = `${kind}-chart-axis-status`;
  const minResult = parseAxisBound(minId), maxResult = parseAxisBound(maxId);
  if (minResult.error || maxResult.error) { setAxisControlStatus(statusId, minResult.error || maxResult.error, true); return; }
  const values = isInput ? inputChartYAxisValues() : resultChartYAxisValues();
  const automatic = chartScaleFromValues(values);
  if (!automatic) { setAxisControlStatus(statusId, '当前图表没有可用曲线。', true); return; }
  const min = minResult.value, max = maxResult.value;
  const actualMin = min ?? automatic.yMin, actualMax = max ?? automatic.yMax;
  if (actualMin >= actualMax) { setAxisControlStatus(statusId, 'Y 轴最小值必须小于最大值。', true); return; }
  if (isInput) inputChartYLimits = { min, max }; else resultChartYLimits = { min, max };
  const unit = (isInput ? inputChartMode : resultChartMode) === 'tdr' ? 'Ω' : 'dB';
  setAxisControlStatus(statusId, `Y 轴范围已应用：${actualMin}–${actualMax} ${unit}`);
  if (isInput) {
    drawInputChart();
    if (inputChartHoverFraction !== null) inputChartMode === 'tdr'
      ? positionInputTdrMarker(inputChartHoverFraction, inputChartHoverYFraction)
      : positionInputChartMarker(inputChartHoverFraction, inputChartHoverYFraction);
  } else drawResultChart();
}
function resetYAxisRange(kind, announce = true) {
  const isInput = kind === 'input';
  const minId = `${kind}-chart-y-min`, maxId = `${kind}-chart-y-max`;
  document.getElementById(minId).value = ''; document.getElementById(maxId).value = '';
  if (isInput) inputChartYLimits = { min: null, max: null }; else resultChartYLimits = { min: null, max: null };
  if (announce) setAxisControlStatus(`${kind}-chart-axis-status`, 'Y 轴已恢复自动缩放。');
  if (isInput) drawInputChart(); else drawResultChart();
}
function resetInputChartAxisControls() {
  inputChartYLimits = { min: null, max: null };
  document.getElementById('input-chart-y-min').value = '';
  document.getElementById('input-chart-y-max').value = '';
  document.getElementById('input-chart-x-value').value = '';
  document.getElementById('input-chart-x-unit').textContent = inputChartMode === 'tdr' ? 'ns' : 'GHz';
  setAxisControlStatus('input-chart-axis-status', 'Y 轴留空时自动缩放；可输入 X 值并定位标记线。');
  inputChartMarkerPinned = false;
}
function resetResultChartAxisControls() {
  resultChartYLimits = { min: null, max: null };
  document.getElementById('result-chart-y-min').value = '';
  document.getElementById('result-chart-y-max').value = '';
  document.getElementById('result-chart-x-value').value = '';
  document.getElementById('result-chart-x-unit').textContent = resultChartMode === 'tdr' ? 'ns' : 'GHz';
  setAxisControlStatus('result-chart-axis-status', 'Y 轴留空时自动缩放；可输入 X 值并定位标记线。');
  resultChartMarkerPinned = false;
}
function currentInputXValues() {
  return inputChartMode === 'tdr' ? inputTdrDisplay().time_ns : (inputChartState?.display?.freq_ghz || []);
}
function currentResultXValues() {
  if (resultChartMode !== 'tdr') return calculation?.chart?.freq_ghz || [];
  if (!resultTdrData) return [];
  return sliceTdrDisplay({ time_ns: resultTdrData.time_ns, series: resultTdrData.series }, 'result-tdr-time-start', 'result-tdr-time-end', 'result-tdr-display-points').time_ns;
}
function locateManualXMarker(kind) {
  const isInput = kind === 'input';
  const inputId = `${kind}-chart-x-value`, unitId = `${kind}-chart-x-unit`, statusId = `${kind}-chart-axis-status`;
  const field = document.getElementById(inputId), raw = field.value.trim();
  const mode = isInput ? inputChartMode : resultChartMode;
  const unit = mode === 'tdr' ? 'ns' : 'GHz';
  if (!raw) {
    if (isInput) { inputChartMarkerPinned = false; hideInputChartMarker(true); }
    else { resultChartMarkerPinned = false; hideResultChartMarker(true); }
    setAxisControlStatus(statusId, 'X 标记线已清除。'); return;
  }
  const target = Number(raw);
  if (!Number.isFinite(target)) { setAxisControlStatus(statusId, '请输入有效的 X 标记值。', true); return; }
  const xValues = isInput ? currentInputXValues() : currentResultXValues();
  const fraction = fractionForXAxisValue(xValues, target);
  if (fraction === null) {
    const first = xValues.length ? Number(xValues[0]) : NaN, last = xValues.length ? Number(xValues[xValues.length - 1]) : NaN;
    const range = Number.isFinite(first) && Number.isFinite(last) ? `当前显示范围为 ${first.toFixed(4)}–${last.toFixed(4)} ${unit}。` : '请先等待图表数据生成。';
    setAxisControlStatus(statusId, `该 X 值不在当前显示范围内。${range}`, true); return;
  }
  document.getElementById(unitId).textContent = unit;
  if (isInput) {
    inputChartMarkerPinned = true;
    inputChartMode === 'tdr' ? positionInputTdrMarker(fraction) : positionInputChartMarker(fraction);
  } else {
    resultChartMarkerPinned = true;
    resultChartMode === 'tdr' ? positionResultTdrMarker(fraction) : positionResultChartMarker(fraction);
  }
  setAxisControlStatus(statusId, `X 标记线已定位：${target.toFixed(4)} ${unit}`);
}
function bindChartAxisControls(kind) {
  document.getElementById(`btn-${kind}-y-apply`).addEventListener('click', () => applyYAxisRange(kind));
  document.getElementById(`btn-${kind}-y-auto`).addEventListener('click', () => resetYAxisRange(kind));
  document.getElementById(`btn-${kind}-x-locate`).addEventListener('click', () => locateManualXMarker(kind));
  document.getElementById(`${kind}-chart-x-value`).addEventListener('keydown', (event) => {
    if (event.key === 'Enter') { event.preventDefault(); locateManualXMarker(kind); }
  });
  [`${kind}-chart-y-min`, `${kind}-chart-y-max`].forEach((id) => document.getElementById(id).addEventListener('keydown', (event) => {
    if (event.key === 'Enter') { event.preventDefault(); applyYAxisRange(kind); }
  }));
}
bindChartAxisControls('input');
bindChartAxisControls('result');
document.getElementById('btn-close-input-chart').addEventListener('click', () => {
  inputChartPanel.hidden = true;
  inputTdrRequestId++;
  hideInputChartMarker(true);
});

function notifySettingChanged(title, detail) {
  if (calculation && !calculationBusy) setStatus('ready', title, detail, 'RE-RUN');
}
document.getElementById('port-map-select').addEventListener('change', () => {
  const hasCalculatedDiff = Boolean(calculation && calculation.nports === 4);
  if (hasCalculatedDiff) mappingRecalcNeeded = true;
  if (Object.values(files).every(Boolean)) inspectSelectedFiles();
  if (hasCalculatedDiff) setStatus('ready', '端口映射已切换', '映射关系与输入图表将刷新；当前去嵌结果仍使用旧映射，请重新运行计算。', 'RE-RUN');
});
document.getElementById('side-select').addEventListener('change', () => notifySettingChanged('去嵌范围已更改', '请重新运行去嵌，以更新 DUT 结果和下载文件。'));
document.getElementById('z0-input').addEventListener('change', () => {
  notifySettingChanged('参考阻抗已更改', '请重新运行去嵌，以按新的 Z₀ 重新归一化并计算。');
  if (inputChartMode === 'tdr') loadInputTdr();
});

function clearAll() {
  inspectionGeneration++;
  Object.keys(files).forEach((slot) => {
    files[slot] = null; fileInputs[slot].value = '';
    const ui = slotUi[slot];
    document.getElementById(ui.statusId).querySelector('.file-status-text').textContent = '尚未选择文件';
    document.getElementById(ui.cardId).classList.remove('has-file');
    const input = document.getElementById(ui.inputId); input.value = 'S21'; input.setAttribute('aria-invalid', 'false');
  });
  calculation = null; mappingRecalcNeeded = false; lastInspection = null; inputChartState = null;
  inputChartMode = 'sparam'; inputChartView.value = 'sparam'; resultChartMode = 'sparam'; resultChartView.value = 'sparam';
  inputTdrRequestId++; inputTdrData = null; resultTdrRequestId++; resultTdrData = null;
  hideInputChartMarker(true); hideResultChartMarker(true);
  inputChartMarkerPinned = false; resultChartMarkerPinned = false;
  resetInputChartAxisControls(); resetResultChartAxisControls();
  resultPanel.hidden = true; fileTools.hidden = true; inputChartPanel.hidden = true;
  setStatus('ready', '等待输入文件', '选择 Total、2X Thru A 与 2X Thru B 后，即可运行计算。', 'READY');
}
document.getElementById('btn-clear').addEventListener('click', clearAll);

function hideResultChartMarker(force = false) {
  if (resultChartMarkerPinned && !force) return;
  resultChartMarkerPinned = false;
  resultChartHoverFraction = null;
  if (resultChartCrosshair) resultChartCrosshair.hidden = true;
  if (resultChartPoints) resultChartPoints.innerHTML = '';
  if (tooltip) tooltip.style.display = 'none';
}
function positionResultChartMarker(fraction, yFraction = resultChartHoverYFraction) {
  if (!calculation || resultPanel.hidden || !canvas || !resultChartCrosshair || !tooltip) return;
  const box = canvas.getBoundingClientRect();
  const plotLeft = 53, plotRight = 16, plotTop = 14, plotBottom = 30;
  const plotW = box.width - plotLeft - plotRight, plotH = box.height - plotTop - plotBottom;
  if (plotW <= 0 || plotH <= 0) return;
  const normalized = Math.max(0, Math.min(1, fraction));
  resultChartHoverFraction = normalized;
  resultChartHoverYFraction = Math.max(0, Math.min(1, yFraction));
  const freq = calculation.chart.freq_ghz;
  const indexPosition = normalized * Math.max(0, freq.length - 1);
  const lower = Math.floor(indexPosition), upper = Math.min(freq.length - 1, lower + 1);
  const part = indexPosition - lower;
  const frequency = Number(freq[lower]) + (Number(freq[upper]) - Number(freq[lower])) * part;
  const xValueField = document.getElementById('result-chart-x-value');
  if (xValueField && Number.isFinite(frequency)) xValueField.value = frequency.toFixed(6);
  const markerX = plotLeft + normalized * plotW;
  resultChartCrosshair.style.left = `${markerX}px`;
  resultChartCrosshair.hidden = false;

  const traces = [];
  activeParameters.forEach((parameter, parameterIndex) => {
    const color = parameterColors[parameterIndex % parameterColors.length];
    selectedNetworkKeys().forEach((networkKey) => {
      const values = calculation.chart.series[parameter]?.[networkKey];
      if (values) traces.push({ parameter, networkKey, values, color });
    });
  });
  const scale = chartScaleWithLimits(traces.flatMap((trace) => trace.values), resultChartYLimits);
  const currentValues = traces.map((trace) => ({ ...trace, value: interpolatedSeriesValue(trace.values, indexPosition) }));
  if (resultChartPoints) {
    resultChartPoints.innerHTML = '';
    currentValues.forEach((trace) => {
      if (!scale || !Number.isFinite(trace.value)) return;
      const dot = document.createElement('span');
      dot.className = 'result-chart-point-marker';
      dot.style.left = `${markerX}px`;
      dot.style.top = `${plotTop + (scale.yMax - trace.value) / (scale.yMax - scale.yMin) * plotH}px`;
      dot.style.backgroundColor = trace.color;
      dot.title = `${trace.parameter} · ${networkLabels[trace.networkKey]} ${trace.value.toFixed(2)} dB`;
      resultChartPoints.appendChild(dot);
    });
  }
  const rows = currentValues
    .filter((trace) => Number.isFinite(trace.value))
    .map((trace) => `<span style="color:${trace.color}">${trace.parameter} · ${networkLabels[trace.networkKey]} ${trace.value.toFixed(2)} dB</span>`);
  tooltip.innerHTML = `<b>${frequency.toFixed(4)} GHz</b><br>${rows.join('<br>')}`;
  tooltip.style.display = 'block';
  const tooltipWidth = tooltip.getBoundingClientRect().width || 180;
  const tooltipHeight = tooltip.getBoundingClientRect().height || 50;
  let left = markerX + 12;
  if (left + tooltipWidth > box.width - 4) left = markerX - tooltipWidth - 12;
  tooltip.style.left = `${Math.max(4, Math.min(box.width - tooltipWidth - 4, left))}px`;
  const top = resultChartHoverYFraction * box.height - 48;
  tooltip.style.top = `${Math.max(3, Math.min(box.height - tooltipHeight - 3, top))}px`;
}
function positionResultTdrMarker(fraction, yFraction = resultChartHoverYFraction) {
  if (!resultTdrData || resultPanel.hidden || !canvas || !resultChartCrosshair || !tooltip) return;
  const visibleKeys = selectedNetworkKeys().filter((key) => resultTdrData.series?.[key]);
  const display = sliceTdrDisplay({ time_ns: resultTdrData.time_ns, series: resultTdrData.series }, 'result-tdr-time-start', 'result-tdr-time-end', 'result-tdr-display-points');
  if (!display.time_ns.length) { hideResultChartMarker(); return; }
  const box = canvas.getBoundingClientRect();
  const plotLeft = 53, plotRight = 16, plotTop = 14, plotBottom = 30;
  const plotW = box.width - plotLeft - plotRight, plotH = box.height - plotTop - plotBottom;
  if (plotW <= 0 || plotH <= 0) return;
  const normalized = Math.max(0, Math.min(1, fraction));
  resultChartHoverFraction = normalized;
  resultChartHoverYFraction = Math.max(0, Math.min(1, yFraction));
  const indexPosition = normalized * Math.max(0, display.time_ns.length - 1);
  const frequency = interpolatedSeriesValue(display.time_ns, indexPosition);
  const xValueField = document.getElementById('result-chart-x-value');
  if (xValueField && Number.isFinite(frequency)) xValueField.value = frequency.toFixed(6);
  const markerX = plotLeft + normalized * plotW;
  resultChartCrosshair.style.left = `${markerX}px`; resultChartCrosshair.hidden = false;
  const currentValues = visibleKeys.map((key) => ({ key, value: interpolatedSeriesValue(display.series[key], indexPosition), color: networkColorDots[key] }));
  const scale = chartScaleWithLimits(visibleKeys.flatMap((key) => display.series[key] || []), resultChartYLimits);
  if (resultChartPoints) {
    resultChartPoints.innerHTML = '';
    currentValues.forEach((trace) => {
      if (!scale || !Number.isFinite(trace.value)) return;
      const dot = document.createElement('span'); dot.className = 'result-chart-point-marker';
      dot.style.left = `${markerX}px`; dot.style.top = `${plotTop + (scale.yMax - trace.value) / (scale.yMax - scale.yMin) * plotH}px`;
      dot.style.backgroundColor = trace.color; dot.title = `${networkLabels[trace.key]}: ${trace.value.toFixed(2)} Ω`;
      resultChartPoints.appendChild(dot);
    });
  }
  const rows = currentValues.filter((trace) => Number.isFinite(trace.value)).map((trace) => `<span style="color:${trace.color}">${networkLabels[trace.key]} ${trace.value.toFixed(2)} Ω</span>`);
  tooltip.innerHTML = `<b>${frequency.toFixed(4)} ns</b><br>${rows.join('<br>')}`;
  tooltip.style.display = 'block';
  const tooltipWidth = tooltip.getBoundingClientRect().width || 180;
  const tooltipHeight = tooltip.getBoundingClientRect().height || 50;
  let left = markerX + 12; if (left + tooltipWidth > box.width - 4) left = markerX - tooltipWidth - 12;
  tooltip.style.left = `${Math.max(4, Math.min(box.width - tooltipWidth - 4, left))}px`;
  const top = resultChartHoverYFraction * box.height - 48;
  tooltip.style.top = `${Math.max(3, Math.min(box.height - tooltipHeight - 3, top))}px`;
}
function updateResultTdrMarker(event) {
  if (!calculation || resultPanel.hidden || !resultTdrData) return;
  const box = canvas.getBoundingClientRect(); const plotW = box.width - 53 - 16;
  const offsetX = event.clientX - box.left - 53;
  if (plotW <= 0 || offsetX < 0 || offsetX > plotW) { hideResultChartMarker(); return; }
  const yFraction = box.height > 0 ? (event.clientY - box.top) / box.height : .25;
  positionResultTdrMarker(offsetX / plotW, yFraction);
}
function updateResultChartMarker(event) {
  resultChartMarkerPinned = false;
  if (resultChartMode === 'tdr') { updateResultTdrMarker(event); return; }
  if (!calculation || resultPanel.hidden) return;
  const box = canvas.getBoundingClientRect();
  const plotW = box.width - 53 - 16;
  const offsetX = event.clientX - box.left - 53;
  if (plotW <= 0 || offsetX < 0 || offsetX > plotW) { hideResultChartMarker(); return; }
  const yFraction = box.height > 0 ? (event.clientY - box.top) / box.height : .25;
  positionResultChartMarker(offsetX / plotW, yFraction);
}
canvas.addEventListener('mousemove', updateResultChartMarker);
canvas.addEventListener('mouseleave', () => hideResultChartMarker());
window.addEventListener('resize', () => {
  drawResultChart(); drawInputChart();
  if (inputChartHoverFraction !== null) {
    if (inputChartMode === 'tdr') positionInputTdrMarker(inputChartHoverFraction, inputChartHoverYFraction);
    else positionInputChartMarker(inputChartHoverFraction, inputChartHoverYFraction);
  }
});

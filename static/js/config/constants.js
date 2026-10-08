/**
 * 前端常量与静态配置：颜色、标签、限制、API 路径。
 * 集中一处便于主题化与后续扩展（例如新增网络类型或图表模式）。
 */

export const API_PATHS = {
  inspect: '/api/inspect',
  deembed: '/api/deembed',
  tdrInput: '/api/tdr/input',
  tdrResult: '/api/tdr/result',
  download: (token, key) => `/api/download/${encodeURIComponent(token)}/${key}`,
};

/** 上传槽位 → DOM id 映射 */
export const SLOT_UI = {
  thru_a: {
    statusId: 'status-thru-a',
    cardId: 'card-thru-a',
    label: '2X Thru A',
    inputId: 'input-param-thru-a',
    noteId: 'param-note-thru-a',
    chartLabel: '2X Thru A',
  },
  total: {
    statusId: 'status-total',
    cardId: 'card-total',
    label: 'Total',
    inputId: 'input-param-total',
    noteId: 'param-note-total',
    chartLabel: 'Total Network',
  },
  thru_b: {
    statusId: 'status-thru-b',
    cardId: 'card-thru-b',
    label: '2X Thru B',
    inputId: 'input-param-thru-b',
    noteId: 'param-note-thru-b',
    chartLabel: '2X Thru B',
  },
};

export const SLOT_KEYS = ['thru_a', 'total', 'thru_b'];

export const NETWORK_LABELS = {
  total: 'Total',
  dut: 'DUT 去嵌',
  fix_a: '1X A',
  fix_b: '1X B',
  thru_a: '2X A',
  thru_b: '2X B',
};

export const NETWORK_DASH = {
  total: [6, 4],
  dut: [],
  fix_a: [2, 3],
  fix_b: [8, 3, 2, 3],
  thru_a: [4, 2],
  thru_b: [1, 4],
};

export const NETWORK_DOT_COLORS = {
  total: '#91a5b8',
  dut: '#54e1d2',
  fix_a: '#67c98f',
  fix_b: '#f3b55f',
  thru_a: '#7aaeff',
  thru_b: '#e987ba',
};

export const PARAMETER_COLORS = ['#54e1d2', '#f3b55f', '#7aaeff', '#e987ba', '#bd93f9', '#a3e635', '#ff8e6b', '#5bc0eb'];

export const INPUT_PARAMETER_DASHES = [[], [6, 3], [2, 3], [8, 3, 2, 3], [1, 3], [6, 2, 1, 2], [9, 2], [3, 1]];

export const INPUT_TDR_COLORS = { total: '#7aaeff', thru_a: '#54e1d2', thru_b: '#f3b55f' };
export const INPUT_TDR_NETWORK_ORDER = ['thru_a', 'total', 'thru_b'];
export const INPUT_TDR_NETWORK_LABELS = { thru_a: '2X Thru A', total: 'Total', thru_b: '2X Thru B' };

export const MAX_CHART_PARAMETERS = 8;
export const MAX_QUICK_PARAMETERS = 32;
export const QUICK_PARAM_STORAGE_KEY = 'rf-deembed-custom-quick-parameters-v1';

export const DEFAULT_QUICK_PARAMETERS = {
  2: ['S11', 'S21', 'S12', 'S22'],
  4: ['SDD11', 'SDD21', 'SCD21', 'SCC21', 'SDC21', 'S11', 'S21'],
};

/** 参数代码校验：Sij 或混合模 SDD/SCC/SCD/SDC + 11/12/21/22 */
export const PARAMETER_PATTERN = /^(?:S[1-4][1-4]|S(?:DD|CC|CD|DC)(?:11|12|21|22))$/;

/** 画布内边距（与 charts/renderer.js 共用） */
export const CHART_PADDING = { left: 53, right: 16, top: 14, bottom: 30 };

export const TDR_DISPLAY_POINTS_DEFAULT = 6000;

export const STATUS_TAGS = { ready: 'READY', busy: 'RUNNING', success: 'DONE', error: 'ERROR' };

export const FILE_EXTENSION_PATTERN = /\.(s2p|s4p|snp|ts|txt)$/i;

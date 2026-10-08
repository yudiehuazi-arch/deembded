/** 后端 API 客户端：统一表单提交、JSON 解析与错误语义。 */

import { API_PATHS } from '../config/constants.js';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export class DeembedApi {
  constructor({ fetchImpl = (...args) => window.fetch(...args), paths = API_PATHS } = {}) {
    this.fetch = fetchImpl;
    this.paths = paths;
  }

  /** 提交 multipart 表单并解析 JSON；失败时抛出带 status 的 ApiError。 */
  async _postForm(path, form) {
    const response = await this.fetch(path, { method: 'POST', body: form });
    const data = await response.json().catch(() => ({}));
    return { response, data };
  }

  async inspect({ files, portMapping = 'auto', token = null }) {
    const form = new FormData();
    if (token) {
      form.append('inspection_token', token);
    } else {
      form.append('total', files.total, files.total.name);
      form.append('thru_a', files.thru_a, files.thru_a.name);
      form.append('thru_b', files.thru_b, files.thru_b.name);
    }
    form.append('port_mapping', portMapping);
    const { response, data } = await this._postForm(this.paths.inspect, form);
    if (!response.ok) throw new ApiError(data.detail || `服务器返回 HTTP ${response.status}`, response.status);
    return data;
  }

  async deembed({ files = null, token = null, side = 'both', portMapping = 'auto', referenceZ0 = 50 }) {
    const form = new FormData();
    if (files) {
      form.append('total', files.total, files.total.name);
      form.append('thru_a', files.thru_a, files.thru_a.name);
      form.append('thru_b', files.thru_b, files.thru_b.name);
    } else if (token) {
      form.append('inspection_token', token);
    }
    form.append('side', side);
    form.append('port_mapping', portMapping);
    form.append('reference_z0', String(referenceZ0));
    const { response, data } = await this._postForm(this.paths.deembed, form);
    if (!response.ok) throw new ApiError(data.detail || data.message || `服务器返回 HTTP ${response.status}`, response.status);
    if (data.success === false) throw new ApiError(data.detail || data.message || '计算未成功完成。', response.status);
    return data;
  }

  async tdrInput({ inspectionToken, port, portMapping, referenceZ0, window: tdrWindow, dcMethod, riseTimePs, slot = 'all' }) {
    const form = new FormData();
    form.append('inspection_token', inspectionToken);
    form.append('slot', slot);
    form.append('port', port);
    form.append('port_mapping', portMapping);
    form.append('reference_z0', referenceZ0);
    form.append('window', tdrWindow);
    form.append('dc_method', dcMethod);
    form.append('rise_time_ps', riseTimePs);
    const { response, data } = await this._postForm(this.paths.tdrInput, form);
    if (!response.ok) throw new ApiError(data.detail || `服务器返回 HTTP ${response.status}`, response.status);
    return data;
  }

  async tdrResult({ inspectionToken, resultToken, port, portMapping, referenceZ0, window: tdrWindow, dcMethod, riseTimePs }) {
    const form = new FormData();
    form.append('inspection_token', inspectionToken);
    form.append('result_token', resultToken);
    form.append('port', port);
    form.append('port_mapping', portMapping);
    form.append('reference_z0', referenceZ0);
    form.append('window', tdrWindow);
    form.append('dc_method', dcMethod);
    form.append('rise_time_ps', riseTimePs);
    const { response, data } = await this._postForm(this.paths.tdrResult, form);
    if (!response.ok) throw new ApiError(data.detail || `服务器返回 HTTP ${response.status}`, response.status);
    return data;
  }

  downloadUrl(token, networkKey) {
    return this.paths.download(token, networkKey);
  }
}

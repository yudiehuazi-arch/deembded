/** 浏览器本地存储：自定义快捷参数。 */

import { MAX_QUICK_PARAMETERS, QUICK_PARAM_STORAGE_KEY } from '../config/constants.js';
import { isValidParameterCode } from './format.js';

export class QuickParameterStore {
  constructor({ storage = globalThis.localStorage, key = QUICK_PARAM_STORAGE_KEY } = {}) {
    this.storage = storage;
    this.key = key;
    this.codes = this.load();
  }

  load() {
    try {
      const raw = JSON.parse(this.storage?.getItem(this.key) || '[]');
      if (!Array.isArray(raw)) return [];
      return [...new Set(raw.map((item) => String(item).trim().toUpperCase()).filter(isValidParameterCode))].slice(
        0,
        MAX_QUICK_PARAMETERS,
      );
    } catch (_) {
      return [];
    }
  }

  save() {
    try {
      this.storage?.setItem(this.key, JSON.stringify(this.codes));
    } catch (_) {
      /* 隐私模式或沙箱环境可能禁用 localStorage，忽略即可。 */
    }
  }

  has(code) {
    return this.codes.includes(code);
  }

  get isFull() {
    return this.codes.length >= MAX_QUICK_PARAMETERS;
  }

  /** 归一化后写入；非法代码直接忽略，返回是否新增。 */
  add(code) {
    const normalized = String(code).trim().toUpperCase();
    if (!isValidParameterCode(normalized) || this.has(normalized)) return false;
    this.codes.push(normalized);
    this.save();
    return true;
  }

  remove(code) {
    const normalized = String(code).trim().toUpperCase();
    this.codes = this.codes.filter((item) => item !== normalized);
    this.save();
  }
}

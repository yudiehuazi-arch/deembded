/** 应用状态：所有可变数据的唯一来源。

视图（View）只读取状态并通过控制器（Workbench）修改状态，避免散落的
全局变量与隐式耦合。
 */

import { SLOT_KEYS } from '../config/constants.js';
import { QuickParameterStore } from './storage.js';

export class WorkbenchState {
  constructor({ quickParameters = new QuickParameterStore() } = {}) {
    this.quickParameters = quickParameters;
    this.files = { thru_a: null, total: null, thru_b: null };
    this.inspection = null;       // /api/inspect 最近一次成功响应
    this.calculation = null;      // /api/deembed 最近一次成功响应
    this.inspectionGeneration = 0; // 竞态保护：丢弃过期的识别响应
    this.calculationBusy = false;
    this.mappingRecalcNeeded = false;
  }

  allFilesSelected() {
    return SLOT_KEYS.every((slot) => Boolean(this.files[slot]));
  }

  setFile(slot, file) {
    this.files[slot] = file;
    this.calculation = null;
    this.inspection = null;
    this.mappingRecalcNeeded = false;
  }

  nextInspectionGeneration() {
    return ++this.inspectionGeneration;
  }

  reset() {
    this.files = { thru_a: null, total: null, thru_b: null };
    this.inspection = null;
    this.calculation = null;
    this.inspectionGeneration++;
    this.calculationBusy = false;
    this.mappingRecalcNeeded = false;
  }
}

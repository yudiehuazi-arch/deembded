/** 底部状态栏控制器：所有流程反馈的唯一出口。 */

import { $ } from '../core/dom.js';
import { STATUS_TAGS } from '../config/constants.js';

export class StatusPanel {
  constructor({ panelId = 'status-panel', titleId = 'status-title', detailId = 'status-detail', tagId = 'status-tag' } = {}) {
    this.panel = $(panelId);
    this.title = $(titleId);
    this.detail = $(detailId);
    this.tag = $(tagId);
  }

  set(kind, title, detail, tag) {
    this.panel?.classList.remove('status-error', 'status-success', 'is-busy');
    if (kind === 'error') this.panel?.classList.add('status-error');
    if (kind === 'success') this.panel?.classList.add('status-success');
    if (kind === 'busy') this.panel?.classList.add('is-busy');
    if (this.title) this.title.textContent = title;
    if (this.detail) this.detail.textContent = detail;
    if (this.tag) this.tag.textContent = tag || STATUS_TAGS[kind] || 'READY';
  }
}

/** 上传卡片：文件选择、拖拽与文件状态显示。 */

import { FILE_EXTENSION_PATTERN, SLOT_KEYS, SLOT_UI } from '../config/constants.js';
import { $ } from '../core/dom.js';
import { formatSize } from '../core/format.js';

export class UploadPanel {
  constructor({ onFileSelected, onInvalidFile }) {
    this.onFileSelected = onFileSelected;
    this.onInvalidFile = onInvalidFile;
    this.inputs = {
      thru_a: $('file-thru-a'),
      total: $('file-total'),
      thru_b: $('file-thru-b'),
    };
  }

  attach() {
    Object.entries(this.inputs).forEach(([slot, input]) =>
      input?.addEventListener('change', (event) => this.selectFile(slot, event.target.files?.[0])),
    );

    document.querySelectorAll('.choose-file-btn').forEach((button) =>
      button.addEventListener('click', () => $(button.dataset.for)?.click()),
    );

    document.querySelectorAll('.upload-card').forEach((card) => {
      card.addEventListener('dragover', (event) => {
        event.preventDefault();
        card.classList.add('drag-over');
      });
      card.addEventListener('dragleave', (event) => {
        if (!card.contains(event.relatedTarget)) card.classList.remove('drag-over');
      });
      card.addEventListener('drop', (event) => {
        event.preventDefault();
        card.classList.remove('drag-over');
        this.selectFile(card.dataset.slot, event.dataTransfer?.files?.[0]);
      });
    });
  }

  selectFile(slot, file) {
    if (!file) return;
    if (!FILE_EXTENSION_PATTERN.test(file.name)) {
      this.onInvalidFile?.(file);
      return;
    }
    this.renderFileStatus(slot, file);
    this.onFileSelected?.(slot, file);
  }

  renderFileStatus(slot, file) {
    const ui = SLOT_UI[slot];
    if (!ui) return;
    const status = $(ui.statusId);
    const text = status?.querySelector('.file-status-text');
    if (text) text.textContent = `${file.name} · ${formatSize(file.size)}`;
    $(ui.cardId)?.classList.add('has-file');
  }

  clearSlot(slot) {
    const ui = SLOT_UI[slot];
    if (!ui) return;
    const status = $(ui.statusId);
    const text = status?.querySelector('.file-status-text');
    if (text) text.textContent = '尚未选择文件';
    $(ui.cardId)?.classList.remove('has-file');
    const input = this.inputs[slot];
    if (input) input.value = '';
  }

  clearAll() {
    SLOT_KEYS.forEach((slot) => this.clearSlot(slot));
  }
}

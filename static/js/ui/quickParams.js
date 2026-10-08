/** 快捷参数芯片与自定义快捷项编辑器。 */

import { DEFAULT_QUICK_PARAMETERS, MAX_CHART_PARAMETERS, SLOT_UI } from '../config/constants.js';
import { $, createElement } from '../core/dom.js';
import { isValidParameterCode, splitParameterCodes } from '../core/format.js';
import { toggleParameterCode } from '../core/params.js';

const slotSlug = (slot) => slot.replaceAll('_', '-');

export class QuickParameterController {
  constructor({ state, onFieldChanged }) {
    this.state = state;
    this.onFieldChanged = onFieldChanged;
    this.lastNports = 2;
    this.lastPreviews = null;
  }

  attach() {
    document.querySelectorAll('.quick-custom-toggle').forEach((button) =>
      button.addEventListener('click', () => this.toggleEditor(button.dataset.customSlot)),
    );
    document.querySelectorAll('.quick-custom-add').forEach((button) =>
      button.addEventListener('click', () => this.addCustom(button.dataset.customSlot)),
    );
    Object.entries(SLOT_UI).forEach(([slot, ui]) => {
      const field = $(ui.inputId);
      field?.addEventListener('input', () => this.refreshSelection(slot));
      field?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          this.onFieldChanged?.(slot, { submit: true });
        }
      });
      const customField = $(`quick-custom-input-${slotSlug(slot)}`);
      customField?.addEventListener('input', () => this.setMessage(slot, ''));
      customField?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          this.addCustom(slot);
        }
      });
    });
  }

  setMessage(slot, message, isError = false) {
    const element = $(`quick-custom-message-${slotSlug(slot)}`);
    if (!element) return;
    element.textContent = message;
    element.classList.toggle('is-error', isError);
  }

  /** 依据当前识别结果重建三个文件的快捷芯片。 */
  render(nports, previews) {
    this.lastNports = nports;
    this.lastPreviews = previews || this.lastPreviews;
    const presets = DEFAULT_QUICK_PARAMETERS[nports] || [];
    Object.entries(SLOT_UI).forEach(([slot, ui]) => {
      const container = $(`quick-params-${slotSlug(slot)}`);
      const field = $(ui.inputId);
      if (!container || !field) return;
      container.innerHTML = '';
      const available = new Set(Object.keys(this.lastPreviews?.[slot]?.series || {}));
      const codes = [...new Set([...presets, ...this.state.quickParameters.codes])].filter((code) => available.has(code));
      const selected = new Set(splitParameterCodes(field.value));

      codes.forEach((code) => {
        const isCustom = this.state.quickParameters.has(code) && !presets.includes(code);
        const wrapper = isCustom ? createElement('span', { className: 'quick-param-custom' }) : container;
        const chip = createElement('button', {
          className: `quick-param-chip${selected.has(code) ? ' is-active' : ''}`,
          text: code,
          attrs: {
            type: 'button',
            'aria-pressed': String(selected.has(code)),
            title: selected.has(code) ? '点击移除该参数' : '点击添加该参数',
          },
        });
        chip.dataset.quickParam = code;
        chip.addEventListener('click', () => this.toggle(slot, code));
        wrapper.appendChild(chip);

        if (isCustom) {
          const remove = createElement('button', {
            className: 'quick-param-remove',
            text: '×',
            attrs: { type: 'button', title: `移除自定义快捷项 ${code}`, 'aria-label': `移除自定义快捷项 ${code}` },
          });
          remove.addEventListener('click', () => this.removeCustom(slot, code));
          wrapper.appendChild(remove);
          container.appendChild(wrapper);
        }
      });
    });
  }

  refreshSelection(slot) {
    const container = $(`quick-params-${slotSlug(slot)}`);
    const field = $(SLOT_UI[slot]?.inputId);
    if (!container || !field) return;
    const selected = new Set(splitParameterCodes(field.value));
    container.querySelectorAll('.quick-param-chip').forEach((chip) => {
      const active = selected.has(chip.dataset.quickParam);
      chip.classList.toggle('is-active', active);
      chip.setAttribute('aria-pressed', String(active));
      chip.title = active ? '点击移除该参数' : '点击添加该参数';
    });
  }

  toggle(slot, code) {
    const field = $(SLOT_UI[slot]?.inputId);
    if (!field) return;
    const { value, overflow } = toggleParameterCode(field.value, code, MAX_CHART_PARAMETERS);
    if (overflow) {
      const note = $(SLOT_UI[slot].noteId);
      if (note) {
        note.textContent = `每张图最多绘制 ${MAX_CHART_PARAMETERS} 条曲线；请先移除一项。`;
        note.classList.add('is-error');
      }
      return;
    }
    field.value = value;
    field.setAttribute('aria-invalid', 'false');
    $(SLOT_UI[slot].noteId)?.classList.remove('is-error');
    field.dispatchEvent(new Event('input', { bubbles: true }));
  }

  toggleEditor(slot) {
    const slug = slotSlug(slot);
    const editor = $(`quick-custom-editor-${slug}`);
    const field = $(`quick-custom-input-${slug}`);
    const toggle = document.querySelector(`.quick-custom-toggle[data-custom-slot="${slot}"]`);
    if (!editor) return;
    editor.hidden = !editor.hidden;
    toggle?.setAttribute('aria-expanded', String(!editor.hidden));
    this.setMessage(slot, '');
    if (!editor.hidden) field?.focus();
  }

  addCustom(slot) {
    const slug = slotSlug(slot);
    const field = $(`quick-custom-input-${slug}`);
    if (!field) return;
    const code = field.value.trim().toUpperCase();
    if (!code) {
      this.setMessage(slot, '请输入一个 S 参数，例如 SDD21。', true);
      return;
    }
    if (!isValidParameterCode(code)) {
      this.setMessage(slot, '格式无效，例如 S43、SDD21 或 SCD21。', true);
      return;
    }
    const available = new Set(Object.keys(this.lastPreviews?.[slot]?.series || {}));
    if (!available.has(code)) {
      this.setMessage(slot, `当前文件不支持 ${code}。`, true);
      return;
    }
    if ((DEFAULT_QUICK_PARAMETERS[this.lastNports] || []).includes(code)) {
      this.setMessage(slot, `${code} 已在默认快捷项中。`);
      return;
    }
    if (this.state.quickParameters.has(code)) {
      this.setMessage(slot, `${code} 已存在于自定义快捷项中。`);
      return;
    }
    if (this.state.quickParameters.isFull) {
      this.setMessage(slot, '自定义快捷项最多保存 32 个。', true);
      return;
    }
    this.state.quickParameters.add(code);
    this.render(this.lastNports, this.lastPreviews);
    field.value = '';
    this.setMessage(slot, `${code} 已添加；点击快捷项即可加入或移出图表。`);
  }

  removeCustom(slot, code) {
    this.state.quickParameters.remove(code);
    this.render(this.lastNports, this.lastPreviews);
    this.setMessage(slot, `${code} 已从快捷项中移除。`);
  }
}

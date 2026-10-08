/** TDR 控件读取器：把输入图表/结果图表的 TDR 面板参数转成接口请求。 */

import { TDR_DISPLAY_POINTS_DEFAULT } from '../config/constants.js';
import { $ } from '../core/dom.js';

export class TdrControls {
  /** @param {'input'|'result'} prefix 控件 id 前缀 */
  constructor(prefix) {
    this.prefix = prefix;
  }

  id(suffix) {
    return `${this.prefix}-tdr-${suffix}`;
  }

  value(suffix, fallback = '') {
    const element = $(this.id(suffix));
    return element ? element.value : fallback;
  }

  /** 反射端口 / 频域窗 / DC 外推 / 上升时间。 */
  readSettings({ portMapping = 'auto', referenceZ0 = 50 } = {}) {
    return {
      port: this.value('port', '1'),
      portMapping,
      referenceZ0,
      window: this.value('window', 'hamming'),
      dcMethod: this.value('dc', 'linear'),
      riseTimePs: this.value('rise', '0') || '0',
    };
  }

  readTimeWindow() {
    return {
      startNs: this.value('time-start', '0'),
      endNs: this.value('time-end', ''),
      pointLimit: Number.parseInt(this.value('display-points', String(TDR_DISPLAY_POINTS_DEFAULT)) || String(TDR_DISPLAY_POINTS_DEFAULT), 10),
    };
  }

  /** 端口下拉框文案：4 端口显示差分端口。 */
  updatePortOptions(nports) {
    const port = $(this.id('port'));
    if (!port) return;
    const differential = nports === 4;
    if (port.options[0]) port.options[0].textContent = differential ? '差分端口 1 · SDD11' : '单端端口 1 · S11';
    if (port.options[1]) port.options[1].textContent = differential ? '差分端口 2 · SDD22' : '单端端口 2 · S22';
  }

  /** 当前选择的反射参数名（用于标题/图例提示）。 */
  parameterName(nports) {
    const second = this.value('port', '1') === '2';
    if (nports === 4) return second ? 'SDD22' : 'SDD11';
    return second ? 'S22' : 'S11';
  }

  /** 绑定控件变化：settings 变化重新请求，时间窗变化仅重绘。 */
  bind({ onSettingsChanged, onWindowChanged }) {
    ['port', 'dc', 'window', 'rise'].forEach((suffix) =>
      $(this.id(suffix))?.addEventListener('change', () => onSettingsChanged?.()),
    );
    ['time-start', 'time-end', 'display-points'].forEach((suffix) =>
      $(this.id(suffix))?.addEventListener('input', () => onWindowChanged?.()),
    );
  }
}

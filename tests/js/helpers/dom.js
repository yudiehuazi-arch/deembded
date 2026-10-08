/** 测试 DOM 环境工厂：用 jsdom 提供 window/document，供视图与控制器单测使用。 */

import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const INDEX_HTML = new URL('../../../static/index.html', import.meta.url);

export function installDom(html = '<!doctype html><html><body></body></html>') {
  const dom = new JSDOM(html, { pretendToBeVisual: true, url: 'http://localhost/' });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.Element = dom.window.Element;
  globalThis.Event = dom.window.Event;
  globalThis.KeyboardEvent = dom.window.KeyboardEvent;
  globalThis.localStorage = dom.window.localStorage;
  globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);
  globalThis.cancelAnimationFrame = (handle) => clearTimeout(handle);
  return dom;
}

/** 装上真实 static/index.html，并按测试需要补齐 jsdom 未实现的浏览器 API。 */
export function installAppDom() {
  const dom = installDom(readFileSync(INDEX_HTML, 'utf8'));
  const { window: jsdomWindow } = dom;

  jsdomWindow.Element.prototype.scrollIntoView = function scrollIntoView() {};
  jsdomWindow.URL.createObjectURL = () => 'blob:test';
  jsdomWindow.URL.revokeObjectURL = () => {};
  jsdomWindow.HTMLCanvasElement.prototype.getContext = () => fakeContext();

  // 统一给元素一个可视尺寸（jsdom 默认全为 0，会让图表直接跳过绘制）。
  jsdomWindow.Element.prototype.getBoundingClientRect = function getBoundingClientRect() {
    return { x: 0, y: 0, left: 0, top: 0, right: 640, bottom: 320, width: 640, height: 320, toJSON: () => ({}) };
  };
  return dom;
}

/** 记录型 fetch：按 URL 返回预设 JSON，并保留每次请求的表单内容。 */
export function stubFetch(routes) {
  const calls = [];
  const handler = {
    inspect: routes.inspect,
    deembed: routes.deembed,
    tdrInput: routes.tdrInput,
    tdrResult: routes.tdrResult,
  };
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, form: options.body });
    const key = url.includes('/tdr/input')
      ? 'tdrInput'
      : url.includes('/tdr/result')
        ? 'tdrResult'
        : url.includes('/inspect')
          ? 'inspect'
          : url.includes('/deembed')
            ? 'deembed'
            : null;
    const queued = handler[key];
    const payload = typeof queued === 'function' ? queued({ index: calls.length, key, url, form: options.body }) : queued;
    if (payload && payload.__status && payload.__status >= 400) {
      return { ok: false, status: payload.__status, json: async () => payload };
    }
    return { ok: true, status: 200, json: async () => payload ?? {} };
  };
  return { fetchImpl, calls };
}

/** 画出 2D 上下文的空实现（jsdom 不提供 canvas 后端）。 */
export function fakeContext() {
  const target = {};
  return new Proxy(target, {
    get: (object, property) => (property in object ? object[property] : () => {}),
    set: (object, property, value) => {
      object[property] = value;
      return true;
    },
  });
}

/** 给元素打上固定的布局尺寸（单元测试用）。 */
export function stubRect(element, { width = 400, height = 220, left = 0, top = 0 } = {}) {
  element.getBoundingClientRect = () => ({
    x: left,
    y: top,
    left,
    top,
    right: left + width,
    bottom: top + height,
    width,
    height,
    toJSON: () => ({}),
  });
  return element;
}

export function canvasElement() {
  const canvas = document.createElement('canvas');
  canvas.getContext = () => fakeContext();
  return stubRect(canvas);
}

/** 等待若干轮事件循环，冲刷未 await 的异步流程。 */
export async function flush(rounds = 4) {
  for (let index = 0; index < rounds; index++) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

/**
 * 生成一个可以放进 FormData 的假文件。
 *
 * ``FormData.append(name, value, filename)`` 要求 value 是 Blob，
 * 因此这里用 Node 的 ``File``（Blob 子类，自带 name/size）。
 */
export function fileStub(name, size = 4096) {
  const bytes = new Uint8Array(size);
  if (typeof File === 'function') return new File([bytes], name, { type: 'text/plain' });
  return Object.assign(new Blob([bytes], { type: 'text/plain' }), { name });
}

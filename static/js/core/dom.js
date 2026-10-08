/** DOM 小工具：统一 `getElementById` 与元素构造，减少样板代码。 */

export const $ = (id) => document.getElementById(id);

export function setText(node, text) {
  if (node) node.textContent = text;
}

export function setHidden(node, hidden) {
  if (node) node.hidden = hidden;
}

export function toggleClass(node, className, enabled) {
  if (node) node.classList.toggle(className, enabled);
}

export function createElement(tag, { className, text, attrs, dataset } = {}) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  if (attrs) Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, value));
  if (dataset) Object.entries(dataset).forEach(([key, value]) => { element.dataset[key] = value; });
  return element;
}

export function clearChildren(node) {
  if (node) node.innerHTML = '';
}

/** 光标读数渲染：输入图使用悬浮读数卡片，结果图使用跟随 tooltip。 */

function buildRow(container, row, { rowClassName, titleClassName, valueClassName, swatchClassName }) {
  const wrapper = document.createElement('div');
  wrapper.className = rowClassName;
  const name = document.createElement('span');
  name.className = titleClassName;
  const swatch = document.createElement('i');
  swatch.className = swatchClassName;
  swatch.style.backgroundColor = row.color;
  const label = document.createElement('span');
  label.textContent = row.label;
  name.append(swatch, label);
  const value = document.createElement('b');
  value.className = valueClassName;
  value.textContent = row.text;
  wrapper.append(name, value);
  container.appendChild(wrapper);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

/** 输入图读数卡片（右下/左下自适应，宽度受限）。 */
export function renderHoverCard({ container, xText, rows, markerX, yFraction, wrap }) {
  container.innerHTML = '';
  const header = document.createElement('div');
  header.className = 'input-chart-hover-frequency';
  header.textContent = xText;
  container.appendChild(header);
  rows.forEach((row) =>
    buildRow(container, row, {
      rowClassName: 'input-chart-hover-row',
      titleClassName: 'input-chart-hover-param',
      valueClassName: 'input-chart-hover-value',
      swatchClassName: 'input-chart-hover-swatch',
    }),
  );
  container.hidden = false;

  const wrapRect = wrap.getBoundingClientRect();
  const width = Math.min(230, Math.max(150, wrapRect.width * 0.5));
  container.style.width = `${width}px`;
  const left = markerX < wrapRect.width / 2 ? markerX + 12 : markerX - width - 12;
  container.style.left = `${clamp(left, 5, Math.max(5, wrapRect.width - width - 5))}px`;
  const height = container.getBoundingClientRect().height || 50 + rows.length * 14;
  const top = yFraction * wrapRect.height + 10;
  container.style.top = `${clamp(top, 5, Math.max(5, wrapRect.height - height - 5))}px`;
}

/** 结果图 tooltip（HTML 行，带颜色）。 */
export function renderTooltip({ container, xText, rows, markerX, yFraction, wrap }) {
  const lines = rows
    .filter((row) => Number.isFinite(row.value))
    .map((row) => `<span style="color:${row.color}">${row.label} ${row.text}</span>`);
  container.innerHTML = `<b>${xText}</b><br>${lines.join('<br>')}`;
  container.style.display = 'block';

  const wrapRect = wrap.getBoundingClientRect();
  const width = container.getBoundingClientRect().width || 180;
  const height = container.getBoundingClientRect().height || 50;
  let left = markerX + 12;
  if (left + width > wrapRect.width - 4) left = markerX - width - 12;
  container.style.left = `${clamp(left, 4, Math.max(4, wrapRect.width - width - 4))}px`;
  container.style.top = `${clamp(yFraction * wrapRect.height - 48, 3, Math.max(3, wrapRect.height - height - 3))}px`;
}

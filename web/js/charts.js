// Hand-made SVG charts: no third-party code ever touches the financial data.
// Rules: one y-axis, thin marks (<=24px), 4px rounded data ends, 2px surface gaps,
// hairline grid, legend for >=2 series, selective direct labels, tooltip on hover/focus.
import { compact, money, esc } from './format.js';

const observers = new WeakMap();

/** Render `build(width)` into `el` now and again whenever the element resizes. */
export function draw(el, build) {
  if (!el) return;
  const render = () => { el.innerHTML = build(Math.max(260, Math.floor(el.clientWidth))); };
  render();
  observers.get(el)?.disconnect();
  let last = el.clientWidth;
  const observer = new ResizeObserver(() => {
    if (Math.abs(el.clientWidth - last) > 4) { last = el.clientWidth; render(); }
  });
  observer.observe(el);
  observers.set(el, observer);
}

export const tipAttr = html => `data-tip="${encodeURIComponent(html)}" tabindex="0"`;
export const tipRow = (color, label, value) => `<div class="tt-row"><span>${color ? `<i class="swatch" style="background:${color}"></i>` : ''}${esc(label)}</span><b>${value}</b></div>`;
export const empty = (text = 'Sem dados para este período.') => `<div class="chart-empty">${esc(text)}</div>`;

function niceTicks(max, count = 4) {
  if (max <= 0) return [0];
  const raw = max / count, power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * power).find(s => s >= raw);
  const ticks = [];
  for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(v);
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

/** Column with 4px rounded top, square at the baseline. */
function column(x, y, w, h, r = 4) {
  if (h <= 0) return '';
  r = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

export function legend(items) {
  return `<div class="legend">${items.map(i => i.tick ? `<span><i class="tick"></i>${esc(i.label)}</span>` : `<span><i class="swatch" style="background:${i.color}"></i>${esc(i.label)}</span>`).join('')}</div>`;
}

/**
 * Grouped or stacked columns over categories (usually months).
 * series: [{label, color, values:[cents|null]}]; null = no data (drawn as a dashed placeholder).
 */
export function columns(width, { labels, series, height = 240, stacked = false, highlight = -1, valueLabels = 'last', tooltipTitle = l => l, extraTip = () => '', onClick = null, format = money }) {
  const pad = { top: 22, right: 8, bottom: 26, left: 46 };
  const plotH = height - pad.top - pad.bottom, plotW = width - pad.left - pad.right;
  const n = labels.length;
  if (!n || !series.some(s => s.values.some(v => v))) return empty();
  const totals = labels.map((_, i) => series.reduce((sum, s) => sum + Math.max(0, s.values[i] || 0), 0));
  const max = stacked ? Math.max(...totals) : Math.max(...series.flatMap(s => s.values.map(v => v || 0)));
  const ticks = niceTicks(max), top = ticks[ticks.length - 1] || 1;
  const y = v => pad.top + plotH - (v / top) * plotH;
  const band = plotW / n;
  const groupW = Math.min(band * 0.72, stacked ? 30 : series.length * 24 + (series.length - 1) * 2);
  const barW = stacked ? groupW : (groupW - (series.length - 1) * 2) / series.length;
  let out = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Gráfico de colunas">`;
  out += ticks.map(t => `<line class="gridline" x1="${pad.left}" x2="${width - pad.right}" y1="${y(t)}" y2="${y(t)}"/><text class="axis" x="${pad.left - 8}" y="${y(t) + 4}" text-anchor="end">${t ? compact(t) : '0'}</text>`).join('');
  labels.forEach((label, i) => {
    const cx = pad.left + band * i + band / 2;
    const x0 = cx - groupW / 2;
    const tipHtml = `<div class="tt-title">${esc(tooltipTitle(label, i))}</div>` + series.map(s => tipRow(s.color, s.label, s.values[i] == null ? 'sem dados' : format(s.values[i]))).join('') + extraTip(i);
    let marks = '';
    if (stacked) {
      let base = 0;
      series.forEach(s => {
        const v = Math.max(0, s.values[i] || 0);
        if (!v) return;
        const y1 = y(base + v), h = y(base) - y1 - (base ? 2 : 0);
        const isTop = series.slice(series.indexOf(s) + 1).every(o => !(o.values[i] > 0));
        marks += isTop ? `<path class="mark" d="${column(x0, y1, groupW, h)}" fill="${s.color}"/>` : `<rect class="mark" x="${x0}" y="${y1}" width="${groupW}" height="${Math.max(0, h)}" fill="${s.color}"/>`;
        base += v;
      });
      if (!totals[i] && series.every(s => s.values[i] == null)) marks += `<rect class="empty-col" x="${x0}" y="${pad.top + plotH - 30}" width="${groupW}" height="30" rx="4"/>`;
    } else {
      series.forEach((s, k) => {
        const v = s.values[i];
        const x = x0 + k * (barW + 2);
        if (v == null) { marks += `<rect class="empty-col" x="${x + 0.5}" y="${pad.top + plotH - 24}" width="${barW - 1}" height="24" rx="4"/>`; return; }
        marks += `<path class="mark" d="${column(x, y(Math.max(v, 0)), barW, y(0) - y(Math.max(v, 0)))}" fill="${s.color}"/>`;
      });
    }
    const showLabel = valueLabels === 'all' || (valueLabels === 'last' && i === n - 1) || (valueLabels === 'highlight' && i === highlight);
    if (showLabel && stacked && totals[i]) marks += `<text class="label strong" x="${cx}" y="${y(totals[i]) - 7}" text-anchor="middle">${compact(totals[i])}</text>`;
    if (showLabel && !stacked) series.forEach((s, k) => { if (s.values[i] > 0) marks += `<text class="label" x="${x0 + k * (barW + 2) + barW / 2}" y="${y(s.values[i]) - 6}" text-anchor="middle">${compact(s.values[i])}</text>`; });
    out += `<g data-group ${onClick ? `data-click="${i}" style="cursor:pointer"` : ''}><rect class="col-bg" x="${pad.left + band * i + 2}" y="${pad.top - 8}" width="${band - 4}" height="${plotH + 8}" rx="8"/>${marks}
      <text class="axis" x="${cx}" y="${height - 8}" text-anchor="middle" ${i === highlight ? 'style="fill:var(--ink);font-weight:650"' : ''}>${esc(label)}</text>
      <rect class="hit" x="${pad.left + band * i}" y="${pad.top - 8}" width="${band}" height="${plotH + 30}" ${tipAttr(tipHtml)}/></g>`;
  });
  out += `<line class="baseline" x1="${pad.left}" x2="${width - pad.right}" y1="${y(0)}" y2="${y(0)}"/>`;
  return out + '</svg>';
}

/** Single-series line with a 10% area wash, end dot and optional average reference. */
export function line(width, { values, labels, color = 'var(--bar)', height = 90, average = null, title = '', format = money, showAxis = false }) {
  const pad = { top: 12, right: 10, bottom: showAxis ? 20 : 8, left: 4 };
  const points = values.map((v, i) => [i, v]).filter(([, v]) => v != null);
  if (points.length === 0) return empty('Sem dados');
  const max = Math.max(1, ...points.map(([, v]) => v), average || 0) * 1.1;
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
  const x = i => pad.left + (values.length === 1 ? plotW / 2 : (i / (values.length - 1)) * plotW);
  const y = v => pad.top + plotH - (Math.max(v, 0) / max) * plotH;
  const d = points.map(([i, v], k) => `${k ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const area = `${d}L${x(points[points.length - 1][0])},${y(0)}L${x(points[0][0])},${y(0)}Z`;
  const [li, lv] = points[points.length - 1];
  let out = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(title)}">`;
  out += `<line class="baseline" x1="${pad.left}" x2="${width - pad.right}" y1="${y(0)}" y2="${y(0)}"/>`;
  if (average) out += `<line x1="${pad.left}" x2="${width - pad.right}" y1="${y(average)}" y2="${y(average)}" stroke="var(--muted)" stroke-width="1" opacity=".6"/>`;
  out += `<path d="${area}" fill="${color}" opacity=".1"/><path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  out += `<circle cx="${x(li)}" cy="${y(lv)}" r="4.5" fill="${color}" stroke="var(--surface)" stroke-width="2"/>`;
  const band = plotW / Math.max(1, values.length - 1);
  values.forEach((v, i) => {
    out += `<rect class="hit" x="${x(i) - band / 2}" y="0" width="${band}" height="${height}" ${tipAttr(`<div class="tt-title">${esc(labels?.[i] || '')}</div>${tipRow(color, title, v == null ? 'sem dados' : format(v))}`)}/>`;
    if (showAxis && labels) out += `<text class="axis" x="${x(i)}" y="${height - 4}" text-anchor="${i === 0 ? 'start' : i === values.length - 1 ? 'end' : 'middle'}">${esc(labels[i])}</text>`;
  });
  return out + '</svg>';
}

/** Tiny trend for stat tiles: de-emphasized history, accent on the current point. */
export function sparkline(width, values, { height = 34, color = 'currentColor' } = {}) {
  const pts = values.map((v, i) => [i, v]).filter(([, v]) => v != null);
  if (pts.length < 2) return '';
  const max = Math.max(...pts.map(p => p[1])), min = Math.min(0, ...pts.map(p => p[1]));
  const x = i => 3 + (i / (values.length - 1)) * (width - 6);
  const y = v => 4 + (height - 8) * (1 - (v - min) / ((max - min) || 1));
  const d = pts.map(([i, v], k) => `${k ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const [li, lv] = pts[pts.length - 1];
  return `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><path d="${d}" fill="none" stroke="${color}" stroke-width="2" opacity=".55" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${x(li)}" cy="${y(lv)}" r="4" fill="${color}"/></svg>`;
}

/** 100% composition strip with a 2px gap between segments. */
export function strip(width, parts, { height = 14 } = {}) {
  const total = parts.reduce((s, p) => s + Math.max(0, p.value), 0);
  if (!total) return '';
  const gaps = (parts.filter(p => p.value > 0).length - 1) * 2;
  let x = 0, out = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Composição">`;
  parts.filter(p => p.value > 0).forEach((p, i, list) => {
    const w = (p.value / total) * (width - gaps);
    const r = i === 0 || i === list.length - 1 ? 4 : 0;
    out += `<rect x="${x}" y="0" width="${Math.max(1, w)}" height="${height}" rx="${r}" fill="${p.color}" ${tipAttr(tipRow(p.color, p.label, `${money(p.value)} · ${(p.value / total * 100).toFixed(0)}%`))}/>`;
    if (r && list.length > 1) out += `<rect x="${i === 0 ? x + Math.max(1, w) - 4 : x}" y="0" width="${Math.min(4, w)}" height="${height}" fill="${p.color}" pointer-events="none"/>`;
    x += w + 2;
  });
  return out + '</svg>';
}

/** Calendar heatmap of daily spending (sequential, one hue). */
export function calendar(width, days, { maxWeeks = 26 } = {}) {
  if (!days.length) return empty();
  const weeks = Math.max(8, Math.min(maxWeeks, Math.floor((width - 22) / 19)));
  const map = new Map(days.map(d => [d.date, d.cents]));
  const last = new Date(days[days.length - 1].date + 'T12:00');
  const end = new Date(last); end.setDate(end.getDate() + (6 - ((end.getDay() + 6) % 7)));
  const gap = 3, cell = Math.min(22, Math.floor((width - 22) / weeks) - gap);
  const start = new Date(end); start.setDate(start.getDate() - weeks * 7 + 1);
  const values = days.map(d => d.cents).sort((a, b) => a - b);
  const q = p => values[Math.min(values.length - 1, Math.floor(p * values.length))];
  const steps = [q(.25), q(.5), q(.75), q(.92)];
  const ramp = ['var(--surface-2)', 'color-mix(in srgb, var(--bar) 22%, var(--surface))', 'color-mix(in srgb, var(--bar) 45%, var(--surface))', 'color-mix(in srgb, var(--bar) 70%, var(--surface))', 'var(--bar)'];
  const level = v => !v ? 0 : 1 + steps.filter(s => v > s).length;
  const h = 7 * (cell + gap) + 18;
  let out = `<svg viewBox="0 0 ${width} ${h}" role="img" aria-label="Gastos por dia">`;
  ['S', 'T', 'Q', 'Q', 'S', 'S', 'D'].forEach((d, i) => { if (i % 2 === 0) out += `<text class="axis" x="0" y="${i * (cell + gap) + cell - 2}">${d}</text>`; });
  const cur = new Date(start);
  for (let w = 0; w < weeks; w++) {
    for (let d = 0; d < 7; d++) {
      const iso = new Date(cur - cur.getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
      const v = map.get(iso) || 0;
      if (cur <= end) out += `<rect x="${22 + w * (cell + gap)}" y="${d * (cell + gap)}" width="${cell}" height="${cell}" rx="3" fill="${ramp[Math.min(4, level(v))]}" ${tipAttr(`<div class="tt-title">${iso.split('-').reverse().join('/')}</div>${v ? money(v) : 'Sem compras'}`)}/>`;
      if (d === 0 && cur.getDate() <= 7) out += `<text class="axis" x="${22 + w * (cell + gap)}" y="${h - 3}">${['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'][cur.getMonth()]}</text>`;
      cur.setDate(cur.getDate() + 1);
    }
  }
  return out + '</svg>';
}

/**
 * Sankey flow: sources -> center -> groups -> leaves, one shared scale.
 * sources: [{label, value, color}]; center: {label}; groups: [{label, value, color, children:[{label, value, href}]}]
 * Every band is the value it carries; percentages are of the center total.
 */
export function sankey(width, { sources = [], center, groups }, { rowHeight = 31, minHeight = 340 } = {}) {
  width = Math.max(width, 680);  // Below this the flows get unreadable; the card scrolls instead.
  const total = groups.reduce((s, g) => s + g.value, 0);
  if (total <= 0) return empty('Sem gastos neste mês.');
  const nodeW = 10, top = 26, bottom = 8;
  const leftLabel = sources.length ? 130 : 0, rightLabel = 180;
  const leaves = groups.flatMap(g => g.children.map(c => ({ ...c, group: g })));
  const height = Math.max(minHeight, leaves.length * rowHeight + top + bottom + groups.length * 6);
  const pad = { src: 14, grp: 30, leaf: 8 };
  const avail = n => height - top - bottom - n;
  const leafTotal = leaves.reduce((s, l) => s + l.value, 0);
  const scale = Math.min(
    sources.length ? avail(pad.src * (sources.length - 1)) / total : Infinity,
    avail(pad.grp * (groups.length - 1)) / total,
    leafTotal ? avail(pad.leaf * (leaves.length - 1)) / leafTotal : Infinity);
  const h = v => Math.max(2, v * scale);
  const x0 = leftLabel, x3 = width - rightLabel - nodeW;
  const xc = sources.length ? x0 + (x3 - x0) * 0.3 : x0;
  const x2 = sources.length ? x0 + (x3 - x0) * 0.63 : x0 + (x3 - x0) * 0.5;
  const pctOf = v => `${(v / total * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`;
  const stack = (items, gap) => {
    const size = items.reduce((s, i) => s + h(i.value), 0) + gap * (items.length - 1);
    let y = top + (height - top - bottom - size) / 2;
    items.forEach(i => { i.y = y; i.h = h(i.value); y += i.h + gap; });
  };
  const centerNode = { value: total };
  stack([centerNode], 0);
  stack(sources, pad.src);
  stack(groups, pad.grp);
  stack(leaves, pad.leaf);

  const band = (xa, ya, yb, xb, yc, yd) => {
    const m = (xa + xb) / 2;
    return `M${xa},${ya}C${m},${ya} ${m},${yc} ${xb},${yc}L${xb},${yd}C${m},${yd} ${m},${yb} ${xa},${yb}Z`;
  };
  let links = '', nodes = '', labels = '';
  const tip = (title, value, extra = '') => tipAttr(`<div class="tt-title">${esc(title)}</div>${tipRow('', 'Valor', money(value))}${tipRow('', 'Do total', pctOf(value))}${extra}`);

  // sources -> center
  let inY = centerNode.y;
  sources.forEach(s => {
    const k = s.h / sources.reduce((a, b) => a + b.h, 0) * centerNode.h;
    links += `<path class="flow" d="${band(x0 + nodeW, s.y, s.y + s.h, xc, inY, inY + k)}" fill="${s.color}" ${tip(`${s.label} → ${center.label}`, s.value)}/>`;
    inY += k;
    nodes += `<rect x="${x0}" y="${s.y}" width="${nodeW}" height="${s.h}" rx="2" fill="${s.color}" ${tip(s.label, s.value)}/>`;
  });
  // center -> groups
  let outY = centerNode.y;
  groups.forEach(g => {
    const k = g.value / total * centerNode.h;
    links += `<path class="flow" d="${band(xc + nodeW, outY, outY + k, x2, g.y, g.y + g.h)}" fill="${g.color}" ${tip(`${center.label} → ${g.label}`, g.value)}/>`;
    outY += k;
    nodes += `<rect x="${x2}" y="${g.y}" width="${nodeW}" height="${g.h}" rx="2" fill="${g.color}" ${tip(g.label, g.value)}/>`;
    labels += `<text class="label strong" x="${x2}" y="${g.y - 8}">${esc(g.label)} <tspan class="sk-value">${compact(g.value)} · ${pctOf(g.value)}</tspan></text>`;
    // group -> leaves
    let gy = g.y;
    const childTotal = g.children.reduce((s, c) => s + c.value, 0) || 1;
    g.children.forEach(c => {
      const leaf = leaves.find(l => l.label === c.label && l.group === g);
      const k2 = c.value / childTotal * g.h;
      links += `<path class="flow" d="${band(x2 + nodeW, gy, gy + k2, x3, leaf.y, leaf.y + leaf.h)}" fill="${g.color}" ${tip(c.label, c.value, tipRow('', 'Grupo', esc(g.label)))}/>`;
      gy += k2;
    });
  });
  nodes += `<rect x="${xc}" y="${centerNode.y}" width="${nodeW}" height="${centerNode.h}" rx="2" fill="var(--ink)" opacity=".8" ${tip(center.label, total)}/>`;
  labels += `<text class="label strong" x="${xc + nodeW / 2}" y="${centerNode.y - 8}" text-anchor="${sources.length ? 'middle' : 'start'}">${esc(center.label)} <tspan class="sk-value">${compact(total)}</tspan></text>`;

  // Leaf labels: centered on the node, nudged apart so they never collide.
  const placeLabels = (items, min = 15) => {
    const ys = items.map(i => i.y + i.h / 2);
    for (let i = 1; i < ys.length; i++) ys[i] = Math.max(ys[i], ys[i - 1] + min);
    const overflow = ys[ys.length - 1] - (height - 6);
    if (overflow > 0) for (let i = ys.length - 1; i >= 0; i--) ys[i] = Math.min(ys[i] - overflow, i < ys.length - 1 ? ys[i + 1] - min : Infinity);
    return ys;
  };
  const leafYs = placeLabels(leaves);
  leaves.forEach((l, i) => {
    nodes += `<rect x="${x3}" y="${l.y}" width="${nodeW}" height="${l.h}" rx="2" fill="${l.group.color}" ${l.href ? `data-href="${esc(l.href)}" style="cursor:pointer"` : ''} ${tip(l.label, l.value, tipRow('', 'Grupo', esc(l.group.label)))}/>`;
    labels += `<text class="label strong" x="${x3 + nodeW + 8}" y="${leafYs[i] + 4}" ${l.href ? `data-href="${esc(l.href)}" style="cursor:pointer"` : ''}>${esc(l.label)} <tspan class="sk-value">${compact(l.value)}</tspan></text>`;
  });
  const srcYs = placeLabels(sources, 30);
  sources.forEach((s, i) => {
    labels += `<text class="label strong" x="${x0 - 8}" y="${srcYs[i] - 1}" text-anchor="end">${esc(s.label)}</text><text class="label sk-value" x="${x0 - 8}" y="${srcYs[i] + 13}" text-anchor="end">${money(s.value)}</text>`;
  });
  return `<svg class="sankey" viewBox="0 0 ${width} ${height}" role="img" aria-label="Fluxo da renda para as categorias de gasto">${links}${nodes}${labels}</svg>`;
}

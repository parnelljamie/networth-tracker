/* Hand-drawn SVG charts for the mockup: time series (stacked or lines), donut, sparkline.
   Marks follow docs/05-ui.md: 2px lines, ~10-16% area washes, hairline solid grid, one y-axis,
   crosshair tooltip on hover and arrow keys, dashed strokes only for the future. */
(function () {
  'use strict';

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function niceStep(range, count) {
    const raw = range / Math.max(count, 1);
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    const m = raw / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
  }
  function ticks(min, max, count) {
    if (max - min < 1e-9) { max = min + 1; }
    const step = niceStep(max - min, count);
    const lo = Math.floor(min / step) * step;
    const hi = Math.ceil(max / step) * step;
    const out = [];
    for (let v = lo; v <= hi + step * 1e-6; v += step) out.push(Math.round(v / step) * step);
    return out;
  }

  function timeChart(el, o) {
    const n = o.dates.length;
    let lastW = 0, idx = null;

    function draw() {
      const W = Math.max(Math.floor(el.clientWidth), 280);
      if (W === lastW && el.firstChild) return;
      lastW = W;
      const H = o.height || 260;
      const markers = (o.markers || []).slice().sort((a, b) => a.index - b.index);
      const pad = { l: 58, r: 12, t: 10 + (markers.length ? 34 : 0), b: 26 };
      const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
      const x = (i) => pad.l + (n <= 1 ? 0 : (i / (n - 1)) * iw);

      const pos = new Array(n).fill(0), neg = new Array(n).fill(0);
      const bands = o.series.map((s) => {
        const lower = [], upper = [], edge = [];
        for (let i = 0; i < n; i++) {
          const v = s.values[i] || 0;
          if (o.stacked) {
            if (v < 0) { upper.push(neg[i]); neg[i] += v; lower.push(neg[i]); edge.push(neg[i]); }
            else { lower.push(pos[i]); pos[i] += v; upper.push(pos[i]); edge.push(pos[i]); }
          } else { upper.push(v); edge.push(v); }
        }
        return { s, lower, upper, edge };
      });

      let lo = Infinity, hi = -Infinity;
      const see = (v) => { if (v < lo) lo = v; if (v > hi) hi = v; };
      bands.forEach((b) => { b.upper.forEach(see); if (o.stacked) b.lower.forEach(see); });
      if (o.total) o.total.values.forEach(see);
      if (o.zero !== false) { see(0); }
      else { const padV = (hi - lo) * 0.08 || 1; lo -= padV; hi += padV; }
      const tk = ticks(lo, hi, o.tickCount || 4);
      const y0 = tk[0], y1 = tk[tk.length - 1];
      const y = (v) => pad.t + (1 - (v - y0) / (y1 - y0 || 1)) * ih;

      const path = (arr, from, to) => {
        let p = '';
        for (let i = from; i <= to; i++) p += (i === from ? 'M' : 'L') + x(i).toFixed(1) + ',' + y(arr[i]).toFixed(1);
        return p;
      };
      const area = (up, low) => {
        let p = path(up, 0, n - 1);
        for (let i = n - 1; i >= 0; i--) p += 'L' + x(i).toFixed(1) + ',' + y(low[i]).toFixed(1);
        return p + 'Z';
      };
      const k = o.dashFrom == null ? null : Math.max(0, Math.min(n - 1, o.dashFrom));
      const stroke = (arr, color) => {
        const st = `fill:none;stroke:${color};stroke-width:2;stroke-linejoin:round;stroke-linecap:round`;
        if (k === null || k >= n - 1) return `<path d="${path(arr, 0, n - 1)}" style="${st}"/>`;
        return (k > 0 ? `<path d="${path(arr, 0, k)}" style="${st}"/>` : '') + `<path d="${path(arr, k, n - 1)}" style="${st};stroke-dasharray:5 5"/>`;
      };

      let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(o.label || 'Chart')}">`;
      tk.forEach((v) => {
        const yy = y(v).toFixed(1);
        svg += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${yy}" y2="${yy}" style="stroke:var(${v === 0 && y0 < 0 ? '--axis' : '--rule'});stroke-width:1"/>`;
        svg += `<text x="${pad.l - 8}" y="${(+yy + 4).toFixed(1)}" text-anchor="end" class="tick">${esc(o.fmtY(v))}</text>`;
      });
      const xCount = Math.min(o.xTicks || (W < 520 ? 3 : 6), n);
      for (let t = 0; t < xCount; t++) {
        const i = Math.round((t * (n - 1)) / (xCount - 1 || 1));
        const anchor = t === 0 ? 'start' : t === xCount - 1 ? 'end' : 'middle';
        svg += `<text x="${x(i).toFixed(1)}" y="${H - 7}" text-anchor="${anchor}" class="tick">${esc(o.fmtX(o.dates[i]))}</text>`;
      }
      if (o.todayIndex != null) {
        const tx = x(o.todayIndex).toFixed(1);
        svg += `<line x1="${tx}" x2="${tx}" y1="${pad.t}" y2="${H - pad.b}" style="stroke:var(--axis);stroke-width:1"/>`;
      }
      bands.forEach((b) => {
        const c = b.s.color;
        if (o.stacked) svg += `<path d="${area(b.upper, b.lower)}" style="fill:${c};fill-opacity:${o.fillOpacity || 0.16};stroke:none"/>`;
        else if (o.wash) svg += `<path d="${area(b.upper, new Array(n).fill(y0))}" style="fill:${c};fill-opacity:0.08;stroke:none"/>`;
      });
      bands.forEach((b) => (svg += stroke(b.edge, b.s.color)));
      if (o.total) svg += stroke(o.total.values, 'var(--ink)');
      markers.forEach((m, j) => {
        const mx = x(m.index);
        svg += `<line x1="${mx.toFixed(1)}" x2="${mx.toFixed(1)}" y1="${(j % 2 ? 26 : 12) + 4}" y2="${H - pad.b}" style="stroke:var(--muted);stroke-width:1;stroke-opacity:.6"/>`;
        const anchor = mx > W - 110 ? 'end' : mx < pad.l + 70 ? 'start' : 'middle';
        svg += `<text x="${mx.toFixed(1)}" y="${j % 2 ? 26 : 12}" text-anchor="${anchor}" class="marker-label">${esc(m.label)}</text>`;
      });
      svg += `<g class="hover"></g></svg>`;

      let legend = '';
      const items = o.series.map((s) => ({ label: s.label, color: s.color }));
      if (o.total) items.push({ label: o.total.label, color: 'var(--ink)', line: true });
      if (items.length >= 2) {
        legend = `<div class="legend">${items.map((it) => `<span class="legend-item"><span class="${it.line ? 'key-line' : 'swatch'}" style="background:${it.color}"></span>${esc(it.label)}</span>`).join('')}</div>`;
      }
      el.innerHTML = `${legend}<div class="chart-plot" tabindex="0" aria-label="${esc(o.label || 'Chart')}. Use arrow keys to read values.">${svg}<div class="chart-tip" hidden></div></div>`;

      const plot = el.querySelector('.chart-plot');
      const tip = el.querySelector('.chart-tip');
      const g = el.querySelector('.hover');
      const show = (i) => {
        idx = i;
        const cx = x(i).toFixed(1);
        let h = `<line x1="${cx}" x2="${cx}" y1="${pad.t}" y2="${H - pad.b}" style="stroke:var(--ink-2);stroke-width:1"/>`;
        bands.forEach((b) => (h += `<circle cx="${cx}" cy="${y(b.edge[i]).toFixed(1)}" r="4" style="fill:${b.s.color};stroke:var(--surface);stroke-width:2"/>`));
        if (o.total) h += `<circle cx="${cx}" cy="${y(o.total.values[i]).toFixed(1)}" r="4" style="fill:var(--ink);stroke:var(--surface);stroke-width:2"/>`;
        g.innerHTML = h;
        const rows = o.series
          .map((s) => `<div class="tip-row"><span class="swatch" style="background:${s.color}"></span><span>${esc(s.label)}</span><b>${o.fmtTip(s.values[i])}</b></div>`)
          .join('');
        const totalRow = o.total ? `<div class="tip-row tip-total"><span class="key-line" style="background:var(--ink)"></span><span>${esc(o.total.label)}</span><b>${o.fmtTip(o.total.values[i])}</b></div>` : '';
        tip.innerHTML = `<div class="tip-date">${esc(o.fmtTipDate(o.dates[i]))}</div>${rows}${totalRow}`;
        tip.hidden = false;
        const scale = plot.clientWidth / W;
        const tw = tip.offsetWidth;
        let left = x(i) * scale + 14;
        if (left + tw > plot.clientWidth) left = x(i) * scale - tw - 14;
        tip.style.left = Math.max(0, left) + 'px';
        tip.style.top = pad.t + 'px';
      };
      const hide = () => { g.innerHTML = ''; tip.hidden = true; };
      plot.addEventListener('pointermove', (e) => {
        const r = plot.getBoundingClientRect();
        const px = ((e.clientX - r.left) * W) / r.width;
        const i = Math.round(((px - pad.l) / iw) * (n - 1));
        show(Math.max(0, Math.min(n - 1, i)));
      });
      plot.addEventListener('pointerleave', hide);
      plot.addEventListener('focus', () => show(idx == null ? n - 1 : idx));
      plot.addEventListener('blur', hide);
      plot.addEventListener('keydown', (e) => {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
        e.preventDefault();
        const i = (idx == null ? n - 1 : idx) + (e.key === 'ArrowRight' ? 1 : -1);
        show(Math.max(0, Math.min(n - 1, i)));
      });
    }

    draw();
    if (el._ro) el._ro.disconnect();
    el._ro = new ResizeObserver(() => draw());
    el._ro.observe(el);
  }

  function donut(el, segs, o = {}) {
    const size = o.size || 176, th = o.thickness || 22;
    const r = size / 2 - 2, ri = r - th, c = size / 2;
    const total = segs.reduce((s, g) => s + g.value, 0) || 1;
    const pt = (rad, a) => `${(c + rad * Math.cos(a)).toFixed(2)},${(c + rad * Math.sin(a)).toFixed(2)}`;
    let a0 = -Math.PI / 2, paths = '';
    segs.forEach((g, k) => {
      const frac = Math.min(g.value / total, 0.9999);
      const a1 = a0 + frac * Math.PI * 2;
      const large = a1 - a0 > Math.PI ? 1 : 0;
      paths += `<path data-k="${k}" tabindex="0" d="M${pt(r, a0)}A${r},${r} 0 ${large} 1 ${pt(r, a1)}L${pt(ri, a1)}A${ri},${ri} 0 ${large} 0 ${pt(ri, a0)}Z" style="fill:${g.color};stroke:var(--surface);stroke-width:2"><title>${esc(g.label)}</title></path>`;
      a0 = a1;
    });
    el.innerHTML = `<div class="donut" style="width:${size}px;height:${size}px"><svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="${esc(o.label || 'Allocation')}">${paths}</svg><div class="donut-center"><span class="donut-k">${o.centerLabel}</span><span class="donut-v">${o.centerValue}</span></div></div>`;
    const k = el.querySelector('.donut-k'), v = el.querySelector('.donut-v');
    const reset = () => { k.innerHTML = o.centerLabel; v.innerHTML = o.centerValue; };
    el.querySelectorAll('path').forEach((p) => {
      const on = () => { const g = segs[+p.dataset.k]; k.textContent = g.label; v.innerHTML = o.fmt(g.value, g.value / total); };
      p.addEventListener('pointerenter', on); p.addEventListener('focus', on);
      p.addEventListener('pointerleave', reset); p.addEventListener('blur', reset);
    });
  }

  function sparkline(values, o = {}) {
    const w = o.w || 120, h = o.h || 34, n = values.length;
    const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
    const x = (i) => 3 + (i * (w - 8)) / (n - 1 || 1);
    const y = (v) => 4 + (1 - (v - min) / span) * (h - 9);
    const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    const color = o.color || 'var(--ink-2)';
    const k = o.dashFrom == null ? n - 1 : o.dashFrom;
    const solid = 'M' + pts.slice(0, k + 1).join('L');
    const dashed = k < n - 1 ? 'M' + pts.slice(k).join('L') : '';
    const fill = `${solid}L${x(k).toFixed(1)},${h}L${x(0).toFixed(1)},${h}Z`;
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">` +
      `<path d="${fill}" style="fill:${color};fill-opacity:.1;stroke:none"/>` +
      `<path d="${solid}" style="fill:none;stroke:${color};stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round"/>` +
      (dashed ? `<path d="${dashed}" style="fill:none;stroke:${color};stroke-width:1.5;stroke-dasharray:3 3"/>` : '') +
      `<circle cx="${x(k).toFixed(1)}" cy="${y(values[k]).toFixed(1)}" r="3" style="fill:var(--accent);stroke:var(--surface);stroke-width:1.5"/></svg>`;
  }

  window.Charts = { timeChart, donut, sparkline, ticks };
})();

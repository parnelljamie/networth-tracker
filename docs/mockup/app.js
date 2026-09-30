/* Waymark mockup: shell, formatting, router, shared helpers and the Overview page. */
(function () {
  'use strict';
  const N = window.NW, C = window.Charts;
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const store = {
    get(k, dflt) { try { const v = localStorage.getItem('waymark:' + k); return v == null ? dflt : JSON.parse(v); } catch (e) { return dflt; } },
    set(k, v) { try { localStorage.setItem('waymark:' + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
  };

  const state = {
    privacy: store.get('privacy', false),
    range: '1Y', heroView: 'total', alloc: 'category',
    tabs: {},
    proj: { scope: 'household', years: 30, scenario: 'base', real: false, view: 'category' },
    pending: true,
    priceMinutes: 3,
  };

  /* ---------- formatting (the only place numbers become text) ---------- */
  const MASK = '£•••••';
  const fmt = {
    gbp(v, o = {}) {
      if (state.privacy) return `<span class="money">${MASK}</span>`;
      const abs = Math.abs(v);
      let s;
      if (o.compact) s = abs >= 1e6 ? (abs / 1e6).toFixed(2) + 'm' : abs >= 1e4 ? Math.round(abs / 1e3) + 'k' : abs >= 1e3 ? (abs / 1e3).toFixed(1) + 'k' : Math.round(abs).toString();
      else s = abs.toLocaleString('en-GB', { minimumFractionDigits: o.dp || 0, maximumFractionDigits: o.dp || 0 });
      const sign = v <= -0.005 ? '−' : o.sign && v >= 0.005 ? '+' : '';
      return `<span class="money">${sign}£${s}</span>`;
    },
    axis(v) {
      if (state.privacy) return '£•••';
      const abs = Math.abs(v), sign = v < 0 ? '−' : '';
      return sign + '£' + (abs >= 1e6 ? (abs / 1e6).toFixed(abs % 1e6 ? 1 : 0) + 'm' : abs >= 1e3 ? Math.round(abs / 1e3) + 'k' : Math.round(abs));
    },
    hero(v) {
      if (state.privacy) return MASK;
      const cents = Math.round(Math.abs(v) * 100);
      const pounds = Math.floor(cents / 100).toLocaleString('en-GB');
      return `${v < 0 ? '−' : ''}£${pounds}<span class="pence">.${String(cents % 100).padStart(2, '0')}</span>`;
    },
    pct(v, dp = 1) { return state.privacy ? '••%' : (v * 100).toFixed(dp) + '%'; },
    delta(v, pct) {
      const cls = v >= 0.5 ? 'up' : v <= -0.5 ? 'down' : 'flat';
      const arrow = cls === 'up' ? '▲' : cls === 'down' ? '▼' : '–';
      const p = pct == null || !isFinite(pct) ? '' : ` (${fmt.pct(Math.abs(pct), 2)})`;
      return `<span class="delta ${cls}"><span aria-hidden="true">${arrow}</span>${fmt.gbp(Math.abs(v))}${p}</span>`;
    },
    units(u) { return state.privacy ? '•••' : u.toLocaleString('en-GB', { maximumFractionDigits: 4 }); },
    price(p) { return state.privacy ? '£•••' : '£' + p.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: p < 10 ? 4 : 2 }); },
    date(dt) { return dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }); },
    dayMonth(dt) { return dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }); },
    monYY(dt) { return dt.toLocaleDateString('en-GB', { month: 'short', year: '2-digit', timeZone: 'UTC' }).replace(' ', " '"); },
    monthYear(dt) { return dt.toLocaleDateString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' }); },
    duration(from, to) {
      const m = N.monthsBetween(from, to);
      const y = Math.floor(m / 12), r = m % 12;
      return [y ? `${y} yr` : '', r ? `${r} mo` : ''].filter(Boolean).join(' ') || 'under a month';
    },
  };

  /* ---------- icons ---------- */
  const svg = (p, s = 18) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
  const ICON = {
    overview: svg('<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>'),
    person: svg('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
    home: svg('<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>'),
    gem: svg('<path d="M6 3h12l3 6-9 12L3 9z"/><path d="M3 9h18M9 3l3 18 3-18"/>'),
    chart: svg('<path d="M3 20h18"/><path d="M5 16l4-5 4 3 6-8"/>'),
    import: svg('<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 21h16"/>'),
    settings: svg('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'),
    ok: svg('<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>', 13),
    warn: svg('<path d="M12 3l10 18H2z"/><path d="M12 10v4M12 17.5v.5"/>', 13),
    car: svg('<path d="M5 16l1.5-5a2 2 0 0 1 2-1.5h7a2 2 0 0 1 2 1.5L19 16"/><rect x="3" y="16" width="18" height="4" rx="1"/><circle cx="7.5" cy="20" r="1"/><circle cx="16.5" cy="20" r="1"/>'),
    watch: svg('<circle cx="12" cy="12" r="6"/><path d="M12 9v3l2 1.5"/><path d="M9 6l1-3h4l1 3M9 18l1 3h4l1-3"/>'),
    card: svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h4"/>'),
    loan: svg('<path d="M4 20V8l8-5 8 5v12"/><path d="M9 20v-5h6v5"/><path d="M12 8.5v.5"/>'),
    plus: svg('<path d="M12 5v14M5 12h14"/>', 16),
    arrow: svg('<path d="M5 12h14M13 6l6 6-6 6"/>', 16),
  };

  /* ---------- shared helpers ---------- */
  const personName = (id) => (N.personById[id] ? N.personById[id].name : 'Joint');
  const helpers = {
    owners(a) {
      const ids = Object.keys(a.owners);
      const label = ids.map((id) => `${personName(id)}${a.owners[id] < 1 ? ' ' + Math.round(a.owners[id] * 100) + '%' : ''}`).join(', ');
      return `<span class="owners" title="${esc(label)}" aria-label="Owned by ${esc(label)}">${ids.map((id) => `<span class="avatar">${N.personById[id].initial}</span>`).join('')}</span>`;
    },
    status(v) {
      if (!v.updated) return `<span class="status ok">${ICON.ok}Live price</span>`;
      if (v.staleness === 'ok') return `<span class="status ok">${ICON.ok}${v.age <= 1 ? 'Today' : v.age + ' days ago'}</span>`;
      return `<span class="status ${v.staleness}">${ICON.warn}${v.age} days old</span>`;
    },
    seg(name, options, current, label) {
      return `<div class="seg" role="group" aria-label="${esc(label || name)}">${options
        .map(([value, text]) => `<button type="button" data-action="seg" data-name="${name}" data-value="${value}" aria-pressed="${String(value) === String(current)}">${text}</button>`)
        .join('')}</div>`;
    },
    tabs(key, list, current) {
      return `<div class="tabs" role="tablist">${list
        .map(([value, text]) => `<button type="button" role="tab" data-action="tab" data-key="${key}" data-value="${value}" aria-selected="${value === current}">${text}</button>`)
        .join('')}</div>`;
    },
    hrefFor(a) {
      if (a.cat === 'property' || a.id === 'mortgage') return '#/property';
      if (['other_asset', 'loan', 'credit_card'].includes(a.cat)) return '#/other';
      return '#/accounts/' + a.id;
    },
    wrapper(a) { return a.wrapper || { cash: 'Cash', property: 'Property', mortgage: 'Mortgage', loan: 'Loan', credit_card: 'Card', other_asset: 'Asset' }[a.cat]; },
    tab(key, dflt) { return state.tabs[key] || dflt; },
    projection(adj = 0, months = 420, real = false) {
      const k = `${adj}|${months}|${real}|${N.accounts.map((a) => a.balance || a.anchor || 0).join(',')}`;
      if (!helpers._proj || helpers._projKey !== k) { helpers._proj = N.project({ months, adj, real }); helpers._projKey = k; }
      return helpers._proj;
    },
    personName,
  };

  /* ---------- router ---------- */
  const routes = [];
  const actions = {};
  const route = (re, fn) => routes.push({ re, fn });
  const go = (hash) => { if (location.hash === hash) refresh(); else location.hash = hash; };
  let current = null;

  function refresh(keepScroll = true) {
    const y = window.scrollY;
    const path = location.hash.replace(/^#/, '') || '/overview';
    const r = routes.find((x) => x.re.test(path)) || routes[0];
    const view = r.fn(...(path.match(r.re) || []).slice(1));
    $('#page-title').textContent = view.title;
    document.title = `${view.title} · Waymark`;
    $('#page').innerHTML = view.html;
    renderNav(path);
    if (view.mount) view.mount();
    if (keepScroll && current === path) window.scrollTo(0, y);
    else window.scrollTo(0, 0);
    current = path;
  }

  function renderNav(path) {
    const hh = N.totals('household');
    const item = (href, icon, label, extra = '') =>
      `<a href="#${href}"${path === href || path.startsWith(href + '/') ? ' aria-current="page"' : ''}>${ICON[icon]}<span>${label}</span>${extra}</a>`;
    $('#nav').innerHTML =
      item('/overview', 'overview', 'Overview') +
      `<div class="nav-label eyebrow">People</div>` +
      N.people.map((p) => item('/people/' + p.id, 'person', p.name, `<span class="nav-value">${fmt.gbp(N.totals(p.id).total, { compact: true })}</span>`)).join('') +
      `<div class="nav-label eyebrow">Shared</div>` +
      item('/property', 'home', 'Property &amp; mortgage') + item('/other', 'gem', 'Other assets') + item('/projections', 'chart', 'Projections') +
      `<div class="nav-label eyebrow">Data</div>` +
      item('/import', 'import', 'Import history') + item('/settings', 'settings', 'Settings');
    $('#rail-total').innerHTML = fmt.hero(hh.total);
    $('#rail-day').innerHTML = `Today ${fmt.delta(hh.day)}`;
    $('#privacy-btn').setAttribute('aria-pressed', String(state.privacy));
    $('#price-text').textContent = state.priceMinutes === 0 ? 'Prices live · just now' : `Prices live · ${state.priceMinutes} min ago`;
    $('#pending-badge').hidden = !state.pending;
  }

  /* ---------- overlays & toasts ---------- */
  function toast(msg) {
    const t = document.createElement('div');
    t.className = 'toast';
    t.textContent = msg;
    $('#toasts').appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }
  function openOverlay(id, html) {
    closeOverlays();
    const el = $('#' + id);
    el.innerHTML = html;
    el.hidden = false;
    $('#scrim').hidden = false;
    const focusable = el.querySelector('input, button, select');
    if (focusable) focusable.focus();
  }
  function closeOverlays() {
    ['sheet', 'dialog', 'palette'].forEach((id) => { $('#' + id).hidden = true; });
    $('#scrim').hidden = true;
    $('#pending-pop').hidden = true;
    $('#rail').classList.remove('open');
  }

  /* ---------- global actions ---------- */
  Object.assign(actions, {
    seg(el) {
      const [scope, key] = el.dataset.name.split('.');
      const value = el.dataset.value;
      const parsed = value === 'true' ? true : value === 'false' ? false : isNaN(+value) ? value : +value;
      if (key) state[scope][key] = parsed; else state[scope] = parsed;
      refresh();
    },
    tab(el) { state.tabs[el.dataset.key] = el.dataset.value; refresh(); },
    'toggle-privacy'() { state.privacy = !state.privacy; store.set('privacy', state.privacy); refresh(); toast(state.privacy ? 'Figures hidden' : 'Figures shown'); },
    'toggle-theme'() {
      const root = document.documentElement;
      const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
      root.dataset.theme = dark ? 'light' : 'dark';
      store.set('theme', root.dataset.theme);
    },
    'open-rail'() { $('#rail').classList.add('open'); $('#scrim').hidden = false; },
    'close-rail'() { closeOverlays(); },
    'close-overlays'() { closeOverlays(); },
    'refresh-prices'(el) {
      el.classList.add('spin');
      setTimeout(() => {
        Object.values(N.instruments).forEach((i) => { const move = (Math.random() - 0.45) * 0.002; i.price *= 1 + move; i.dayPct += move; });
        el.classList.remove('spin');
        state.priceMinutes = 0;
        refresh();
        toast('Prices refreshed for 8 instruments');
      }, 700);
    },
    go(el) { go(el.dataset.href); },
  });

  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-action]');
    if (t && actions[t.dataset.action]) { e.preventDefault(); actions[t.dataset.action](t, e); return; }
    const row = e.target.closest('[data-href]');
    if (row && !e.target.closest('a, button, input')) go(row.dataset.href);
  });
  document.addEventListener('keydown', (e) => {
    const typing = /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);
    if (e.key === 'Escape') closeOverlays();
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); actions.palette && actions.palette(); }
    if (e.shiftKey && e.key === 'P' && !typing) actions['toggle-privacy']();
    if (e.key === 'Enter' && !typing && document.activeElement.dataset && document.activeElement.dataset.href) go(document.activeElement.dataset.href);
  });

  /* ---------- Overview ---------- */
  const RANGE_WEEKS = { '1M': 4, '3M': 13, '6M': 26, YTD: null, '1Y': 52, '2Y': 104 };
  const RANGE_LABEL = { '1M': '1 month', '3M': '3 months', '6M': '6 months', YTD: 'Year to date', '1Y': '1 year', '2Y': '2 years' };

  function rangeStart(hist) {
    const last = hist.dates.length - 1;
    if (state.range === 'YTD') return hist.dates.findIndex((dt) => dt >= N.d(2026, 1, 1)) - 1;
    return Math.max(0, last - RANGE_WEEKS[state.range]);
  }

  function allocation(hh) {
    if (state.alloc === 'category') {
      return N.GROUPS.filter((g) => g.key !== 'debt').map((g) => ({ label: g.label, color: g.color, value: hh.byGroup[g.key] }));
    }
    const buckets = new Map();
    const add = (label, value) => buckets.set(label, (buckets.get(label) || 0) + value);
    hh.rows.forEach(({ a, v }) => {
      if (v.value <= 0) return;
      if (state.alloc === 'class') {
        if (a.method === 'holdings') N.holdingRows(a).forEach((h) => add(h.ins.cls, h.value));
        else add({ investment: 'Multi-asset', pension: 'Multi-asset', cash: 'Cash', property: 'Property', other_asset: 'Other' }[a.cat], v.value);
      } else {
        add({ ISA: 'ISA', LISA: 'Lifetime ISA', SIPP: 'Pension', Workplace: 'Pension' }[a.wrapper] || { cash: 'Unwrapped cash', property: 'Property', other_asset: 'Other assets' }[a.cat], v.value);
      }
    });
    const order = state.alloc === 'class'
      ? ['Equity', 'Multi-asset', 'Cash', 'Property', 'Commodity', 'Other']
      : ['ISA', 'Pension', 'Unwrapped cash', 'Property', 'Lifetime ISA', 'Other assets'];
    return order.filter((k) => buckets.has(k)).map((k, i) => ({ label: k, value: buckets.get(k), color: `var(--s${i + 1})` }));
  }

  function overview() {
    const hh = N.totals('household');
    const hist = N.history('household');
    const from = rangeStart(hist);
    const last = hist.dates.length - 1;
    const change = hh.total - hist.total[from];
    const proj = helpers.projection();
    const home = N.accounts.find((a) => a.id === 'home');
    const owed = -N.valuation(N.accounts.find((a) => a.id === 'mortgage')).value;
    const ltv = owed / N.valuation(home).value;

    const people = N.people.map((p) => {
      const t = N.totals(p.id);
      const ph = N.history(p.id);
      const m = t.total - ph.total[last - 4];
      return `<a class="person-row" href="#/people/${p.id}">
        <span class="avatar">${p.initial}</span>
        <span><span class="person-name">${p.name}</span><span class="caption"> · 1 month ${fmt.delta(m)}</span></span>
        <span class="figure figure-md">${fmt.gbp(t.total)}</span>
        <span class="bar" aria-label="${fmt.pct(t.total / hh.total, 0)} of household"><span style="width:${(t.total / hh.total) * 100}%"></span></span>
      </a>`;
    }).join('');

    const segs = allocation(hh);
    const segTotal = segs.reduce((s, g) => s + g.value, 0);
    const legend = segs.map((g) => `<div><span class="swatch" style="background:${g.color}"></span><span>${g.label}</span><span class="num">${fmt.gbp(g.value, { compact: true })}</span><span class="num muted" style="text-align:right">${fmt.pct(g.value / segTotal, 0)}</span></div>`).join('');

    const al = N.allowances;
    const daysLeft = Math.round((al.end - N.TODAY) / N.DAY);
    const allowRows = N.people.map((p) => {
      const u = al[p.id];
      return `<div class="allow">
        <div class="allow-head"><span><b>${p.name}</b> · ISA</span><span class="num">${fmt.gbp(u.isa)} of ${fmt.gbp(al.limits.isa)}</span></div>
        <div class="meter" role="meter" aria-valuemin="0" aria-valuemax="${al.limits.isa}" aria-valuenow="${u.isa}" aria-label="${p.name} ISA allowance used"><span style="width:${(u.isa / al.limits.isa) * 100}%"></span></div>
        <span class="caption">${fmt.gbp(al.limits.isa - u.isa)} left${u.lisa ? ` · Lifetime ISA ${fmt.gbp(u.lisa)} of ${fmt.gbp(al.limits.lisa)}` : ''} · Pension ${fmt.gbp(u.pension)} of ${fmt.gbp(al.limits.pension)}</span>
      </div>`;
    }).join('');

    const soon = [];
    N.plans.forEach((p) => N.occurrences(p, N.TODAY, N.addDays(N.TODAY, 30)).forEach((dt) => soon.push({ dt, p })));
    soon.sort((a, b) => a.dt - b.dt);
    const acc = N.accountById();
    const stale = hh.rows.filter((r) => r.v.staleness !== 'ok');
    const coming = stale.map(({ a, v }) => `<div class="list-row"><span class="status ${v.staleness}">${ICON.warn}</span><span>${esc(a.provider)} ${esc(a.name.toLowerCase())}<span class="caption"> · last updated ${v.age} days ago</span></span><button class="btn sm" type="button" data-action="quick-update">Update</button></div>`).join('') +
      soon.slice(0, 5).map(({ dt, p }) => `<div class="list-row"><span class="date-stamp">${fmt.dayMonth(dt)}</span><span>${esc(p.name)}<span class="caption"> · ${esc(acc[p.account].provider)}</span></span><span class="num">${fmt.gbp(p.gross)}</span></div>`).join('') +
      `<div class="list-row"><span class="date-stamp">2029</span><span>Mortgage fix ends 31 May<span class="caption"> · in ${fmt.duration(N.TODAY, N.d(2029, 5, 31))}</span></span><a class="link-btn" href="#/property">Plan</a></div>`;

    const rowsByGroup = N.GROUPS.map((g) => {
      const rows = hh.rows.filter((r) => r.v.group === g.key);
      if (!rows.length) return '';
      const sub = rows.reduce((s, r) => s + r.v.value, 0);
      return `<tr class="group"><td colspan="3"><span class="swatch" style="background:${g.color}"></span> ${g.label}</td><td class="r">${fmt.gbp(sub)}</td><td></td></tr>` +
        rows.map(({ a, v }) => `<tr class="link" tabindex="0" data-href="${helpers.hrefFor(a)}">
          <td>${esc(a.name)}<span class="sub">${esc(a.provider)} · ${helpers.wrapper(a)}</span></td>
          <td>${helpers.owners(a)}</td>
          <td class="r">${v.day ? fmt.delta(v.day) : '<span class="muted">–</span>'}</td>
          <td class="r">${fmt.gbp(v.value)}</td>
          <td class="r">${helpers.status(v)}</td></tr>`).join('');
    }).join('');

    const movers = {};
    N.accounts.filter((a) => a.method === 'holdings').forEach((a) => N.holdingRows(a).forEach((h) => {
      const m = movers[h.i] || (movers[h.i] = { ins: h.ins, day: 0 });
      m.day += h.day;
    }));
    const moverRows = Object.values(movers).sort((a, b) => Math.abs(b.day) - Math.abs(a.day)).slice(0, 5)
      .map((m) => `<div class="list-row"><span class="tag mono">${m.ins.symbol}</span><span class="caption">${esc(m.ins.name)}</span><span>${fmt.delta(m.day, m.ins.dayPct)}</span></div>`).join('');

    const mortgageFree = N.summarise(proj.loanRows.mortgage).payoff;
    const ms = [
      { k: 'Net worth passes', v: fmt.gbp(750000, { compact: true }), dt: N.firstReaching(proj.dates, proj.total, 750000) },
      { k: 'Net worth passes', v: fmt.gbp(1000000, { compact: true }), dt: N.firstReaching(proj.dates, proj.total, 1000000) },
      { k: 'Mortgage-free', v: fmt.monthYear(mortgageFree), dt: null, note: `${fmt.duration(N.TODAY, mortgageFree)} away` },
      { k: 'You can access your pension', v: fmt.monthYear(N.birthday(N.people[0], 57)), dt: null, note: 'Age 57' },
    ].map((m) => `<div class="ms"><span class="eyebrow">${m.k}</span><span class="figure figure-md">${m.v}</span><span class="caption">${m.dt ? fmt.monthYear(m.dt) : m.note}</span></div>`).join('');

    return {
      title: 'Overview',
      html: `
      <div class="filter-row">
        <span class="eyebrow">Range</span>
        ${helpers.seg('range', Object.keys(RANGE_WEEKS).map((k) => [k, k]), state.range, 'Time range')}
        <span class="caption">Applies to every figure on this page</span>
      </div>
      <div class="grid">
        <section class="panel span-8 hero" aria-label="Household net worth">
          <div class="hero-top">
            <div class="hero-figure">
              <span class="eyebrow">Household net worth · ${fmt.date(N.TODAY)}</span>
              <span class="figure figure-xl">${fmt.hero(hh.total)}</span>
              <div class="chips">
                <span><span class="chip-label">Today</span>${fmt.delta(hh.day, hh.day / (hh.total - hh.day))}</span>
                <span><span class="chip-label">${RANGE_LABEL[state.range]}</span>${fmt.delta(change, change / hist.total[from])}</span>
              </div>
            </div>
            ${helpers.seg('heroView', [['total', 'Total'], ['category', 'By category']], state.heroView, 'Chart view')}
          </div>
          <div class="chart" id="hero-chart"></div>
        </section>
        <div class="stack span-4">
          <section class="section">
            <div class="section-head"><h2>People</h2><span class="caption">Joint items split by ownership</span></div>
            ${people}
          </section>
          <div class="tiles">
            <div class="tile"><span class="eyebrow">Accessible now</span><span class="figure figure-md">${fmt.gbp(hh.liquid, { compact: true })}</span><span class="caption">ISAs, cash, less cards and loans</span></div>
            <div class="tile"><span class="eyebrow">Locked away</span><span class="figure figure-md">${fmt.gbp(hh.locked, { compact: true })}</span><span class="caption">Pensions, LISA, home equity</span></div>
            <div class="tile"><span class="eyebrow">Total debt</span><span class="figure figure-md">${fmt.gbp(hh.debts, { compact: true })}</span><span class="caption">Mortgage, car loan, card</span></div>
            <div class="tile"><span class="eyebrow">Mortgage LTV</span><span class="figure figure-md">${fmt.pct(ltv)}</span><span class="caption">${fmt.gbp(owed, { compact: true })} on ${fmt.gbp(N.valuation(home).value, { compact: true })}</span></div>
          </div>
        </div>

        <section class="section span-4">
          <div class="section-head"><h2>Allocation</h2>${helpers.seg('alloc', [['category', 'Category'], ['class', 'Asset class'], ['wrapper', 'Wrapper']], state.alloc, 'Allocation grouping')}</div>
          <div class="alloc"><div id="alloc-donut"></div><div class="alloc-legend">${legend}</div></div>
        </section>
        <section class="section span-4">
          <div class="section-head"><h2>Allowances ${al.taxYear}</h2><span class="caption">${daysLeft} days left · ends ${fmt.date(al.end)}</span></div>
          ${allowRows}
        </section>
        <section class="section span-4">
          <div class="section-head"><h2>Coming up</h2><span class="caption">Next 30 days</span></div>
          ${coming}
        </section>

        <section class="section span-8">
          <div class="section-head"><h2>Accounts</h2><span class="caption">${hh.rows.length} accounts · select a row to open it</span></div>
          <div class="table-wrap"><table class="ledger">
            <thead><tr><th>Account</th><th>Owners</th><th class="r">Today</th><th class="r">Value</th><th class="r">Updated</th></tr></thead>
            <tbody>${rowsByGroup}</tbody>
            <tfoot><tr><td colspan="3">Net worth</td><td class="r">${fmt.gbp(hh.total)}</td><td></td></tr></tfoot>
          </table></div>
        </section>
        <div class="stack span-4">
          <section class="section">
            <div class="section-head"><h2>Today's movers</h2><span class="caption">Across all holdings</span></div>
            ${moverRows}
          </section>
        </div>

        <section class="section span-12">
          <div class="section-head"><h2>Milestones</h2><a class="link-btn" href="#/projections">Open projections</a></div>
          <div class="milestones">${ms}</div>
          <p class="footer-note">Projected with the base scenario: 6% a year on investments and pensions before fees, 3% on the home, current plans continuing. Illustrations, not advice.</p>
        </section>
      </div>`,
      mount() {
        const n = last - from + 1;
        const dates = hist.dates.slice(from);
        const base = {
          dates, height: 250, label: 'Household net worth over time',
          fmtY: fmt.axis, fmtX: n <= 14 ? fmt.dayMonth : fmt.monYY, fmtTip: (v) => fmt.gbp(v), fmtTipDate: (dt) => 'Week of ' + fmt.date(dt),
        };
        if (state.heroView === 'total') {
          C.timeChart($('#hero-chart'), { ...base, series: [{ label: 'Net worth', color: 'var(--accent)', values: hist.total.slice(from) }], wash: true, zero: false });
        } else {
          C.timeChart($('#hero-chart'), {
            ...base, stacked: true,
            series: N.GROUPS.map((g) => ({ label: g.label, color: g.color, values: hist.byGroup[g.key].slice(from) })),
            total: { label: 'Net worth', values: hist.total.slice(from) },
          });
        }
        C.donut($('#alloc-donut'), segs, {
          size: 164, thickness: 20, label: 'Allocation of assets',
          centerLabel: 'Assets', centerValue: fmt.gbp(segTotal, { compact: true }),
          fmt: (v, share) => `${fmt.gbp(v, { compact: true })} · ${fmt.pct(share, 0)}`,
        });
      },
    };
  }

  route(/^\/overview$/, overview);

  function start() {
    const theme = store.get('theme', null);
    if (theme) document.documentElement.dataset.theme = theme;
    window.addEventListener('hashchange', () => refresh(false));
    refresh(false);
    setInterval(() => { state.priceMinutes += 1; renderNav(location.hash.replace(/^#/, '') || '/overview'); }, 60000);
  }

  window.App = { N, C, $, esc, state, store, fmt, ICON, helpers, route, actions, refresh, go, toast, openOverlay, closeOverlays, start };
})();

/* Waymark mockup: person pages and account pages. */
(function () {
  'use strict';
  const { N, C, $, esc, state, fmt, ICON, helpers, route, actions, refresh, toast, openOverlay, closeOverlays } = window.App;

  /* ---------- inline editing ---------- */
  const commit = {
    balance(ds, value) {
      const a = N.accounts.find((x) => x.id === ds.id);
      if (a.method === 'model') { a.anchor = value; a.anchorDate = N.TODAY; } else { a.balance = value; a.asOf = N.TODAY; }
      toast(`${a.provider} ${a.name.toLowerCase()} saved as ${fmt.gbp(value).replace(/<[^>]+>/g, '')} on ${fmt.date(N.TODAY)}`);
      refresh();
    },
    holding(ds, value) {
      const a = N.accounts.find((x) => x.id === ds.id);
      const h = a.holdings.find((x) => x.i === ds.inst);
      if (value < 0) { toast('Enter a number of zero or more'); refresh(); return; }
      h[ds.field] = value;
      (N.transactions[a.id] || (N.transactions[a.id] = [])).unshift({ date: N.TODAY, type: 'ADJUSTMENT', sym: ds.inst, units: ds.field === 'units' ? value : null, amount: 0, note: `${ds.field === 'units' ? 'Units' : 'Average cost'} edited in holdings` });
      toast(`Saved as an adjustment dated ${fmt.date(N.TODAY)}`);
      refresh();
    },
    cash(ds, value) {
      N.accounts.find((x) => x.id === ds.id).cash = value;
      toast('Uninvested cash updated');
      refresh();
    },
  };
  const editable = (display, raw, data, label) =>
    `<button type="button" class="editable" data-action="edit-cell" data-raw="${raw}" data-label="${esc(label)}" ${Object.entries(data).map(([k, v]) => `data-${k}="${esc(v)}"`).join(' ')} aria-label="Edit ${esc(label)}">${display}</button>`;

  actions['edit-cell'] = (el) => {
    const input = document.createElement('input');
    input.className = 'cell-input';
    input.type = 'number';
    input.step = 'any';
    input.id = 'edit-' + (el.dataset.id || '') + (el.dataset.inst || '') + (el.dataset.field || '');
    input.value = el.dataset.raw;
    input.setAttribute('aria-label', el.dataset.label);
    const ds = { ...el.dataset };
    el.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const finish = (save) => {
      if (done) return;
      done = true;
      if (save && input.value !== '' && !isNaN(+input.value) && +input.value !== +ds.raw) commit[ds.kind](ds, +input.value);
      else refresh();
    };
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') finish(true);
      if (e.key === 'Escape') { e.stopPropagation(); finish(false); }
    });
    input.addEventListener('blur', () => finish(true));
  };

  actions['confirm-pending'] = () => {
    const a = N.accounts.find((x) => x.id === 'isa-you');
    (N.transactions['isa-you'] || []).forEach((t) => {
      if (t.status !== 'pending') return;
      t.status = 'confirmed';
      if (t.type === 'BUY') a.holdings.find((h) => h.i === t.sym).units += t.units;
    });
    state.pending = false;
    closeOverlays();
    toast('3 entries confirmed · holdings updated');
    refresh();
  };

  /* ---------- small builders ---------- */
  const accountsFor = (pid, cats) => N.accounts.filter((a) => (a.owners[pid] || 0) > 0 && cats.includes(a.cat));
  const scale = (series, ratio) => series.map((v) => v * ratio);

  function pensionForecast(a, pid) {
    const p = N.personById[pid];
    const years = N.yearsBetween(N.TODAY, N.birthday(p, p.retire));
    const r = 0.06 - (a.fee || 0);
    const monthly = N.plans.filter((x) => x.account === a.id).reduce((s, x) => s + (x.freq === 'monthly' ? x.gross : x.gross / 12), 0);
    const g = Math.pow(1 + r, years);
    return Math.abs(N.valuation(a).value) * g + monthly * 12 * ((g - 1) / r);
  }

  function accountCard(a, pid, hist) {
    const v = N.valuation(a);
    const s = a.owners[pid] || 1;
    const groupNow = N.totals(pid).byGroup[v.group] || 1;
    const spark = C.sparkline(scale(hist.byGroup[v.group].slice(-27), (v.value * s) / groupNow), { w: 110, h: 34, color: 'var(--ink-2)' });
    const plansFor = N.plans.filter((x) => x.account === a.id);
    let foot = helpers.status(v);
    if (v.gain != null) foot = `<span class="caption">Gain since cost</span> ${v.gain >= 0 ? fmt.delta(v.gain, v.gain / v.cost) : fmt.delta(v.gain, v.gain / v.cost)}`;
    let extra = '';
    if (a.cat === 'pension') {
      const split = plansFor.reduce((t, x) => ({ you: t.you + (x.split ? x.split.you : x.amount), employer: t.employer + (x.split ? x.split.employer : 0), relief: t.relief + (x.split ? x.split.relief : 0) }), { you: 0, employer: 0, relief: 0 });
      extra = `<div class="caption">Each month: ${fmt.gbp(split.you)} from ${N.personById[pid].name === 'You' ? 'you' : 'them'}${split.employer ? ` · ${fmt.gbp(split.employer)} employer` : ''}${split.relief ? ` · ${fmt.gbp(split.relief)} tax relief` : ''}</div>
        <div class="caption">About ${fmt.gbp(pensionForecast(a, pid), { compact: true })} at ${N.personById[pid].retire} · accessible from ${fmt.monthYear(N.birthday(N.personById[pid], 57))}</div>`;
    }
    return `<div class="card" role="link" tabindex="0" data-href="${helpers.hrefFor(a)}">
      <div class="card-top"><div><div><b>${esc(a.name)}</b></div><div class="caption">${esc(a.provider)}</div></div><span class="tag">${helpers.wrapper(a)}</span></div>
      <div class="card-top"><span class="figure figure-md">${fmt.gbp(Math.abs(v.value) * s)}</span>${spark}</div>
      ${extra}
      <div class="card-foot">${foot}${v.day ? `<span>${fmt.delta(v.day)}</span>` : ''}</div>
    </div>`;
  }

  /* ---------- person page ---------- */
  function personPage(pid) {
    const p = N.personById[pid];
    const t = N.totals(pid), hh = N.totals('household');
    const hist = N.history(pid);
    const last = hist.dates.length - 1;
    const age = Math.floor(N.yearsBetween(p.dob, N.TODAY));
    const key = 'person-' + pid;
    const tab = helpers.tab(key, 'summary');
    const mortgageShare = N.valuation(N.accounts.find((a) => a.id === 'mortgage')).value * 0.5;

    let body = '';
    let mount = null;
    if (tab === 'summary') {
      const monthly = N.plans.filter((x) => x.owner === pid || x.owner === 'joint').map((x) => ({ x, amt: (x.freq === 'monthly' ? x.gross : x.gross / 12) * (x.owner === 'joint' ? 0.5 : 1) }));
      const monthlyTotal = monthly.reduce((s, m) => s + m.amt, 0);
      const al = N.allowances[pid];
      body = `
      <div class="kpis">
        <div class="kpi"><span class="eyebrow">Investments</span><span class="figure figure-md">${fmt.gbp(t.byGroup.investment)}</span></div>
        <div class="kpi"><span class="eyebrow">Pensions</span><span class="figure figure-md">${fmt.gbp(t.byGroup.pension)}</span></div>
        <div class="kpi"><span class="eyebrow">Cash</span><span class="figure figure-md">${fmt.gbp(t.byGroup.cash)}</span></div>
        <div class="kpi"><span class="eyebrow">Home equity · 50%</span><span class="figure figure-md">${fmt.gbp(t.byGroup.property + mortgageShare)}</span></div>
        <div class="kpi"><span class="eyebrow">Other assets</span><span class="figure figure-md">${fmt.gbp(t.byGroup.other)}</span></div>
        <div class="kpi"><span class="eyebrow">Other debts</span><span class="figure figure-md">${fmt.gbp(t.byGroup.debt - mortgageShare)}</span></div>
      </div>
      <div class="grid">
        <section class="panel span-8"><div class="section-head"><h2>${p.name === 'You' ? 'Your' : p.name + '’s'} net worth</h2><span class="caption">Last 2 years, weekly</span></div><div class="chart" id="person-chart"></div></section>
        <div class="stack span-4">
          <section class="section"><div class="section-head"><h2>Going in each month</h2><span class="figure figure-md">${fmt.gbp(monthlyTotal)}</span></div>
            ${monthly.map((m) => `<div class="list-row"><span class="date-stamp">${m.x.freq === 'monthly' ? 'Day ' + m.x.day : 'Yearly'}</span><span>${esc(m.x.name)}${m.x.owner === 'joint' ? '<span class="caption"> · your half</span>' : ''}</span><span class="num">${fmt.gbp(m.amt)}</span></div>`).join('')}
          </section>
          <section class="section"><div class="section-head"><h2>ISA allowance ${N.allowances.taxYear}</h2><span class="caption">${fmt.gbp(20000 - al.isa)} left</span></div>
            <div class="meter" role="meter" aria-valuenow="${al.isa}" aria-valuemin="0" aria-valuemax="20000" aria-label="ISA allowance used"><span style="width:${al.isa / 200}%"></span></div>
          </section>
        </div>
      </div>`;
      mount = () => C.timeChart($('#person-chart'), {
        dates: hist.dates, height: 240, label: 'Net worth over time', series: [{ label: 'Net worth', color: 'var(--accent)', values: hist.total }],
        wash: true, zero: false, fmtY: fmt.axis, fmtX: fmt.monYY, fmtTip: (v) => fmt.gbp(v), fmtTipDate: (dt) => 'Week of ' + fmt.date(dt),
      });
    } else if (tab === 'investments' || tab === 'pensions') {
      const cat = tab === 'investments' ? 'investment' : 'pension';
      const list = accountsFor(pid, [cat]);
      const combined = {};
      list.filter((a) => a.method === 'holdings').forEach((a) => N.holdingRows(a).forEach((h) => {
        const c = combined[h.i] || (combined[h.i] = { ins: h.ins, units: 0, value: 0, cost: 0, where: [] });
        c.units += h.units; c.value += h.value; c.cost += h.cost; c.where.push(a.wrapper);
      }));
      const rows = Object.values(combined).sort((a, b) => b.value - a.value);
      body = `<div class="cards">${list.map((a) => accountCard(a, pid, hist)).join('')}</div>` +
        (rows.length ? `<section class="section"><div class="section-head"><h2>Combined holdings</h2><span class="caption">The same fund across accounts, added together</span></div>
        <div class="table-wrap"><table class="ledger"><thead><tr><th>Instrument</th><th>Held in</th><th class="r">Units</th><th class="r">Value</th><th class="r">Gain</th></tr></thead><tbody>
        ${rows.map((r) => `<tr><td><span class="tag mono">${r.ins.symbol}</span> ${esc(r.ins.name)}</td><td>${r.where.join(', ')}</td><td class="r">${fmt.units(r.units)}</td><td class="r">${fmt.gbp(r.value)}</td><td class="r">${fmt.delta(r.value - r.cost, (r.value - r.cost) / r.cost)}</td></tr>`).join('')}
        </tbody></table></div></section>` : '');
    } else if (tab === 'cash') {
      const list = accountsFor(pid, ['cash']);
      body = `<section class="section"><div class="section-head"><h2>Cash accounts</h2><span class="caption">Select a balance to change it</span></div>
      <div class="table-wrap"><table class="ledger"><thead><tr><th>Account</th><th>Owners</th><th class="r">Interest</th><th class="r">Balance</th><th class="r">Updated</th></tr></thead><tbody>
      ${list.map((a) => { const v = N.valuation(a); return `<tr><td>${esc(a.name)}<span class="sub">${esc(a.provider)}</span></td><td>${helpers.owners(a)}</td><td class="r">${a.rate ? fmt.pct(a.rate, 2) : '<span class="muted">–</span>'}</td><td class="r">${editable(fmt.gbp(a.balance, { dp: 2 }), a.balance, { kind: 'balance', id: a.id }, a.provider + ' balance')}</td><td class="r">${helpers.status(v)}</td></tr>`; }).join('')}
      </tbody><tfoot><tr><td colspan="3">${p.name === 'You' ? 'Your' : 'Their'} share of cash</td><td class="r">${fmt.gbp(t.byGroup.cash, { dp: 2 })}</td><td></td></tr></tfoot></table></div></section>`;
    } else if (tab === 'property') {
      const home = N.accounts.find((a) => a.id === 'home');
      const hv = N.valuation(home).value;
      body = `<div class="cards"><div class="card" role="link" tabindex="0" data-href="#/property">
        <div class="card-top"><div><b>Home</b><div class="caption">${esc(home.provider)} · owned 50/50</div></div><span class="icon-tile">${ICON.home}</span></div>
        <div class="tiles"><div class="tile"><span class="eyebrow">Your half of value</span><span class="figure figure-md">${fmt.gbp(hv / 2)}</span></div><div class="tile"><span class="eyebrow">Your half of mortgage</span><span class="figure figure-md">${fmt.gbp(mortgageShare)}</span></div></div>
        <div class="card-foot"><span>Equity <b>${fmt.gbp(hv / 2 + mortgageShare)}</b></span><span class="link-btn">Open property ${ICON.arrow}</span></div>
      </div></div>`;
    } else if (tab === 'other') {
      const list = accountsFor(pid, ['other_asset', 'loan', 'credit_card']);
      body = list.length ? `<div class="cards">${list.map((a) => accountCard(a, pid, hist)).join('')}</div>` : `<p class="caption">Nothing here yet.</p>`;
    } else {
      const list = N.plans.filter((x) => x.owner === pid || x.owner === 'joint');
      const acc = N.accountById();
      body = `<section class="section"><div class="section-head"><h2>Regular payments</h2><button class="btn sm" type="button" data-action="add-plan">${ICON.plus}Add plan</button></div>
      <div class="table-wrap"><table class="ledger"><thead><tr><th>Plan</th><th>Into</th><th>When</th><th class="r">You pay</th><th class="r">Goes in</th><th class="r">Next</th></tr></thead><tbody>
      ${list.map((x) => { const next = N.occurrences(x, N.TODAY, N.addMonths(N.TODAY, 13))[0]; return `<tr><td>${esc(x.name)}${x.auto ? ' <span class="tag">Auto-records</span>' : ''}${x.alloc ? `<span class="sub">${x.alloc.map(([s, w]) => `${Math.round(w * 100)}% ${N.instruments[s].symbol}`).join(' · ')}</span>` : ''}</td><td>${esc(acc[x.account].provider)}<span class="sub">${esc(acc[x.account].name)}</span></td><td>${x.freq === 'monthly' ? 'Monthly, day ' + x.day : 'Yearly, 6 Apr'}</td><td class="r">${fmt.gbp(x.amount * (x.owner === 'joint' ? 0.5 : 1))}</td><td class="r">${fmt.gbp(x.gross)}</td><td class="r mono">${next ? fmt.dayMonth(next) : '–'}</td></tr>`; }).join('')}
      </tbody></table></div></section>`;
    }

    return {
      title: p.name === 'You' ? 'You' : p.name,
      html: `
      <div class="page-head">
        <div class="who">
          <span class="avatar lg">${p.initial}</span>
          <div class="hero-figure">
            <span class="eyebrow">Age ${age} · ${fmt.pct(t.total / hh.total, 0)} of household</span>
            <span class="figure figure-lg">${fmt.hero(t.total)}</span>
            <div class="chips">
              <span><span class="chip-label">Today</span>${fmt.delta(t.day)}</span>
              <span><span class="chip-label">1 month</span>${fmt.delta(t.total - hist.total[last - 4])}</span>
              <span><span class="chip-label">1 year</span>${fmt.delta(t.total - hist.total[last - 52], (t.total - hist.total[last - 52]) / hist.total[last - 52])}</span>
            </div>
          </div>
        </div>
      </div>
      ${helpers.tabs(key, [['summary', 'Summary'], ['investments', 'Investments'], ['pensions', 'Pensions'], ['cash', 'Cash'], ['property', 'Property'], ['other', 'Other'], ['plans', 'Plans']], tab)}
      ${body}`,
      mount,
    };
  }

  /* ---------- account page ---------- */
  function accountPage(id) {
    const a = N.accounts.find((x) => x.id === id);
    if (!a) return { title: 'Account not found', html: '<p>That account does not exist. <a href="#/overview">Back to the overview</a></p>' };
    const v = N.valuation(a);
    const owner = Object.keys(a.owners)[0];
    const key = 'acct-' + id;
    const holdings = a.method === 'holdings';
    const tab = helpers.tab(key, holdings ? 'holdings' : 'balances');
    let body = '', mount = null;

    if (tab === 'holdings') {
      const rows = N.holdingRows(a);
      const total = Math.abs(v.value);
      const txPending = id === 'isa-you' && state.pending;
      body = `${txPending ? `<div class="banner">${ICON.warn}<span><b>3 entries from Monthly ISA</b> are waiting for you to confirm with the units Trading 212 actually bought.</span><button class="btn sm" type="button" data-action="tab" data-key="${key}" data-value="transactions">Review</button></div>` : ''}
      <div class="grid">
        <section class="section span-8">
          <div class="section-head"><h2>Holdings</h2><span class="caption">Select units or average cost to edit</span></div>
          <div class="table-wrap"><table class="ledger">
            <thead><tr><th>Instrument</th><th class="r">Units</th><th class="r">Avg cost</th><th class="r">Price</th><th class="r">Value</th><th class="r">Gain</th><th class="r">Today</th></tr></thead>
            <tbody>${rows.map((h) => `<tr>
              <td><span class="tag mono">${h.ins.symbol}</span><span class="sub">${esc(h.ins.name)}</span></td>
              <td class="r">${editable(fmt.units(h.units), h.units, { kind: 'holding', id, inst: h.i, field: 'units' }, h.ins.symbol + ' units')}</td>
              <td class="r">${editable(fmt.price(h.avg), h.avg, { kind: 'holding', id, inst: h.i, field: 'avg' }, h.ins.symbol + ' average cost')}</td>
              <td class="r">${fmt.price(h.ins.price)}<span class="sub mono">${h.ins.ccy === 'GBp' ? (h.ins.price * 100).toLocaleString('en-GB', { maximumFractionDigits: 1 }) + 'p' : h.ins.ccy === 'USD' ? '$' + h.ins.priceUsd.toFixed(2) + ' @ ' + h.ins.fx : 'GBP'}</span></td>
              <td class="r">${fmt.gbp(h.value, { dp: 2 })}</td>
              <td class="r">${fmt.delta(h.gain, h.gainPct)}</td>
              <td class="r">${fmt.delta(h.day, h.dayPct)}</td></tr>`).join('')}
              <tr><td>Cash<span class="sub">Not yet invested</span></td><td></td><td></td><td></td><td class="r">${editable(fmt.gbp(a.cash, { dp: 2 }), a.cash, { kind: 'cash', id }, 'Uninvested cash')}</td><td></td><td></td></tr>
            </tbody>
            <tfoot><tr><td colspan="4">Total</td><td class="r">${fmt.gbp(total, { dp: 2 })}</td><td class="r">${fmt.delta(v.gain, v.gain / v.cost)}</td><td class="r">${fmt.delta(v.day)}</td></tr></tfoot>
          </table></div>
        </section>
        <section class="section span-4">
          <div class="section-head"><h2>Weights</h2><button class="btn sm" type="button" data-action="add-holding" data-id="${id}">${ICON.plus}Add holding</button></div>
          ${rows.slice().sort((x, y) => y.value - x.value).map((h) => `<div class="allow"><div class="allow-head"><span class="mono">${h.ins.symbol}</span><span class="num">${fmt.pct(h.value / total)}</span></div><div class="bar"><span style="width:${(h.value / total) * 100}%;background:var(--s1)"></span></div></div>`).join('')}
          <p class="footer-note">Editing units or average cost never overwrites history: it records an adjustment, so imported transactions can replace it later.</p>
        </section>
      </div>`;
    } else if (tab === 'transactions') {
      const tx = N.transactions[id] || [];
      body = `<section class="section"><div class="section-head"><h2>Transactions</h2>${tx.some((x) => x.status === 'pending') ? `<button class="btn sm primary" type="button" data-action="confirm-pending">Confirm 3 pending</button>` : ''}</div>
        ${tx.length ? `<div class="table-wrap"><table class="ledger"><thead><tr><th>Date</th><th>Type</th><th>Instrument</th><th class="r">Units</th><th class="r">Cash effect</th><th>Note</th></tr></thead><tbody>
        ${tx.map((x) => `<tr class="${x.status === 'pending' ? 'pending' : ''}"><td class="mono">${fmt.date(x.date)}</td><td><span class="tag ${x.status === 'pending' ? 'pending' : ''}">${x.type.replace('_', ' ')}${x.status === 'pending' ? ' · pending' : ''}</span></td><td class="mono">${x.sym ? N.instruments[x.sym].symbol : '–'}</td><td class="r">${x.units != null ? fmt.units(x.units) : '–'}</td><td class="r">${x.amount ? fmt.gbp(x.amount, { dp: 2, sign: true }) : x.cost ? `<span class="caption">cost ${fmt.gbp(x.cost, { dp: 2 })}</span>` : '–'}</td><td class="caption">${esc(x.note || '')}</td></tr>`).join('')}
        </tbody></table></div>` : `<p class="caption">No transactions yet. These holdings were entered as opening balances; importing your platform's history (Phase 8) fills this in.</p>`}
      </section>`;
    } else if (tab === 'balances') {
      const entries = N.balanceEntries(a);
      body = `<div class="grid">
        <section class="section span-6"><div class="section-head"><h2>${a.method === 'model' ? 'Valuations' : 'Balances'}</h2><span class="caption">Newest first</span></div>
          <div class="table-wrap"><table class="ledger"><thead><tr><th>Date</th><th class="r">${a.method === 'model' ? 'Valued at' : 'Balance'}</th><th>Source</th></tr></thead><tbody>
          <tr><td class="mono">${fmt.date(N.TODAY)}</td><td class="r">${editable('<span class="caption">Add today’s figure</span>', entries[0].value.toFixed(2), { kind: 'balance', id }, 'New balance')}</td><td></td></tr>
          ${entries.map((e) => `<tr><td class="mono">${fmt.date(e.date)}</td><td class="r">${fmt.gbp(e.value, { dp: 2 })}</td><td class="caption">${e.source}</td></tr>`).join('')}
          </tbody></table></div></section>
        <section class="panel span-6"><div class="section-head"><h2>Over time</h2></div><div class="chart" id="bal-chart"></div></section>
      </div>`;
      mount = () => {
        const e = entries.slice().reverse();
        C.timeChart($('#bal-chart'), { dates: e.map((x) => x.date), height: 220, series: [{ label: 'Balance', color: 'var(--accent)', values: e.map((x) => x.value) }], wash: true, zero: false, label: 'Balance history', fmtY: fmt.axis, fmtX: fmt.monYY, fmtTip: (x) => fmt.gbp(x, { dp: 2 }), fmtTipDate: fmt.date });
      };
    } else if (tab === 'history') {
      const hist = N.history(owner);
      const groupNow = N.totals(owner).byGroup[v.group] || 1;
      const values = scale(hist.byGroup[v.group], Math.abs(v.value) * a.owners[owner] / groupNow);
      const cost = v.cost || Math.abs(v.value) * 0.85;
      const contrib = values.map((_, i) => cost * (0.62 + 0.38 * (i / (values.length - 1))));
      body = `<section class="panel"><div class="section-head"><h2>Value and money paid in</h2><span class="caption">The gap between the lines is investment growth</span></div><div class="chart" id="acct-chart"></div></section>`;
      mount = () => C.timeChart($('#acct-chart'), {
        dates: hist.dates, height: 260, label: 'Account value and net contributions',
        series: [{ label: 'Value', color: 'var(--s1)', values }, { label: 'Paid in', color: 'var(--s2)', values: contrib }],
        zero: false, fmtY: fmt.axis, fmtX: fmt.monYY, fmtTip: (x) => fmt.gbp(x), fmtTipDate: (dt) => 'Week of ' + fmt.date(dt),
      });
    } else if (tab === 'plans') {
      const list = N.plans.filter((x) => x.account === id);
      body = `<section class="section"><div class="section-head"><h2>Plans paying into this account</h2><button class="btn sm" type="button" data-action="add-plan">${ICON.plus}Add plan</button></div>
        ${list.length ? list.map((x) => `<div class="list-row"><span class="date-stamp">${x.freq === 'monthly' ? 'Day ' + x.day : '6 Apr'}</span><span>${esc(x.name)}${x.alloc ? `<span class="caption"> · ${x.alloc.map(([s, w]) => `${Math.round(w * 100)}% ${N.instruments[s].symbol}`).join(', ')}</span>` : ''}</span><span class="num">${fmt.gbp(x.gross)}</span></div>`).join('') : '<p class="caption">No regular payments go into this account.</p>'}
      </section>`;
    } else {
      body = `<section class="section" style="max-width:720px"><div class="section-head"><h2>Account settings</h2></div>
        <div class="form-grid">
          <div class="field"><label for="set-name">Name</label><input class="input" id="set-name" value="${esc(a.name)}"></div>
          <div class="field"><label for="set-provider">Provider</label><input class="input" id="set-provider" value="${esc(a.provider)}"></div>
          <div class="field"><label for="set-return">Expected return</label><div class="affix"><input class="input has-post" id="set-return" type="number" step="0.1" value="6.0"><span class="post">%</span></div></div>
          <div class="field"><label for="set-fee">Annual fees</label><div class="affix"><input class="input has-post" id="set-fee" type="number" step="0.01" value="${((a.fee || 0) * 100).toFixed(2)}"><span class="post">%</span></div></div>
          <div class="field full"><span class="label">Owners</span><div class="caption">${Object.entries(a.owners).map(([pid, s]) => `${helpers.personName(pid)} ${Math.round(s * 100)}%`).join(' · ')}${a.wrapper ? ' · tax wrappers always have one owner' : ''}</div></div>
        </div>
        <div class="dialog-actions" style="justify-content:flex-start;margin-top:16px"><button class="btn primary" type="button" data-action="saved">Save changes</button><button class="btn" type="button" data-action="saved-archive">Archive account</button></div>
      </section>`;
    }

    const tabs = holdings
      ? [['holdings', 'Holdings'], ['transactions', 'Transactions'], ['history', 'History'], ['plans', 'Plans'], ['settings', 'Settings']]
      : [['balances', a.method === 'model' ? 'Valuations' : 'Balances'], ['history', 'History'], ['plans', 'Plans'], ['settings', 'Settings']];
    return {
      title: `${a.name}`,
      html: `
      <div class="page-head">
        <div class="hero-figure">
          <span class="eyebrow"><a href="#/people/${owner}">${helpers.personName(owner)}</a> · ${esc(a.provider)} · ${helpers.wrapper(a)}</span>
          <span class="figure figure-lg">${fmt.hero(Math.abs(v.value))}</span>
          <div class="chips">
            ${v.gain != null ? `<span><span class="chip-label">Gain since cost</span>${fmt.delta(v.gain, v.gain / v.cost)}</span>` : `<span>${helpers.status(v)}</span>`}
            ${v.day ? `<span><span class="chip-label">Today</span>${fmt.delta(v.day)}</span>` : ''}
            <span>${helpers.owners(a)}</span>
          </div>
        </div>
      </div>
      ${helpers.tabs(key, tabs, tab)}
      ${body}`,
      mount,
    };
  }

  actions.saved = () => toast('Account saved');
  actions['saved-archive'] = () => toast('Archived accounts stay in history. Undo from Settings.');

  route(/^\/people\/(you|partner)$/, personPage);
  route(/^\/accounts\/([\w-]+)$/, accountPage);
})();

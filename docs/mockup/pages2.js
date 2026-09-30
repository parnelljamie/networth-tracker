/* Waymark mockup: property & mortgage, other assets, projections, import, settings,
   quick update, command palette, pending purchases and dialogs. */
(function () {
  'use strict';
  const { N, C, $, esc, state, fmt, ICON, helpers, route, actions, refresh, go, toast, openOverlay, closeOverlays } = window.App;
  const byId = (id) => N.accounts.find((a) => a.id === id);
  const plain = (html) => html.replace(/<[^>]+>/g, '');
  state.sim = { extra: 100, lump: 0, effect: 'reduce_term' };
  state.openYears = { 2026: true };
  state.allYears = false;

  /* ---------- property & mortgage ---------- */
  function simulate(m, owed) {
    const loan = { ...m.loan, effect: state.sim.effect };
    const base = N.schedule(loan, owed, N.TODAY, N.overpaymentFor(m));
    const lumps = state.sim.lump > 0 ? [{ date: N.d(2027, 1, 1), amount: state.sim.lump }] : [];
    const sim = N.schedule(loan, owed, N.TODAY, N.overpaymentFor(m, state.sim.extra, lumps));
    const b = N.summarise(base), s = N.summarise(sim);
    const fixYear = (150 + state.sim.extra) * 12 + state.sim.lump;
    const allowed = owed * m.loan.allowance;
    return `
      <div class="tiles">
        <div class="tile"><span class="eyebrow">Mortgage-free</span><span class="figure figure-md">${fmt.monthYear(s.payoff)}</span><span class="caption">now ${fmt.monthYear(b.payoff)}</span></div>
        <div class="tile"><span class="eyebrow">Time saved</span><span class="figure figure-md">${fmt.duration(s.payoff, b.payoff)}</span><span class="caption">${b.n - s.n} fewer payments</span></div>
        <div class="tile"><span class="eyebrow">Interest saved</span><span class="figure figure-md">${fmt.gbp(b.interest - s.interest)}</span><span class="caption">over the rest of the term</span></div>
        <div class="tile"><span class="eyebrow">Next payment</span><span class="figure figure-md">${fmt.gbp(sim[1].payment, { dp: 2 })}</span><span class="caption">${state.sim.effect === 'reduce_term' ? 'same payment, shorter term' : 'lower payment, same term'}</span></div>
      </div>
      <span class="status ${fixYear > allowed ? 'warn' : 'ok'}">${fixYear > allowed ? ICON.warn : ICON.ok}${fixYear > allowed ? `${fmt.gbp(fixYear)} a year is over the ${fmt.gbp(allowed)} penalty-free limit during the fix` : `${fmt.gbp(fixYear)} a year is within the 10% penalty-free limit during the fix`}</span>`;
  }

  function propertyPage() {
    const home = byId('home'), m = byId('mortgage');
    const value = N.valuation(home).value;
    const owed = -N.valuation(m).value;
    const rows = N.schedule(m.loan, owed, N.TODAY, N.overpaymentFor(m));
    const sum = N.summarise(rows);
    const { rate, period } = N.rateOn(m.loan, N.TODAY);
    const equity = value - owed;

    const years = {};
    rows.forEach((r) => {
      const y = r.date.getUTCFullYear();
      const t = years[y] || (years[y] = { rows: [], payment: 0, interest: 0, principal: 0, over: 0, closing: 0 });
      t.rows.push(r); t.payment += r.payment; t.interest += r.interest; t.principal += r.principal; t.over += r.over; t.closing = r.closing;
    });
    const yearKeys = Object.keys(years).slice(0, state.allYears ? undefined : 6);
    const schedule = yearKeys.map((y) => {
      const t = years[y];
      const open = state.openYears[y];
      return `<tr class="year" tabindex="0" data-action="toggle-year" data-year="${y}" aria-expanded="${!!open}"><td>${open ? '▾' : '▸'} ${y}</td><td class="r">${fmt.gbp(t.payment)}</td><td class="r">${fmt.gbp(t.interest)}</td><td class="r">${fmt.gbp(t.principal)}</td><td class="r">${fmt.gbp(t.over)}</td><td class="r">${fmt.gbp(t.closing)}</td></tr>` +
        (open ? t.rows.map((r) => `<tr><td class="mono">${fmt.date(r.date)}${r.rate !== rate ? ` <span class="tag">${fmt.pct(r.rate, 2)}</span>` : ''}</td><td class="r">${fmt.gbp(r.payment, { dp: 2 })}</td><td class="r">${fmt.gbp(r.interest, { dp: 2 })}</td><td class="r">${fmt.gbp(r.principal, { dp: 2 })}</td><td class="r">${r.over ? fmt.gbp(r.over, { dp: 2 }) : '–'}</td><td class="r">${fmt.gbp(r.closing, { dp: 2 })}</td></tr>`).join('') : '');
    }).join('');

    const span = (a, b) => N.monthsBetween(a, b);
    const total = span(m.loan.start, m.loan.maturity);
    const p0 = m.loan.periods[0], p1 = m.loan.periods[1];

    return {
      title: 'Property & mortgage',
      html: `
      <div class="page-head"><div class="hero-figure"><span class="eyebrow">${esc(home.provider)} · owned 50/50 · bought ${fmt.monthYear(home.purchase.date)} for ${fmt.gbp(home.purchase.price)}</span><span class="figure figure-lg">${fmt.hero(equity)}</span><span class="caption">Home equity · ${fmt.gbp(equity / 2)} each</span></div></div>
      <div class="kpis">
        <div class="kpi"><span class="eyebrow">Home value</span><span class="figure figure-md">${fmt.gbp(value)}</span><span class="caption">+3% a year since ${fmt.gbp(home.anchor)} on ${fmt.date(home.anchorDate)}</span></div>
        <div class="kpi"><span class="eyebrow">Mortgage owed</span><span class="figure figure-md">${fmt.gbp(owed)}</span><span class="caption">Estimated from the ${fmt.date(m.asOf)} statement</span></div>
        <div class="kpi"><span class="eyebrow">Loan to value</span><span class="figure figure-md">${fmt.pct(owed / value)}</span><span class="caption">Next band at 40%</span></div>
        <div class="kpi"><span class="eyebrow">Rate</span><span class="figure figure-md">${fmt.pct(rate, 2)}</span><span class="caption">${period.label} ends ${fmt.date(period.end)} · in ${fmt.duration(N.TODAY, period.end)}</span></div>
        <div class="kpi"><span class="eyebrow">Monthly payment</span><span class="figure figure-md">${fmt.gbp(rows[0].payment, { dp: 2 })}</span><span class="caption">plus ${fmt.gbp(150)} overpayment</span></div>
        <div class="kpi"><span class="eyebrow">Mortgage-free</span><span class="figure figure-md">${fmt.monthYear(sum.payoff)}</span><span class="caption">Contract ends ${fmt.monthYear(m.loan.maturity)}</span></div>
      </div>
      <div class="grid">
        <section class="panel span-8"><div class="section-head"><h2>Value, mortgage and equity</h2><span class="caption">Solid is history, dashed is projected</span></div><div class="chart" id="prop-chart"></div></section>
        <section class="section span-4">
          <div class="section-head"><h2>Overpayment calculator</h2><span class="caption">On top of today’s £150 a month</span></div>
          <div class="stack">
            <div class="field"><label for="sim-extra">Extra each month: <b id="sim-extra-label">${fmt.gbp(state.sim.extra)}</b></label><input type="range" id="sim-extra" min="0" max="1000" step="25" value="${state.sim.extra}"></div>
            <div class="field"><label for="sim-lump">One-off lump sum in January 2027</label><div class="affix"><span class="pre">£</span><input class="input has-pre" id="sim-lump" type="number" min="0" step="500" value="${state.sim.lump}"></div></div>
            ${helpers.seg('sim.effect', [['reduce_term', 'Shorten the term'], ['reduce_payment', 'Lower the payment']], state.sim.effect, 'What overpaying does')}
            <div id="sim-out" class="stack">${simulate(m, owed)}</div>
            <button class="btn" type="button" data-action="save-sim">Save as a monthly plan</button>
          </div>
        </section>
        <section class="section span-12">
          <div class="section-head"><h2>Rate periods</h2><button class="btn sm" type="button" data-action="soon" data-msg="Rate period editor opens here">Edit rates</button></div>
          <div class="timeline" role="img" aria-label="Rate periods from 2019 to 2049">
            <div class="tl-past" style="flex:${span(p0.start, p0.end)}"></div><div class="tl-now" style="flex:${span(p1.start, p1.end)}"></div><div class="tl-future" style="flex:${total - span(p0.start, p1.end)}"></div>
          </div>
          <div class="tl-key" style="margin-top:10px">
            <span><span class="swatch" style="background:var(--rule)"></span>${fmt.pct(p0.rate, 2)} ${p0.label} · ${fmt.monthYear(p0.start)} to ${fmt.monthYear(p0.end)}</span>
            <span><span class="swatch" style="background:var(--accent)"></span>${fmt.pct(p1.rate, 2)} ${p1.label} · ${fmt.monthYear(p1.start)} to ${fmt.monthYear(p1.end)} · now</span>
            <span><span class="swatch" style="box-shadow:inset 0 0 0 1px var(--axis)"></span>${fmt.pct(m.loan.fallback, 2)} assumed after the fix · you can change this</span>
          </div>
        </section>
        <section class="section span-12">
          <div class="section-head"><h2>Payment schedule</h2><span class="caption">Select a year to see each payment</span></div>
          <div class="table-wrap"><table class="ledger">
            <thead><tr><th>Year</th><th class="r">Payments</th><th class="r">Interest</th><th class="r">Principal</th><th class="r">Overpaid</th><th class="r">Balance at end</th></tr></thead>
            <tbody>${schedule}</tbody>
          </table></div>
          ${state.allYears ? '' : `<button class="link-btn" type="button" data-action="all-years" style="margin-top:12px">Show all ${Object.keys(years).length} years</button>`}
        </section>
      </div>`,
      mount() {
        const dates = [];
        for (let dt = N.d(2019, 7, 1); dt <= m.loan.maturity; dt = N.addMonths(dt, 3)) dates.push(dt);
        const todayIdx = dates.findIndex((dt) => dt > N.TODAY) - 1;
        const hist = N.schedule(m.loan, m.loan.original, m.loan.start, null, m.asOf);
        const fit = m.balance / N.balanceOn(hist, m.asOf, m.loan.original);
        const bal = dates.map((dt) => (dt <= N.TODAY ? N.balanceOn(hist, dt, m.loan.original) * (1 - (1 - fit) * N.yearsBetween(m.loan.start, dt) / N.yearsBetween(m.loan.start, m.asOf)) : N.balanceOn(rows, dt, owed)));
        const val = dates.map((dt) => (dt <= home.anchorDate ? home.purchase.price * Math.pow(home.anchor / home.purchase.price, N.yearsBetween(home.purchase.date, dt) / N.yearsBetween(home.purchase.date, home.anchorDate)) : N.modelValue(home, dt)));
        C.timeChart($('#prop-chart'), {
          dates, height: 270, label: 'Home value, mortgage balance and equity', dashFrom: todayIdx, todayIndex: todayIdx,
          series: [{ label: 'Home value', color: 'var(--s4)', values: val }, { label: 'Mortgage owed', color: 'var(--s5)', values: bal }],
          total: { label: 'Equity', values: val.map((v, i) => v - bal[i]) },
          fmtY: fmt.axis, fmtX: (dt) => String(dt.getUTCFullYear()), fmtTip: (v) => fmt.gbp(v), fmtTipDate: fmt.monthYear,
        });
        const update = () => {
          state.sim.extra = +$('#sim-extra').value;
          state.sim.lump = Math.max(0, +$('#sim-lump').value || 0);
          $('#sim-extra-label').innerHTML = fmt.gbp(state.sim.extra);
          $('#sim-out').innerHTML = simulate(m, owed);
        };
        $('#sim-extra').addEventListener('input', update);
        $('#sim-lump').addEventListener('input', update);
      },
    };
  }
  actions['toggle-year'] = (el) => { state.openYears[el.dataset.year] = !state.openYears[el.dataset.year]; refresh(); };
  actions['all-years'] = () => { state.allYears = true; refresh(); };
  actions['save-sim'] = () => toast(`Saved: extra ${plain(fmt.gbp(state.sim.extra))} a month from 1 Oct 2026`);
  actions.soon = (el) => toast(el.dataset.msg);

  /* ---------- other assets ---------- */
  function otherPage() {
    const assets = N.accounts.filter((a) => a.cat === 'other_asset');
    const debts = N.accounts.filter((a) => a.cat === 'loan' || a.cat === 'credit_card');
    const card = (a) => {
      const v = N.valuation(a);
      const pts = [];
      for (let dt = a.anchorDate; dt <= N.addMonths(N.TODAY, 60); dt = N.addMonths(dt, 3)) pts.push(dt);
      const k = pts.findIndex((dt) => dt > N.TODAY) - 1;
      const five = N.modelValue(a, N.addMonths(N.TODAY, 60));
      return `<div class="card" style="cursor:default">
        <div class="card-top"><div class="who"><span class="icon-tile">${ICON[a.kind] || ICON.gem}</span><div><b>${esc(a.name)}</b><div class="caption">${esc(a.provider)}</div></div></div>${helpers.owners(a)}</div>
        <div class="card-top"><span class="figure figure-md">${fmt.gbp(v.value)}</span>${C.sparkline(pts.map((dt) => N.modelValue(a, dt)), { w: 120, h: 36, dashFrom: Math.max(k, 0) })}</div>
        <div class="card-foot"><span class="tag">${a.rate < 0 ? '▼' : '▲'} ${fmt.pct(Math.abs(a.rate))} a year</span><span class="caption">In 5 years about ${fmt.gbp(five)}</span></div>
        <div class="caption">Valued ${fmt.gbp(a.anchor)} on ${fmt.date(a.anchorDate)} · compound${a.floor ? ` · never below ${fmt.gbp(a.floor)}` : ''}</div>
      </div>`;
    };
    const debtCard = (a) => {
      const v = N.valuation(a);
      let detail = helpers.status(v);
      if (a.method === 'amortising') {
        const rows = N.schedule(a.loan, -v.value, N.TODAY, null);
        detail = `<span class="caption">${fmt.pct(a.loan.fallback, 1)} APR · ${fmt.gbp(rows[0].payment, { dp: 2 })} a month · paid off ${fmt.monthYear(N.summarise(rows).payoff)}</span>`;
      }
      return `<div class="card" style="cursor:default"><div class="card-top"><div class="who"><span class="icon-tile">${a.cat === 'loan' ? ICON.loan : ICON.card}</span><div><b>${esc(a.name)}</b><div class="caption">${esc(a.provider)}</div></div></div>${helpers.owners(a)}</div><span class="figure figure-md">${fmt.gbp(v.value)}</span>${detail}</div>`;
    };
    return {
      title: 'Other assets',
      html: `
      <section class="section"><div class="section-head"><h2>Assets that gain or lose value</h2><button class="btn sm primary" type="button" data-action="add-asset">${ICON.plus}Add asset</button></div>
        <div class="cards">${assets.map(card).join('')}</div>
      </section>
      <section class="section"><div class="section-head"><h2>Loans and cards</h2><span class="caption">${fmt.gbp(debts.reduce((s, a) => s + N.valuation(a).value, 0))} in total</span></div>
        <div class="cards">${debts.map(debtCard).join('')}</div>
      </section>
      <p class="footer-note">Each asset grows or shrinks from its last valuation at its own yearly rate. Enter a new valuation any time and the model restarts from it.</p>`,
    };
  }

  actions['add-asset'] = () => {
    openOverlay('dialog', `
      <h2 id="dialog-title">Add an asset</h2>
      <div class="form-grid">
        <div class="field full"><label for="as-name">Name</label><input class="input" id="as-name" value="Engagement ring"></div>
        <div class="field"><label for="as-kind">Type</label><select class="input" id="as-kind"><option value="gem">Jewellery</option><option value="car">Vehicle</option><option value="watch">Watch</option><option value="gem">Art or collectible</option></select></div>
        <div class="field"><label for="as-owner">Owner</label><select class="input" id="as-owner"><option value="you">You</option><option value="partner">Partner</option><option value="joint">Joint 50/50</option></select></div>
        <div class="field"><label for="as-value">Value</label><div class="affix"><span class="pre">£</span><input class="input has-pre" id="as-value" type="number" value="3500"></div></div>
        <div class="field"><label for="as-date">Valued on</label><input class="input" id="as-date" type="date" value="2026-09-15"></div>
        <div class="field"><label for="as-dir">Direction</label><select class="input" id="as-dir"><option value="1">Gains value</option><option value="-1">Loses value</option></select></div>
        <div class="field"><label for="as-rate">Rate per year</label><div class="affix"><input class="input has-post" id="as-rate" type="number" step="0.5" value="2"><span class="post">%</span></div></div>
      </div>
      <div class="banner" style="background:var(--accent-soft);border-color:var(--border)"><span id="as-preview"></span></div>
      <div class="dialog-actions"><button class="btn" type="button" data-action="close-overlays">Cancel</button><button class="btn primary" type="button" data-action="save-asset">Add asset</button></div>`);
    const preview = () => {
      const v = +$('#as-value').value || 0, r = (+$('#as-rate').value || 0) / 100 * +$('#as-dir').value;
      $('#as-preview').innerHTML = `In 5 years about <b>${fmt.gbp(v * N.growth(r, 5))}</b>, in 10 years about <b>${fmt.gbp(v * N.growth(r, 10))}</b>`;
    };
    $('#dialog').addEventListener('input', preview);
    preview();
  };
  actions['save-asset'] = () => {
    const owner = $('#as-owner').value;
    const [y, mo, da] = $('#as-date').value.split('-').map(Number);
    N.accounts.push({
      id: 'asset-' + Date.now(), name: $('#as-name').value || 'New asset', provider: 'Added today', cat: 'other_asset', kind: $('#as-kind').value, method: 'model',
      owners: owner === 'joint' ? { you: 0.5, partner: 0.5 } : { [owner]: 1 }, anchor: +$('#as-value').value || 0, anchorDate: N.d(y || 2026, mo || 9, da || 15),
      rate: ((+$('#as-rate').value || 0) / 100) * +$('#as-dir').value,
    });
    closeOverlays();
    toast('Asset added · net worth updated');
    refresh();
  };

  /* ---------- projections ---------- */
  function projectionsPage() {
    const pr = state.proj;
    const adj = { pessimistic: -0.02, base: 0, optimistic: 0.02 }[pr.scenario];
    const months = pr.years * 12;
    const p = helpers.projection(adj, months, pr.real);
    const scope = pr.scope;
    const ratio = {};
    const hh = N.totals('household'), mine = scope === 'household' ? hh : N.totals(scope);
    N.GROUPS.forEach((g) => (ratio[g.key] = hh.byGroup[g.key] ? mine.byGroup[g.key] / hh.byGroup[g.key] : 0));
    const groupVals = (g) => p.byGroup[g].map((v) => v * ratio[g]);
    const total = scope === 'household' ? p.total : p.byPerson[scope];
    const byPerson = scope === 'household' && pr.view === 'person';

    const idxOf = (dt) => { const i = p.dates.findIndex((x) => x >= dt); return i < 0 ? null : i; };
    const mf = N.summarise(p.loanRows.mortgage).payoff;
    const marks = [
      { dt: N.d(2029, 5, 31), label: 'Fix ends' },
      { dt: mf, label: 'Mortgage-free' },
      { dt: N.firstReaching(p.dates, total, 1000000), label: scope === 'household' ? '£1m' : null },
      { dt: N.birthday(N.people[0], 57), label: 'Your pension opens' },
      { dt: N.birthday(N.people[1], 57), label: 'Partner’s pension opens' },
    ].filter((x) => x.dt && x.label && idxOf(x.dt) !== null && (scope === 'household' || !x.label.includes(scope === 'you' ? 'Partner' : 'Your')));

    const rowsAt = [1, 5, 10, 20, 30, 40].filter((y) => y <= pr.years).map((y) => {
      const i = y * 12, dt = p.dates[i];
      const ages = N.people.map((q) => Math.floor(N.yearsBetween(q.dob, dt)));
      return `<tr><td>${y} ${y === 1 ? 'year' : 'years'}<span class="sub mono">${fmt.monthYear(dt)}</span></td><td class="r">${ages.join(' / ')}</td>
        <td class="r">${fmt.gbp(groupVals('investment')[i], { compact: true })}</td><td class="r">${fmt.gbp(groupVals('pension')[i], { compact: true })}</td><td class="r">${fmt.gbp(groupVals('cash')[i], { compact: true })}</td>
        <td class="r">${fmt.gbp(groupVals('property')[i] + p.loanRows.mortgage ? groupVals('property')[i] - N.balanceOn(p.loanRows.mortgage, dt, 0) * (scope === 'household' ? 1 : 0.5) * (pr.real ? 1 / Math.pow(1.025, N.yearsBetween(N.TODAY, dt)) : 1) : 0, { compact: true })}</td>
        <td class="r"><b>${fmt.gbp(total[i], { compact: true })}</b></td></tr>`;
    }).join('');

    return {
      title: 'Projections',
      html: `
      <div class="filter-row">
        ${helpers.seg('proj.scope', [['household', 'Household'], ['you', 'You'], ['partner', 'Partner']], scope, 'Whose projection')}
        ${helpers.seg('proj.scenario', [['pessimistic', 'Pessimistic'], ['base', 'Base'], ['optimistic', 'Optimistic']], pr.scenario, 'Scenario')}
        ${helpers.seg('proj.real', [['false', 'Future pounds'], ['true', 'Today’s money']], pr.real, 'Money terms')}
        ${scope === 'household' ? helpers.seg('proj.view', [['category', 'By category'], ['person', 'By person']], pr.view, 'Split') : ''}
        <label class="field" for="proj-years" style="min-width:220px;flex:1;max-width:340px"><span class="label">Horizon: <b id="proj-years-label">${pr.years} years</b> · to ${fmt.monthYear(p.dates[months])}</span><input type="range" id="proj-years" min="5" max="40" step="1" value="${pr.years}"></label>
      </div>
      <div class="grid">
        <section class="panel span-12">
          <div class="hero-top"><div class="hero-figure"><span class="eyebrow">Projected net worth in ${pr.years} years · ${pr.scenario} scenario${pr.real ? ' · today’s money' : ''}</span><span class="figure figure-xl">${fmt.hero(total[months])}</span></div>
          <span class="caption">Investments and pensions ${fmt.pct(0.06 + adj, 0)} a year before fees · home 3% · inflation 2.5%</span></div>
          <div class="chart" id="proj-chart" style="margin-top:12px"></div>
        </section>
        <section class="section span-8">
          <div class="section-head"><h2>Checkpoints</h2><span class="caption">Ages shown as You / Partner</span></div>
          <div class="table-wrap"><table class="ledger"><thead><tr><th>When</th><th class="r">Ages</th><th class="r">Investments</th><th class="r">Pensions</th><th class="r">Cash</th><th class="r">Home equity</th><th class="r">Net worth</th></tr></thead><tbody>${rowsAt}</tbody></table></div>
        </section>
        <section class="section span-4">
          <div class="section-head"><h2>Scenarios compared</h2><span class="caption">Same plans, different returns</span></div>
          <div class="chart" id="scen-chart"></div>
        </section>
      </div>
      <p class="footer-note">Projections illustrate your own assumptions. They are not predictions or financial advice. Contributions stop at each person’s retirement age of 67; the Lifetime ISA stops at 50.</p>`,
      mount() {
        const markers = marks.map((x) => ({ index: idxOf(x.dt), label: x.label }));
        const common = { dates: p.dates, height: 300, markers, label: 'Projected net worth', fmtY: fmt.axis, fmtX: (dt) => String(dt.getUTCFullYear()), fmtTip: (v) => fmt.gbp(v), fmtTipDate: fmt.monthYear };
        if (byPerson) {
          C.timeChart($('#proj-chart'), { ...common, stacked: true, series: N.people.map((q, i) => ({ label: q.name, color: `var(--s${i + 1})`, values: p.byPerson[q.id] })), total: { label: 'Household', values: total } });
        } else {
          C.timeChart($('#proj-chart'), { ...common, stacked: true, series: N.GROUPS.map((g) => ({ label: g.label, color: g.color, values: groupVals(g.key) })), total: { label: 'Net worth', values: total } });
        }
        const pick = (a) => { const q = helpers.projection(a, months, pr.real); return scope === 'household' ? q.total : q.byPerson[scope]; };
        const series = [['Pessimistic', -0.02], ['Base', 0], ['Optimistic', 0.02]].map(([label, a], i) => ({ label, color: `var(--s${i + 1})`, values: pick(a) }));
        helpers.projection(adj, months, pr.real);
        C.timeChart($('#scen-chart'), { dates: p.dates, height: 230, series, label: 'Scenario comparison', fmtY: fmt.axis, fmtX: (dt) => String(dt.getUTCFullYear()), xTicks: 3, fmtTip: (v) => fmt.gbp(v, { compact: true }), fmtTipDate: fmt.monthYear });
        const slider = $('#proj-years');
        slider.addEventListener('input', () => { $('#proj-years-label').textContent = slider.value + ' years'; });
        slider.addEventListener('change', () => { state.proj.years = +slider.value; refresh(); });
      },
    };
  }

  /* ---------- import ---------- */
  function importPage() {
    const steps = ['Upload a CSV export', 'Match its columns', 'Match funds and shares', 'Check against today’s holdings', 'Import', 'Rebuild history'];
    return {
      title: 'Import history',
      html: `
      <section class="panel" style="max-width:920px">
        <div class="section-head"><h2>Bring in past transactions</h2><span class="tag">Phase 8</span></div>
        <ol class="tl-key" style="padding-left:18px;display:grid;gap:6px;margin:12px 0 18px">${steps.map((s, i) => `<li${i === 3 ? ' style="font-weight:600;color:var(--ink)"' : ''}>${s}</li>`).join('')}</ol>
        <div class="banner" style="background:var(--accent-soft);border-color:var(--border)"><span><b>trading212-history-2021-2026.csv</b> · 412 rows · Trading 212 Stocks &amp; Shares ISA</span></div>
        <div class="section-head" style="margin-top:18px"><h2>Check against today’s holdings</h2><span class="caption">Differences usually mean part of the history is missing</span></div>
        <div class="table-wrap"><table class="ledger"><thead><tr><th>Instrument</th><th class="r">Units now</th><th class="r">Units from history</th><th class="r">Difference</th><th>Result</th></tr></thead><tbody>
          <tr><td class="mono">VWRP.L</td><td class="r">210</td><td class="r">210</td><td class="r">0</td><td><span class="status ok">${ICON.ok}Matches</span></td></tr>
          <tr><td class="mono">VUAG.L</td><td class="r">115</td><td class="r">115</td><td class="r">0</td><td><span class="status ok">${ICON.ok}Matches</span></td></tr>
          <tr><td class="mono">SGLN.L</td><td class="r">160</td><td class="r">158.5</td><td class="r">−1.5</td><td><span class="status warn">${ICON.warn}1.5 units unexplained</span></td></tr>
          <tr><td class="mono">ISF.L</td><td class="r">520</td><td class="r">520</td><td class="r">0</td><td><span class="status ok">${ICON.ok}Matches</span></td></tr>
        </tbody></table></div>
        <div class="dialog-actions" style="justify-content:flex-start;margin-top:16px;flex-wrap:wrap">
          <button class="btn primary" type="button" data-action="soon" data-msg="Imported 412 transactions · rebuilding history from April 2021">Import and keep today’s units</button>
          <button class="btn" type="button" data-action="soon" data-msg="Imported exactly as the file says">Import exactly as the file says</button>
        </div>
      </section>`,
    };
  }

  /* ---------- settings ---------- */
  function settingsPage() {
    return {
      title: 'Settings',
      html: `
      <div class="grid">
        <section class="section span-6"><div class="section-head"><h2>People</h2><button class="btn sm" type="button" data-action="soon" data-msg="Add a person, for example a child with a Junior ISA">${ICON.plus}Add person</button></div>
          <div class="table-wrap"><table class="ledger"><thead><tr><th>Name</th><th>Born</th><th class="r">Retires at</th><th>In household total</th></tr></thead><tbody>
          ${N.people.map((q) => `<tr><td><span class="avatar">${q.initial}</span> ${q.name}</td><td class="mono">${fmt.date(q.dob)}</td><td class="r">${q.retire}</td><td>Yes</td></tr>`).join('')}
          </tbody></table></div></section>
        <section class="section span-6"><div class="section-head"><h2>Assumptions</h2><span class="caption">Used by projections</span></div>
          <div class="form-grid" style="margin-top:12px">
            ${[['Inflation', 2.5], ['Shares', 6], ['Bonds', 3.5], ['Cash savings', 3.5], ['Home', 3], ['Mortgage rate after fixes', 4.75]].map(([l, v], i) => `<div class="field"><label for="as-${i}">${l}</label><div class="affix"><input class="input has-post" id="as-${i}" type="number" step="0.25" value="${v}"><span class="post">%</span></div></div>`).join('')}
          </div></section>
        <section class="section span-6"><div class="section-head"><h2>Tax-year allowances</h2><span class="caption">Stored as data, check each April</span></div>
          <div class="table-wrap"><table class="ledger"><thead><tr><th>Tax year</th><th class="r">ISA</th><th class="r">Lifetime ISA</th><th class="r">Junior ISA</th><th class="r">Pension</th></tr></thead><tbody>
            <tr><td class="mono">2026/27</td><td class="r">£20,000</td><td class="r">£4,000</td><td class="r">£9,000</td><td class="r">£60,000</td></tr>
            <tr><td class="mono">2025/26</td><td class="r">£20,000</td><td class="r">£4,000</td><td class="r">£9,000</td><td class="r">£60,000</td></tr>
          </tbody></table></div></section>
        <section class="section span-6"><div class="section-head"><h2>Your data</h2><span class="caption mono">data\\networth.db</span></div>
          <div class="list-row"><span class="status ok">${ICON.ok}</span><span>Backed up last night at 22:30<span class="caption"> · keeping 30 copies</span></span><button class="btn sm" type="button" data-action="soon" data-msg="Backup saved">Back up now</button></div>
          <div class="list-row"><span class="status ok">${ICON.ok}</span><span>Prices refresh every 15 minutes while markets are open</span><span></span></div>
          <div class="list-row"><span class="status ok">${ICON.ok}</span><span>Everything stays on this computer</span><button class="btn sm" type="button" data-action="soon" data-msg="Export saved as waymark-export.json">Export JSON</button></div>
        </section>
      </div>`,
    };
  }

  /* ---------- quick update ---------- */
  actions['quick-update'] = () => {
    const groups = [['you', 'You'], ['partner', 'Partner'], ['joint', 'Shared']];
    const rows = (key) => N.accounts.filter((a) => a.method !== 'holdings' && (key === 'joint' ? Object.keys(a.owners).length > 1 : Object.keys(a.owners).length === 1 && a.owners[key])).map((a) => {
      const v = N.valuation(a);
      const last = a.method === 'model' ? a.anchor : a.balance;
      return `<div class="qu-row"><div><b>${esc(a.provider)}</b> <span class="ink2">${esc(a.name)}</span><div class="caption">Last ${fmt.gbp(last)} on ${fmt.date(v.updated)}${a.method !== 'balance' ? ` · now about ${fmt.gbp(Math.abs(v.value))}` : ''}</div>${v.staleness !== 'ok' ? helpers.status(v) : ''}</div>
        <div class="affix"><span class="pre">£</span><input class="input has-pre" id="qu-${a.id}" data-qu="${a.id}" type="number" step="0.01" inputmode="decimal" aria-label="New value for ${esc(a.provider)} ${esc(a.name)}"></div></div>`;
    }).join('');
    openOverlay('sheet', `
      <div class="sheet-head"><div><h2 class="figure figure-md" style="margin:0">Quick update</h2><div class="caption">Type today’s figures, leave the rest blank</div></div><button class="icon-btn" type="button" data-action="close-overlays" aria-label="Close">✕</button></div>
      <div class="sheet-body">${groups.map(([k, l]) => `<div class="eyebrow" style="margin-top:18px">${l}</div>${rows(k)}`).join('')}</div>
      <div class="sheet-foot"><span class="caption" id="qu-count">No changes yet</span><button class="btn primary" type="button" data-action="save-quick">Save updates</button></div>`);
    $('#sheet').addEventListener('input', () => {
      const n = [...document.querySelectorAll('[data-qu]')].filter((i) => i.value !== '').length;
      $('#qu-count').textContent = n ? `${n} ${n === 1 ? 'figure' : 'figures'} ready to save` : 'No changes yet';
    });
  };
  actions['save-quick'] = () => {
    let n = 0;
    document.querySelectorAll('[data-qu]').forEach((i) => {
      if (i.value === '' || isNaN(+i.value)) return;
      const a = byId(i.dataset.qu);
      if (a.method === 'model') { a.anchor = +i.value; a.anchorDate = N.TODAY; } else { a.balance = +i.value; a.asOf = N.TODAY; }
      n++;
    });
    closeOverlays();
    toast(n ? `Saved ${n} ${n === 1 ? 'update' : 'updates'} · net worth recalculated` : 'Nothing to save');
    refresh();
  };

  /* ---------- pending purchases ---------- */
  actions['toggle-pending'] = (el) => {
    const pop = $('#pending-pop');
    if (!pop.hidden) { pop.hidden = true; el.setAttribute('aria-expanded', 'false'); return; }
    const tx = (N.transactions['isa-you'] || []).filter((t) => t.status === 'pending');
    pop.innerHTML = tx.length
      ? `<div class="section-head" style="margin:0"><h2>Waiting for you</h2><span class="caption">Monthly ISA · ${fmt.date(N.TODAY)}</span></div>
        ${tx.map((t) => `<div class="list-row"><span class="tag pending">${t.type}</span><span>${t.sym ? `<span class="mono">${N.instruments[t.sym].symbol}</span> · ${fmt.units(t.units)} units` : 'Cash in'}</span><span class="num">${fmt.gbp(t.amount, { dp: 2, sign: true })}</span></div>`).join('')}
        <div class="dialog-actions"><a class="btn sm" href="#/accounts/isa-you">Edit first</a><button class="btn sm primary" type="button" data-action="confirm-pending">Confirm all</button></div>`
      : `<p class="caption" style="margin:0">Nothing waiting. Regular purchases appear here on the day they are due.</p>`;
    pop.hidden = false;
    el.setAttribute('aria-expanded', 'true');
  };

  /* ---------- add holding / plan ---------- */
  const SEARCH = [
    { key: 'VUSA', symbol: 'VUSA.L', name: 'Vanguard S&P 500 UCITS ETF (Dist)', exch: 'London', ccy: 'GBp', price: 89.12, cls: 'Equity' },
    { key: 'IITU', symbol: 'IITU.L', name: 'iShares S&P 500 Information Technology Sector UCITS ETF', exch: 'London', ccy: 'GBp', price: 28.44, cls: 'Equity' },
    { key: 'FIDW', symbol: '0P0001CZMQ.L', name: 'Fidelity Index World Fund P Acc', exch: 'Fund', ccy: 'GBP', price: 3.214, cls: 'Equity' },
    { key: 'SSLN', symbol: 'SSLN.L', name: 'iShares Physical Silver ETC', exch: 'London', ccy: 'GBp', price: 27.9, cls: 'Commodity' },
  ];
  actions['add-holding'] = (el) => {
    const id = el.dataset.id;
    openOverlay('dialog', `
      <h2 id="dialog-title">Add a holding</h2>
      <div class="field"><label for="ah-q">Search by name, ticker or ISIN</label><input class="input" id="ah-q" value="S&amp;P 500" autocomplete="off"></div>
      <div id="ah-results" role="radiogroup" aria-label="Search results"></div>
      <div class="form-grid">
        <div class="field"><label for="ah-units">Units you hold</label><input class="input" id="ah-units" type="number" step="any" value="25"></div>
        <div class="field"><label for="ah-avg">Average cost per unit</label><div class="affix"><span class="pre">£</span><input class="input has-pre" id="ah-avg" type="number" step="any" value="80.00"></div></div>
      </div>
      <p class="caption" style="margin:0">Saved as an opening balance dated today. Prices quoted in pence are converted to pounds automatically.</p>
      <div class="dialog-actions"><button class="btn" type="button" data-action="close-overlays">Cancel</button><button class="btn primary" type="button" data-action="save-holding" data-id="${id}">Add holding</button></div>`);
    const draw = () => {
      const q = $('#ah-q').value.toLowerCase();
      const hits = SEARCH.filter((s) => (s.symbol + s.name).toLowerCase().includes(q) || !q);
      $('#ah-results').innerHTML = hits.map((s, i) => `<label class="list-row" style="cursor:pointer" for="ah-${s.key}"><input type="radio" name="ah-pick" id="ah-${s.key}" value="${s.key}"${i === 0 ? ' checked' : ''}><span><span class="tag mono">${s.symbol}</span> ${esc(s.name)}<span class="caption"> · ${s.exch} · ${s.ccy === 'GBp' ? 'quoted in pence' : 'quoted in pounds'}</span></span><span class="num">${fmt.price(s.price)}</span></label>`).join('') || '<p class="caption">No matches. Try the ISIN, or add a manual price instead.</p>';
    };
    $('#ah-q').addEventListener('input', draw);
    draw();
  };
  actions['save-holding'] = (el) => {
    const pick = document.querySelector('input[name="ah-pick"]:checked');
    if (!pick) { toast('Choose an instrument from the results first'); return; }
    const s = SEARCH.find((x) => x.key === pick.value);
    N.instruments[s.key] = { symbol: s.symbol, name: s.name, cls: s.cls, ccy: s.ccy, price: s.price, dayPct: 0.001 };
    const a = byId(el.dataset.id);
    const existing = a.holdings.find((h) => h.i === s.key);
    if (existing) existing.units += +$('#ah-units').value || 0;
    else a.holdings.push({ i: s.key, units: +$('#ah-units').value || 0, avg: +$('#ah-avg').value || 0 });
    closeOverlays();
    toast(`${s.symbol} added as an opening balance`);
    refresh();
  };
  actions['add-plan'] = () => toast('The plan form opens here: amount, schedule, split across funds, tax relief');

  /* ---------- command palette ---------- */
  actions.palette = () => {
    const items = [
      ['Go to Overview', '#/overview', 'Page'], ['Go to You', '#/people/you', 'Person'], ['Go to Partner', '#/people/partner', 'Person'],
      ['Go to Property & mortgage', '#/property', 'Page'], ['Go to Other assets', '#/other', 'Page'], ['Go to Projections', '#/projections', 'Page'],
      ['Go to Import history', '#/import', 'Page'], ['Go to Settings', '#/settings', 'Page'],
      ...N.accounts.filter((a) => a.method === 'holdings' || ['cash', 'pension', 'investment'].includes(a.cat)).map((a) => [`${a.provider} ${a.name}`, helpers.hrefFor(a), 'Account']),
      ['Quick update', 'quick-update', 'Action'], ['Refresh prices', 'refresh-prices', 'Action'], ['Hide or show figures', 'toggle-privacy', 'Action'], ['Switch theme', 'toggle-theme', 'Action'],
    ];
    openOverlay('palette', `<input id="pal-q" placeholder="Search pages, accounts and actions" autocomplete="off" aria-label="Search"><ul id="pal-list" role="listbox"></ul>`);
    let sel = 0, shown = items;
    const run = (it) => {
      closeOverlays();
      if (it[1].startsWith('#')) go(it[1]);
      else actions[it[1]](it[1] === 'refresh-prices' ? $('#refresh-btn') : document.body);
    };
    const draw = () => {
      const q = $('#pal-q').value.toLowerCase();
      shown = items.filter((it) => it[0].toLowerCase().includes(q));
      sel = Math.min(sel, Math.max(shown.length - 1, 0));
      $('#pal-list').innerHTML = shown.map((it, i) => `<li><button type="button" role="option" data-i="${i}" aria-selected="${i === sel}">${esc(it[0])}<span class="muted">${it[2]}</span></button></li>`).join('') || '<li class="caption" style="padding:12px">No matches</li>';
      $('#pal-list').querySelectorAll('button').forEach((b) => b.addEventListener('click', () => run(shown[+b.dataset.i])));
    };
    $('#pal-q').addEventListener('input', () => { sel = 0; draw(); });
    $('#pal-q').addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(0, Math.min(shown.length - 1, sel + (e.key === 'ArrowDown' ? 1 : -1))); draw(); }
      if (e.key === 'Enter' && shown[sel]) run(shown[sel]);
    });
    draw();
  };

  route(/^\/property$/, propertyPage);
  route(/^\/other$/, otherPage);
  route(/^\/projections$/, projectionsPage);
  route(/^\/import$/, importPage);
  route(/^\/settings$/, settingsPage);

  window.App.start();
})();

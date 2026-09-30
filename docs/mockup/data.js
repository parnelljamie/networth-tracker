/* Sample household for the clickable mockup. Every figure is illustrative.
   The maths mirrors backend/app/engine (amortisation, growth, recurring dates, projection). */
(function () {
  'use strict';

  const DAY = 86400000;
  const d = (y, m, day) => new Date(Date.UTC(y, m - 1, day));
  const TODAY = d(2026, 9, 15);
  const daysInMonth = (y, m0) => new Date(Date.UTC(y, m0 + 1, 0)).getUTCDate();
  const clampDay = (y, m0, day) => new Date(Date.UTC(y, m0, Math.min(day, daysInMonth(y, m0))));
  function addMonths(dt, n) {
    const m = dt.getUTCMonth() + n;
    return clampDay(dt.getUTCFullYear() + Math.floor(m / 12), ((m % 12) + 12) % 12, dt.getUTCDate());
  }
  const monthEnd = (dt) => clampDay(dt.getUTCFullYear(), dt.getUTCMonth(), 31);
  const addDays = (dt, n) => new Date(dt.getTime() + n * DAY);
  const yearsBetween = (a, b) => (b - a) / DAY / 365.25;
  const monthsBetween = (a, b) => (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + b.getUTCMonth() - a.getUTCMonth();
  const growth = (rate, years) => (years <= 0 ? 1 : 1 + rate <= 0 ? 0 : Math.pow(1 + rate, years));
  const firstOfMonth = (dt) => d(dt.getUTCFullYear(), dt.getUTCMonth() + 1, 1);

  /* ---------- people ---------- */
  const people = [
    { id: 'you', name: 'You', initial: 'Y', dob: d(1991, 3, 12), retire: 67 },
    { id: 'partner', name: 'Partner', initial: 'P', dob: d(1993, 7, 2), retire: 67 },
  ];
  const personById = Object.fromEntries(people.map((p) => [p.id, p]));
  const birthday = (p, age) => d(p.dob.getUTCFullYear() + age, p.dob.getUTCMonth() + 1, p.dob.getUTCDate());

  /* ---------- instruments (price in GBP; quoted currency kept for display) ---------- */
  const instruments = {
    VWRP: { symbol: 'VWRP.L', name: 'Vanguard FTSE All-World UCITS ETF (Acc)', cls: 'Equity', ccy: 'GBp', price: 118.42, dayPct: 0.0042 },
    VUAG: { symbol: 'VUAG.L', name: 'Vanguard S&P 500 UCITS ETF (Acc)', cls: 'Equity', ccy: 'GBp', price: 96.31, dayPct: 0.0061 },
    SGLN: { symbol: 'SGLN.L', name: 'iShares Physical Gold ETC', cls: 'Commodity', ccy: 'GBp', price: 46.85, dayPct: -0.0035 },
    ISF: { symbol: 'ISF.L', name: 'iShares Core FTSE 100 UCITS ETF', cls: 'Equity', ccy: 'GBp', price: 9.036, dayPct: 0.0018 },
    VHVG: { symbol: 'VHVG.L', name: 'Vanguard FTSE Developed World UCITS ETF (Acc)', cls: 'Equity', ccy: 'GBp', price: 92.4, dayPct: 0.0039 },
    VFEG: { symbol: 'VFEG.L', name: 'Vanguard FTSE Emerging Markets UCITS ETF (Acc)', cls: 'Equity', ccy: 'GBp', price: 53.72, dayPct: -0.0012 },
    LS80: { symbol: '0P0000TKZK.L', name: 'Vanguard LifeStrategy 80% Equity Fund (Acc)', cls: 'Multi-asset', ccy: 'GBP', price: 282.14, dayPct: 0.0024 },
    AAPL: { symbol: 'AAPL', name: 'Apple Inc.', cls: 'Equity', ccy: 'USD', priceUsd: 238.1, fx: 0.7431, price: 176.93, dayPct: 0.0087 },
  };

  /* ---------- accounts ---------- */
  const accounts = [
    { id: 'isa-you', name: 'Stocks & Shares ISA', provider: 'Trading 212', cat: 'investment', wrapper: 'ISA', method: 'holdings', owners: { you: 1 }, fee: 0.0012, cash: 71.98,
      holdings: [{ i: 'VWRP', units: 210, avg: 101.3 }, { i: 'VUAG', units: 115, avg: 82.1 }, { i: 'SGLN', units: 160, avg: 38.2 }, { i: 'ISF', units: 520, avg: 7.95 }] },
    { id: 'isa-partner', name: 'Stocks & Shares ISA', provider: 'Vanguard Investor', cat: 'investment', wrapper: 'ISA', method: 'holdings', owners: { partner: 1 }, fee: 0.0015, cash: 0,
      holdings: [{ i: 'VHVG', units: 290, avg: 78.8 }, { i: 'VFEG', units: 95, avg: 49.1 }] },
    { id: 'lisa-partner', name: 'Lifetime ISA', provider: 'Moneybox', cat: 'investment', wrapper: 'LISA', method: 'balance', owners: { partner: 1 }, balance: 14800, asOf: d(2026, 9, 1), fee: 0.0045 },
    { id: 'wp-you', name: 'Workplace pension', provider: 'Aviva', cat: 'pension', wrapper: 'Workplace', method: 'balance', owners: { you: 1 }, balance: 86400, asOf: d(2026, 8, 12), fee: 0.004 },
    { id: 'sipp-you', name: 'SIPP', provider: 'Vanguard', cat: 'pension', wrapper: 'SIPP', method: 'holdings', owners: { you: 1 }, fee: 0.0015, cash: 48.2,
      holdings: [{ i: 'LS80', units: 52.4, avg: 241.6 }, { i: 'VWRP', units: 48, avg: 104.9 }, { i: 'AAPL', units: 12, avg: 139.4 }] },
    { id: 'wp-partner', name: 'Workplace pension', provider: 'Nest', cat: 'pension', wrapper: 'Workplace', method: 'balance', owners: { partner: 1 }, balance: 54200, asOf: d(2026, 8, 5), fee: 0.003 },
    { id: 'monzo', name: 'Current account', provider: 'Monzo', cat: 'cash', method: 'balance', owners: { you: 1 }, balance: 2150, asOf: d(2026, 9, 14), rate: 0 },
    { id: 'saver', name: 'Easy access saver', provider: 'Chase', cat: 'cash', method: 'balance', owners: { you: 1 }, balance: 12400, asOf: d(2026, 9, 1), rate: 0.038 },
    { id: 'premium-bonds', name: 'Premium Bonds', provider: 'NS&I', cat: 'cash', method: 'balance', owners: { you: 1 }, balance: 5000, asOf: d(2026, 9, 2), rate: 0.036 },
    { id: 'starling', name: 'Current account', provider: 'Starling', cat: 'cash', method: 'balance', owners: { partner: 1 }, balance: 6300, asOf: d(2026, 9, 12), rate: 0.0325 },
    { id: 'joint', name: 'Joint account', provider: 'Nationwide', cat: 'cash', method: 'balance', owners: { you: 0.5, partner: 0.5 }, balance: 3200, asOf: d(2026, 9, 14), rate: 0 },
    { id: 'home', name: 'Home', provider: '14 Orchard Close', cat: 'property', method: 'model', owners: { you: 0.5, partner: 0.5 }, anchor: 458300, anchorDate: d(2026, 3, 1), rate: 0.03,
      purchase: { price: 325000, date: d(2019, 6, 14) } },
    { id: 'mortgage', name: 'Mortgage', provider: 'Nationwide', cat: 'mortgage', method: 'amortising', owners: { you: 0.5, partner: 0.5 }, balance: 215310.44, asOf: d(2026, 8, 1),
      loan: { maturity: d(2049, 6, 1), day: 1, effect: 'reduce_term', fallback: 0.0475, original: 260000, start: d(2019, 6, 14), allowance: 0.1, secures: 'home',
        periods: [
          { start: d(2019, 6, 14), end: d(2024, 5, 31), rate: 0.0189, label: '5-year fix' },
          { start: d(2024, 6, 1), end: d(2029, 5, 31), rate: 0.0419, label: '5-year fix' },
        ] } },
    { id: 'car-loan', name: 'Car loan', provider: 'Black Horse', cat: 'loan', method: 'amortising', owners: { partner: 1 }, balance: 6400, asOf: d(2026, 9, 1),
      loan: { maturity: d(2028, 6, 1), day: 1, effect: 'reduce_term', fallback: 0.079, periods: [] } },
    { id: 'credit-card', name: 'Credit card', provider: 'American Express', cat: 'credit_card', method: 'balance', owners: { you: 1 }, balance: 850, asOf: d(2026, 8, 8) },
    { id: 'car', name: 'Car', provider: '2022 Skoda Octavia Estate', cat: 'other_asset', kind: 'car', method: 'model', owners: { you: 1 }, anchor: 20100, anchorDate: d(2026, 2, 2), rate: -0.15, floor: 3000 },
    { id: 'watch', name: 'Watch', provider: 'Omega Seamaster', cat: 'other_asset', kind: 'watch', method: 'model', owners: { partner: 1 }, anchor: 4080, anchorDate: d(2025, 11, 20), rate: 0.03 },
  ];
  const accountById = () => Object.fromEntries(accounts.map((a) => [a.id, a]));

  /* ---------- recurring plans ---------- */
  const plans = [
    { id: 'p1', name: 'Monthly ISA', account: 'isa-you', owner: 'you', kind: 'contribution', amount: 500, gross: 500, freq: 'monthly', day: 15, start: d(2023, 4, 15), alloc: [['VWRP', 0.8], ['VUAG', 0.2]], auto: true },
    { id: 'p2', name: 'Workplace pension', account: 'wp-you', owner: 'you', kind: 'contribution', amount: 425, gross: 850, freq: 'monthly', day: 28, start: d(2021, 9, 28), split: { you: 425, employer: 425, relief: 0 } },
    { id: 'p3', name: 'SIPP top-up', account: 'sipp-you', owner: 'you', kind: 'contribution', amount: 400, gross: 500, freq: 'monthly', day: 5, start: d(2024, 1, 5), split: { you: 400, employer: 0, relief: 100 } },
    { id: 'p4', name: 'Savings', account: 'saver', owner: 'you', kind: 'contribution', amount: 300, gross: 300, freq: 'monthly', day: 2, start: d(2025, 1, 2) },
    { id: 'p5', name: 'Mortgage overpayment', account: 'mortgage', owner: 'joint', kind: 'overpayment', amount: 150, gross: 150, freq: 'monthly', day: 1, start: d(2025, 1, 1) },
    { id: 'p6', name: 'Monthly ISA', account: 'isa-partner', owner: 'partner', kind: 'contribution', amount: 300, gross: 300, freq: 'monthly', day: 1, start: d(2024, 5, 1), alloc: [['VHVG', 0.85], ['VFEG', 0.15]], auto: true },
    { id: 'p7', name: 'Lifetime ISA', account: 'lisa-partner', owner: 'partner', kind: 'contribution', amount: 4000, gross: 5000, freq: 'annually', day: 6, month: 4, start: d(2022, 4, 6), end: d(2043, 7, 1), split: { you: 4000, employer: 0, relief: 1000 } },
    { id: 'p8', name: 'Workplace pension', account: 'wp-partner', owner: 'partner', kind: 'contribution', amount: 310, gross: 620, freq: 'monthly', day: 25, start: d(2022, 2, 25), split: { you: 310, employer: 310, relief: 0 } },
  ];

  /* occurrences of a plan in (from, to] */
  function occurrences(p, from, to) {
    const out = [];
    const last = p.end && p.end < to ? p.end : to;
    let cursor = firstOfMonth(from);
    while (cursor <= last) {
      const y = cursor.getUTCFullYear(), m0 = cursor.getUTCMonth();
      if (p.freq === 'monthly' || (p.freq === 'annually' && m0 === p.month - 1)) {
        const due = clampDay(y, m0, p.day);
        if (due > from && due <= last && due >= p.start) out.push(due);
      }
      cursor = addMonths(cursor, 1);
    }
    return out;
  }

  /* ---------- amortisation (port of engine/amortisation.py) ---------- */
  function annuity(bal, rate, n) {
    if (bal <= 0) return 0;
    if (n <= 0) return bal;
    const r = rate / 12;
    return Math.abs(r) < 1e-12 ? bal / n : (bal * r) / (1 - Math.pow(1 + r, -n));
  }
  function paymentsToClear(bal, rate, pay) {
    if (bal <= 0) return 0;
    if (pay <= 0) return null;
    const r = rate / 12;
    if (Math.abs(r) < 1e-12) return Math.ceil(bal / pay - 1e-6);
    const x = 1 - (bal * r) / pay;
    return x <= 0 ? null : Math.ceil(-Math.log(x) / Math.log(1 + r) - 1e-6);
  }
  function rateOn(loan, dt) {
    const p = loan.periods.filter((q) => q.start <= dt && (!q.end || dt <= q.end)).sort((a, b) => b.start - a.start)[0];
    return p ? { rate: p.rate, period: p } : { rate: loan.fallback, period: null };
  }
  function nextPayment(dt, day, strict) {
    let c = clampDay(dt.getUTCFullYear(), dt.getUTCMonth(), day);
    if (c < dt || (strict && +c === +dt)) {
      const n = addMonths(firstOfMonth(dt), 1);
      c = clampDay(n.getUTCFullYear(), n.getUTCMonth(), day);
    }
    return c;
  }
  function schedule(loan, balance, fromDate, extra, until) {
    const rows = [];
    let pay = nextPayment(fromDate, loan.day, true);
    let payment = null, cur = null, recalc = true;
    while (balance > 0.005 && rows.length < 900) {
      if (until && pay > until) break;
      const { rate } = rateOn(loan, pay);
      const remaining = Math.max(monthsBetween(pay, loan.maturity) + 1, 1);
      const interest = (balance * rate) / 12;
      if (rate !== cur) recalc = true;
      if (recalc) {
        let n = remaining;
        if (payment !== null && cur !== null && loan.effect === 'reduce_term') {
          const eff = paymentsToClear(balance, cur, payment);
          if (eff !== null) n = Math.max(Math.min(n, eff), 1);
        }
        payment = annuity(balance, rate, n);
        recalc = false;
      }
      cur = rate;
      let principal = payment - interest, scheduled = payment;
      if (remaining <= 1 || principal >= balance - 0.005) { principal = balance; scheduled = interest + balance; }
      const over = Math.min(extra ? extra(pay) : 0, Math.max(balance - principal, 0));
      const closing = Math.max(balance - principal - over, 0);
      rows.push({ date: pay, rate, opening: balance, payment: scheduled, interest, principal, over, closing });
      if (over > 0 && loan.effect === 'reduce_payment') recalc = true;
      balance = closing;
      const nx = addMonths(firstOfMonth(pay), 1);
      pay = clampDay(nx.getUTCFullYear(), nx.getUTCMonth(), loan.day);
    }
    return rows;
  }
  const balanceOn = (rows, dt, dflt) => { let v = dflt; for (const r of rows) { if (r.date > dt) break; v = r.closing; } return v; };
  const summarise = (rows) => ({
    n: rows.length,
    interest: rows.reduce((s, r) => s + r.interest, 0),
    payoff: rows.length && rows[rows.length - 1].closing <= 0.005 ? rows[rows.length - 1].date : null,
  });
  function overpaymentFor(a, extraMonthly = 0, lumps = []) {
    const planned = plans.filter((p) => p.account === a.id && p.kind === 'overpayment');
    return (pay) => {
      let x = 0;
      planned.forEach((p) => { if (pay >= p.start && (!p.end || pay <= p.end)) x += p.amount; });
      if (extraMonthly && pay > TODAY) x += extraMonthly;
      lumps.forEach((l) => { if (+nextPayment(l.date, a.loan.day, false) === +pay) x += l.amount; });
      return x;
    };
  }

  /* ---------- valuation ---------- */
  const LIABILITY = new Set(['mortgage', 'loan', 'credit_card']);
  const GROUP = { investment: 'investment', pension: 'pension', cash: 'cash', property: 'property', mortgage: 'debt', loan: 'debt', credit_card: 'debt', other_asset: 'other' };
  const GROUPS = [
    { key: 'investment', label: 'Investments', color: 'var(--s1)' },
    { key: 'pension', label: 'Pensions', color: 'var(--s2)' },
    { key: 'cash', label: 'Cash', color: 'var(--s3)' },
    { key: 'property', label: 'Property', color: 'var(--s4)' },
    { key: 'other', label: 'Other assets', color: 'var(--s6)' },
    { key: 'debt', label: 'Debts', color: 'var(--s5)' },
  ];

  function modelValue(a, dt) {
    let v = a.anchor * growth(a.rate, yearsBetween(a.anchorDate, dt));
    if (a.floor != null && a.rate < 0) v = Math.max(v, Math.min(a.floor, a.anchor));
    return v;
  }
  function holdingRows(a) {
    return a.holdings.map((h) => {
      const ins = instruments[h.i];
      const value = h.units * ins.price;
      const cost = h.units * h.avg;
      const prev = ins.price / (1 + ins.dayPct);
      return { ...h, ins, value, cost, gain: value - cost, gainPct: cost ? (value - cost) / cost : 0, day: h.units * (ins.price - prev), dayPct: ins.dayPct };
    });
  }
  function loanOwedToday(a) {
    const rows = schedule(a.loan, a.balance, a.asOf, overpaymentFor(a), TODAY);
    return balanceOn(rows, TODAY, a.balance);
  }
  function valuation(a) {
    let gross = 0, cost = null, day = 0, estimated = false;
    if (a.method === 'holdings') {
      const rows = holdingRows(a);
      gross = rows.reduce((s, r) => s + r.value, 0) + a.cash;
      cost = rows.reduce((s, r) => s + r.cost, 0) + a.cash;
      day = rows.reduce((s, r) => s + r.day, 0);
    } else if (a.method === 'balance') {
      gross = a.balance;
    } else if (a.method === 'model') {
      gross = modelValue(a, TODAY);
      estimated = true;
    } else {
      gross = loanOwedToday(a);
      estimated = true;
    }
    const sign = LIABILITY.has(a.cat) ? -1 : 1;
    const updated = a.method === 'holdings' ? null : a.method === 'model' ? a.anchorDate : a.asOf;
    const age = updated ? Math.round((TODAY - updated) / DAY) : 0;
    const staleness = a.method === 'model' ? 'ok' : age > 90 ? 'alert' : age > 35 ? 'warn' : 'ok';
    const liquid = ['investment', 'cash', 'loan', 'credit_card'].includes(a.cat) && a.wrapper !== 'LISA';
    return { value: sign * gross, gross, cost, gain: cost == null ? null : gross - cost, day, estimated, updated, age, staleness, liquid, group: GROUP[a.cat] };
  }
  const share = (a, scope) => (scope === 'household' ? 1 : a.owners[scope] || 0);

  function totals(scope = 'household') {
    const out = { total: 0, assets: 0, debts: 0, liquid: 0, locked: 0, day: 0, byGroup: {}, rows: [] };
    GROUPS.forEach((g) => (out.byGroup[g.key] = 0));
    accounts.forEach((a) => {
      const s = share(a, scope);
      if (!s) return;
      const v = valuation(a);
      const scoped = v.value * s;
      out.total += scoped;
      if (scoped >= 0) out.assets += scoped; else out.debts += scoped;
      if (v.liquid) out.liquid += scoped; else out.locked += scoped;
      out.day += v.day * s;
      out.byGroup[v.group] += scoped;
      out.rows.push({ a, v, s, scoped });
    });
    return out;
  }

  /* ---------- history (weekly, two years, pinned to today's values) ---------- */
  function mulberry32(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const WEEKS = 104;
  function history(scope = 'household') {
    const rng = mulberry32(20260915);
    const gauss = () => Math.sqrt(-2 * Math.log(rng() || 1e-9)) * Math.cos(2 * Math.PI * rng());
    const dates = [];
    for (let w = WEEKS; w >= 0; w--) dates.push(addDays(TODAY, -7 * w));
    const house = totals('household').byGroup;
    const mine = totals(scope).byGroup;
    const shape = {
      investment: { start: 0.63, vol: 0.02, dip: 0.08 },
      pension: { start: 0.77, vol: 0.013, dip: 0.055 },
      cash: { start: 0.8, vol: 0.018, dip: 0 },
      property: { start: 0.948, vol: 0.0015, dip: 0 },
      other: { start: 1.24, vol: 0, dip: 0 },
      debt: { start: 1.052, vol: 0, dip: 0 },
    };
    const byGroup = {};
    GROUPS.forEach((g) => {
      const s = shape[g.key];
      let w = 0;
      const walk = dates.map(() => (w += gauss() * s.vol));
      const end = walk[WEEKS];
      const ratio = house[g.key] ? mine[g.key] / house[g.key] : 0;
      byGroup[g.key] = dates.map((_, i) => {
        const t = i / WEEKS;
        const bridge = walk[i] - t * end;
        const dip = i < 27 ? 0 : i <= 29 ? (s.dip * (i - 26)) / 3 : s.dip * Math.exp(-(i - 29) / 7);
        return house[g.key] * ratio * (s.start + (1 - s.start) * t + bridge - dip * (1 - t));
      });
    });
    const total = dates.map((_, i) => GROUPS.reduce((sum, g) => sum + byGroup[g.key][i], 0));
    return { dates, byGroup, total };
  }

  /* ---------- projection (port of engine/projection.py) ---------- */
  const DEFAULT_RETURN = { investment: 0.06, pension: 0.06, cash: 0.035 };
  function project({ months = 360, adj = 0, real = false, inflation = 0.025 } = {}) {
    const dates = [TODAY];
    for (let m = 1; m <= months; m++) dates.push(monthEnd(addMonths(TODAY, m)));
    const n = dates.length;
    const zeros = () => new Array(n).fill(0);
    const out = { dates, byGroup: {}, byPerson: { you: zeros(), partner: zeros() }, total: zeros(), contrib: zeros(), loanRows: {} };
    GROUPS.forEach((g) => (out.byGroup[g.key] = zeros()));
    const deflate = (v, i) => (real ? v / Math.pow(1 + inflation, yearsBetween(TODAY, dates[i])) : v);

    accounts.forEach((a) => {
      const v0 = Math.abs(valuation(a).value);
      let vals;
      if (['investment', 'pension', 'cash'].includes(a.cat)) {
        const rate = (a.rate != null && a.cat === 'cash' ? a.rate : DEFAULT_RETURN[a.cat]) + (a.cat === 'cash' ? 0 : adj) - (a.fee || 0);
        const own = plans.filter((p) => p.account === a.id && p.kind === 'contribution');
        let v = v0, cum = 0;
        vals = [v];
        for (let m = 1; m < n; m++) {
          v *= growth(rate, yearsBetween(dates[m - 1], dates[m]));
          own.forEach((p) => {
            const owner = personById[p.owner];
            const stop = owner ? birthday(owner, owner.retire) : null;
            occurrences(p, dates[m - 1], dates[m]).forEach((due) => {
              if (!stop || due < stop) { v += p.gross; cum += p.gross; }
            });
          });
          vals.push(Math.max(v, 0));
          out.contrib[m] += deflate(cum, m);
        }
      } else if (a.method === 'model') {
        vals = dates.map((dt) => modelValue(a, dt));
      } else if (a.method === 'amortising') {
        const rows = schedule(a.loan, v0, TODAY, overpaymentFor(a), dates[n - 1]);
        out.loanRows[a.id] = rows;
        vals = dates.map((dt) => balanceOn(rows, dt, v0));
      } else {
        vals = dates.map(() => v0);
      }
      const sign = LIABILITY.has(a.cat) ? -1 : 1;
      const g = GROUP[a.cat];
      vals.forEach((x, i) => {
        const y = sign * deflate(x, i);
        out.byGroup[g][i] += y;
        out.total[i] += y;
        Object.entries(a.owners).forEach(([pid, s]) => (out.byPerson[pid][i] += y * s));
      });
    });
    return out;
  }
  const firstReaching = (dates, series, target) => { const i = series.findIndex((v) => v >= target); return i < 0 ? null : dates[i]; };

  /* ---------- ledger, allowances, balance history ---------- */
  const transactions = {
    'isa-you': [
      { date: d(2026, 9, 15), type: 'DEPOSIT', amount: 500, status: 'pending', note: 'Monthly ISA' },
      { date: d(2026, 9, 15), type: 'BUY', sym: 'VWRP', units: 3.3778, amount: -400, status: 'pending', note: 'Monthly ISA · 80%' },
      { date: d(2026, 9, 15), type: 'BUY', sym: 'VUAG', units: 1.0384, amount: -100, status: 'pending', note: 'Monthly ISA · 20%' },
      { date: d(2026, 8, 17), type: 'BUY', sym: 'VWRP', units: 3.4102, amount: -400 },
      { date: d(2026, 8, 17), type: 'BUY', sym: 'VUAG', units: 1.0551, amount: -100 },
      { date: d(2026, 8, 15), type: 'DEPOSIT', amount: 500 },
      { date: d(2026, 8, 6), type: 'DIVIDEND', sym: 'ISF', amount: 18.44 },
      { date: d(2026, 7, 15), type: 'BUY', sym: 'VWRP', units: 3.4631, amount: -400 },
      { date: d(2026, 7, 15), type: 'BUY', sym: 'VUAG', units: 1.0712, amount: -100 },
      { date: d(2026, 7, 15), type: 'DEPOSIT', amount: 500 },
      { date: d(2026, 4, 7), type: 'BUY', sym: 'SGLN', units: 21.5, amount: -942.1 },
      { date: d(2026, 4, 6), type: 'DEPOSIT', amount: 5000, note: 'New tax year' },
      { date: d(2026, 3, 14), type: 'OPENING_BALANCE', sym: 'VWRP', units: 196.2, cost: 19620.4, note: 'Entered when tracking started' },
      { date: d(2026, 3, 14), type: 'OPENING_BALANCE', sym: 'VUAG', units: 110.4, cost: 9020.5, note: 'Entered when tracking started' },
    ],
  };
  const allowances = {
    taxYear: '2026/27', end: d(2027, 4, 5), limits: { isa: 20000, lisa: 4000, pension: 60000 },
    you: { isa: 8000, lisa: 0, pension: 6750 },
    partner: { isa: 5500, lisa: 4000, pension: 3100 },
  };
  function balanceEntries(a) {
    const rng = mulberry32(a.id.split('').reduce((s, c) => s + c.charCodeAt(0), 0));
    const out = [];
    let v = a.method === 'model' ? a.anchor : a.balance;
    let dt = a.method === 'model' ? a.anchorDate : a.asOf;
    for (let k = 0; k < 8; k++) {
      out.push({ date: dt, value: v, source: k === 0 ? 'Manual' : a.cat === 'pension' ? 'Statement' : 'Manual' });
      dt = addMonths(dt, a.method === 'model' ? -6 : -1);
      const drift = a.cat === 'pension' ? 0.012 : a.method === 'model' ? -a.rate / 2 : 0;
      v = v / (1 + drift + (rng() - 0.5) * (a.cat === 'cash' ? 0.12 : 0.01));
    }
    return out;
  }

  window.NW = {
    TODAY, DAY, d, addMonths, addDays, monthEnd, yearsBetween, monthsBetween, growth, birthday,
    people, personById, instruments, accounts, accountById, plans, transactions, allowances, GROUPS, GROUP, LIABILITY,
    occurrences, annuity, schedule, balanceOn, summarise, rateOn, overpaymentFor, modelValue,
    holdingRows, valuation, totals, history, project, firstReaching, balanceEntries,
  };
})();

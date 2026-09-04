/* 六人旅行决策工作台 —— 前端逻辑（无框架）。 */
'use strict';
const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));

const S = {
  project: null, meta: null, analysis: null,
  plans: null, weather: 'sunny', selPlanId: null, selWeather: 'sunny', votes: {},
  step: 1, unsaved: false, kbOpen: false,
};

const LABEL = {};
const KIND_TEXT = { hard: '硬约束', soft: '偏好' };

function api(path, opts) {
  return fetch(path, opts).then(r => r.json().then(j => ({ ok: r.ok, status: r.status, body: j })));
}
function toast(msg) {
  const el = $('#toast'); el.textContent = msg; el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2400);
}

/* ---------------------------------------------------------------- 初始化 */
async function init() {
  const [st, meta] = await Promise.all([api('/api/state'), api('/api/meta')]);
  S.project = st.body.project; S.meta = meta.body;
  Object.keys(S.meta.dimensions).forEach(k => LABEL[k] = S.meta.dimensions[k].label);
  refreshConflicts();
  renderAll();
  bindNav();
}

async function refreshConflicts() {
  const c = await api('/api/conflicts');
  S.analysis = c.body;
}

async function saveState(next) {
  S.project = next || S.project;
  const r = await api('/api/state', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project: S.project }),
  });
  if (!r.ok) { toast('保存失败：' + (r.body.error || r.status)); return false; }
  S.project = r.body.project;
  await refreshConflicts();
  S.unsaved = false;
  S.plans = null; S.selPlanId = null; S.votes = {};
  return true;
}

function markDirty() { S.unsaved = true; renderNav(); }

/* ---------------------------------------------------------------- 渲染 */
function renderAll() {
  renderNav();
  renderSettings();
  renderReqs();
  renderAnalysis();
  renderCityKB();
  renderPlansPanel();
  renderDecidePanel();
}

function renderNav() {
  const nav = $('#nav'); nav.innerHTML = '';
  const titles = ['需求共识', '冲突与不确定', '生成候选方案', '决策与导出'];
  titles.forEach((t, i) => {
    const b = document.createElement('button');
    b.textContent = (i + 1) + '. ' + t;
    if (S.step === i + 1) b.className = 'active';
    b.onclick = () => { S.step = i + 1; $$('.step').forEach(p => p.style.display = 'none');
      $('#step' + S.step).style.display = 'block'; renderNav(); };
    nav.appendChild(b);
  });
  $('#saveBtn').disabled = !S.unsaved;
  $('#saveBtn').textContent = S.unsaved ? '● 保存修改' : '保存修改';
}

function renderSettings() {
  const d = S.project.settings.trip_dates || {};
  $('#dateStart').value = d.start || '';
  $('#dateEnd').value = d.end || '';
  $('#dateStart').onchange = e => { S.project.settings.trip_dates = Object.assign(
    {}, S.project.settings.trip_dates, { start: e.target.value }); markDirty(); };
  $('#dateEnd').onchange = e => { S.project.settings.trip_dates = Object.assign(
    {}, S.project.settings.trip_dates, { end: e.target.value }); markDirty(); };
}

function reqOf(p, r) { return S.project.requirements.find(x => x.rid === r.rid); }

function memberName(id) {
  const m = S.project.members.find(x => x.id === id);
  return m ? (m.alias || id) : id;
}

function kindToggle(r) {
  const cur = reqOf(S.project, r);
  cur.kind = cur.kind === 'hard' ? 'soft' : 'hard';
  markDirty(); renderReqs();
}

/* 每种维度支持编辑的字段；返回 [{label, type, get, set}] 或 null */
function editorsFor(r) {
  const v = r.value || {};
  const E = [];
  const addNum = (key, label) => E.push({ label, type: 'number', val: v[key] || 0,
    set: x => v[key] = Number(x) });
  const addTime = (key, label) => E.push({ label, type: 'text', val: v[key] || 'HH:MM',
    ph: 'HH:MM', set: x => v[key] = x });
  switch (r.dimension) {
    case 'budget_cap': addNum('max_yuan', '人均上限(元)'); break;
    case 'walk_limit': addNum('max_steps', '每天步数上限'); break;
    case 'return_deadline':
      addTime('time', '返回截止'); E.push({ label: '地点', type: 'text', val: v.place || '',
        set: x => v.place = x });
      break;
    case 'depart_earliest': addTime('time', '最早出发'); break;
    case 'transport_capacity': addNum('seats', '座位数'); break;
    default: return null;
  }
  return E;
}

function renderReqs() {
  const host = $('#reqs'); host.innerHTML = '';
  const ids = S.project.members.map(m => m.id);
  const byOwner = {};
  S.project.requirements.forEach(r => {
    const key = r.scope === 'group' ? '__GROUP__' : r.member;
    (byOwner[key] = byOwner[key] || []).push(r);
  });
  const order = ids.concat('__GROUP__');
  order.forEach(key => {
    const list = byOwner[key] || [];
    if (!list.length) return;
    const block = document.createElement('div'); block.className = 'member-block';
    const head = document.createElement('div'); head.className = 'member-head';
    head.innerHTML = key === '__GROUP__'
      ? '👥 全员级需求'
      : '👤 成员 ' + memberName(key) + '（硬约束：' +
        list.filter(r => r.kind === 'hard').map(r => LABEL[r.dimension]).join('、') +
        (list.some(r => r.kind === 'hard') ? '' : '无') + '）';
    block.appendChild(head);
    list.forEach(r => block.appendChild(reqRow(r)));
    host.appendChild(block);
  });
}

function reqRow(r) {
  const row = document.createElement('div'); row.className = 'req';
  const dim = document.createElement('div'); dim.className = 'dim';
  dim.innerHTML = '<span class="chip ' + (r.kind === 'hard' ? 'hard' : 'soft') + '">' +
    (r.kind === 'hard' ? '硬' : '软') + '</span> ' + (LABEL[r.dimension] || r.dimension);
  row.appendChild(dim);
  if (r.scope === 'member') {
    const tag = document.createElement('span'); tag.className = 'tag';
    tag.textContent = memberName(r.member); dim.appendChild(tag);
  }
  const ops = document.createElement('div'); ops.className = 'ops';
  const kb = document.createElement('button'); kb.className = 'kind-btn ' + r.kind;
  kb.textContent = KIND_TEXT[r.kind];
  kb.title = '点击切换 硬/软';
  kb.onclick = () => kindToggle(r);
  ops.appendChild(kb);
  const eds = editorsFor(r);
  if (eds) eds.forEach(e => {
    const lab = document.createElement('label');
    lab.innerHTML = '<span class="muted">' + e.label + '</span> ';
    const inp = document.createElement('input');
    inp.type = e.type; inp.className = e.type === 'number' ? 'num' : 'txt';
    inp.value = e.val; if (e.ph) inp.placeholder = e.ph;
    inp.onchange = ev => { e.set(ev.target.value); markDirty(); renderReqs(); };
    lab.appendChild(inp); ops.appendChild(lab);
  });
  row.appendChild(ops);
  if (r.quote) { const q = document.createElement('div'); q.className = 'src';
    q.textContent = '「' + r.quote + '」'; row.appendChild(q); }
  if (r.note) { const n = document.createElement('div'); n.className = 'why';
    n.textContent = '· ' + r.note; row.appendChild(n); }
  return row;
}

function severityCls(s) { return s === 'high' ? 'high' : (s === 'medium' ? 'medium' : 'info'); }

function renderAnalysis() {
  const cf = $('#conflicts'); cf.innerHTML = '';
  (S.analysis.conflicts || []).forEach(c => {
    const d = document.createElement('div');
    d.className = 'conf ' + severityCls(c.severity);
    d.innerHTML = '<div style="min-width:200px"><span class="tag">' +
      ({ high: '⚠️ 需拍板', medium: '⚖️ 有取舍', info: 'ℹ️ 背景' }[c.severity] || c.severity) +
      '</span> <span class="t">' + c.title + '</span></div>' +
      '<div class="d">' + c.detail + '</div>';
    cf.appendChild(d);
  });
  const uc = $('#uncertainties'); uc.innerHTML = '';
  (S.analysis.uncertainties || []).forEach(u => {
    const d = document.createElement('div'); d.className = 'unc';
    d.innerHTML = '<span class="q"><b>☐ ' + u.question + '</b><div class="d muted">' +
      u.detail + '</div></span><span class="owner">' + u.owner + '</span>' +
      (u.due ? '<span class="due">' + u.due + '</span>' : '');
    uc.appendChild(d);
  });
}

function renderCityKB() {
  const box = $('#kb'); box.innerHTML = '';
  const cities = S.meta.cities; const order = S.meta.city_order;
  order.forEach(id => {
    const c = cities[id];
    const det = document.createElement('details');
    det.innerHTML = '<summary>📍 ' + c.name + '　<em class="muted">' + c.pros +
      '</em></summary><p class="hint" style="margin-top:6px"><b>短板：</b>' + c.cons +
      '　<b>素食：</b>' + c.veg_note + '</p><p class="hint">白天活动 ' + c.acts +
      ' 项 / 雨天室内备选 ' + c.rain_acts + ' 项；住宿示例：' + c.lodging.join('、') + '</p>';
    box.appendChild(det);
  });
}

/* ---------------------------------------------------------------- 方案 */
async function generate() {
  const btn = $('#genBtn'); btn.disabled = true; btn.textContent = '生成中…';
  const r = await api('/api/plans', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ weather: S.weather }),
  });
  btn.disabled = false; btn.textContent = '生成候选方案';
  if (!r.ok) { toast('生成失败：' + (r.body.error || r.status)); return; }
  S.plans = r.body.plans; S.selPlanId = null; S.selWeather = S.weather; S.votes = {};
  renderPlansPanel(); renderDecidePanel();
  toast('已生成 ' + S.plans.length + ' 个可行候选');
  if (r.body.city_notes && Object.keys(r.body.city_notes).length) {
    console.warn('city_notes', r.body.city_notes);
  }
}

function renderPlansPanel() {
  const host = $('#plans'); host.innerHTML = '';
  $('#detail').innerHTML = '';
  if (!S.plans) {
    host.innerHTML = '<p class="hint">先点上面「生成候选方案」。天气切换后需重新生成。</p>';
    return;
  }
  if (!S.plans.length) {
    host.innerHTML = '<p class="conf high" style="border:none">😶 当前约束下没有完全可行的方案。' +
      '请回到第 1 步，把某条偏好（如步行上限 / 预算）从"硬"改成"软"，或换日期再看。</p>';
    return;
  }
  S.plans.forEach(p => host.appendChild(planCard(p)));
}

function planCard(p) {
  const card = document.createElement('div');
  card.className = 'plan-card' + (S.selPlanId === p.id ? ' sel' : '');
  const match = p.match;
  const cls = match >= 90 ? 'hi' : (match >= 70 ? 'mid' : 'lo');
  card.innerHTML =
    '<div style="display:flex;justify-content:space-between;align-items:baseline">' +
      '<span class="plan-city">' + p.city_name + '</span>' +
      '<span class="badge match ' + cls + '">匹配 ' + match + '%</span></div>' +
    '<div class="plan-meta">' + p.transport.name + ' · ' + p.lodging.name + '</div>' +
    '<div>' + (p.flags || []).map(f => '<span class="tag warn">' + f + '</span>').join('') + '</div>' +
    '<div class="plan-foot"><span class="price">人均约 ' + p.cost.total + ' 元</span>' +
      '<span class="muted">步/天 ' + p.days.map(d => d.steps_est).join('·') + '</span></div>';
  card.onclick = () => { S.selPlanId = p.id; S.selWeather = p.weather;
    renderPlansPanel(); showDetail(p); };
  return card;
}

function blockCls(b) { return b.type === 'activity' ? 'act' : ''; }

function showDetail(p) {
  const host = $('#detail'); host.innerHTML = '';
  if (!p) { host.innerHTML = ''; return; }
  const g = p.gaps || {};
  let gapHtml = S.project.members.map(m => {
    const mg = g[m.id] || [];
    const cls = mg.length ? 'no' : 'ok';
    const txt = mg.length ? mg.map(x => x.why).join('；') : '✓ 全部满足';
    return '<div class="gaprow ' + cls + '">' + memberName(m.id) + '：' + txt + '</div>';
  }).join('');
  if (g.GROUP && g.GROUP.length) {
    gapHtml += g.GROUP.map(x => '<div class="gaprow warn">全员：' + x.why + '</div>').join('');
  }
  host.innerHTML =
    '<div class="panel">' +
    '<h2 class="sec">📋 ' + p.city_name + ' · ' + p.transport.name +
    ' <button class="btn primary" style="margin-left:auto" id="selPlan">✓ 选定此方案，进入表决</button></h2>' +
    '<div class="muted">' + (p.transport.note || '') + '</div>' +
    p.days.map(d =>
      '<div class="daycard"><h4>' + d.label + ' ' + (d.date || '') +
      ' <span class="muted">（步行约 ' + d.steps_est + ' 步）</span></h4>' +
      d.blocks.map(b => '<div class="blk ' + blockCls(b) + '"><span class="t">' + b.when +
        '</span><span><b>' + b.title + '</b> ' + (b.note || '') +
        (b.act ? ' <em class="muted">' + ((b.act.steps||0)+'步') +
        (b.act.cost ? '，门票' + b.act.cost + '元' : '') + '</em>' : '') +
        '</span></div>').join('') + '</div>').join('') +
    '<div class="daycard"><h4>💴 费用（每人估算）</h4><div class="blk"><span class="t"></span>' +
      '<span>交通 ' + p.cost.transport + ' ＋ 住宿 ' + p.cost.lodging +
      ' ＋ 餐饮 ' + p.cost.food + ' ＋ 门票活动 ' + p.cost.activities +
      ' ＝ <b class="price">' + p.cost.total + ' 元</b></span></div></div>' +
    '<div class="daycard"><h4>👥 逐人核对</h4>' + gapHtml + '</div>' +
    '</div>';
  $('#selPlan').onclick = () => {
    S.votes = {};
    $$('.step').forEach(p2 => p2.style.display = 'none');
    S.step = 4; $('#step4').style.display = 'block';
    renderNav(); renderDecidePanel();
    toast('已选定：' + p.city_name + '（匹配 ' + p.match + '%）');
  };
}

/* ---------------------------------------------------------------- 决策 */
function renderDecidePanel() {
  const host = $('#decide'); host.innerHTML = '';
  const sel = S.selPlanId ? S.plans.find(x => x.id === S.selPlanId) : null;
  if (!sel) {
    host.innerHTML = '<p class="hint">尚未选定方案：请到第 3 步生成候选并点「选定此方案」。</p>';
    return;
  }
  host.innerHTML =
    '<div class="panel"><h2 class="sec">📍 已选定：' + sel.city_name + ' · ' +
    sel.transport.name + '（匹配 ' + sel.match + '%）</h2>' +
    '<div class="muted">六人各自表态（可在群里对着投）</div>' +
    '<div id="voteArea"></div>' +
    '<button class="btn primary" id="doExport" style="margin-top:10px">📤 生成定稿文本（可发群聊）</button>' +
    '<div id="exportOut"></div></div>';
  const va = $('#voteArea'); va.innerHTML = '';
  const opts = [['accept', '✓ 接受'], ['concerned', '▲ 有保留'], ['oppose', '✗ 反对']];
  S.project.members.forEach(m => {
    const row = document.createElement('div'); row.className = 'vote';
    row.innerHTML = '<b style="width:64px">' + memberName(m.id) + '</b>';
    opts.forEach(([k, label]) => {
      const b = document.createElement('button'); b.textContent = label;
      if (S.votes[m.id] === k) b.className = 'on-' + k;
      b.onclick = () => { S.votes[m.id] = S.votes[m.id] === k ? null : k; renderDecidePanel(); };
      row.appendChild(b);
    });
    va.appendChild(row);
  });
  $('#doExport').onclick = async () => {
    const btn = $('#doExport'); btn.disabled = true; btn.textContent = '生成中…';
    const r = await api('/api/decide', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_id: sel.id, votes: S.votes, weather: S.selWeather || 'sunny' }),
    });
    btn.disabled = false; btn.textContent = '📤 生成定稿文本（可发群聊）';
    if (!r.ok) { toast('生成失败：' + (r.body.error || r.status)); return; }
    const out = $('#exportOut');
    out.innerHTML = '<h3 style="margin:14px 0 6px">⬇️ 复制下面的内容发到群聊：</h3>' +
      '<pre class="export" id="exportText"></pre>' +
      '<button class="btn ghost" id="copyBtn" style="margin-top:8px">📋 复制全文</button>';
    $('#exportText').textContent = r.body.export;
    $('#copyBtn').onclick = () => {
      const txt = $('#exportText').textContent;
      const done = () => toast('已复制');
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(txt).then(done).catch(() => fallbackCopy(txt, done));
      } else fallbackCopy(txt, done);
    };
    toast('定稿已生成');
  };
}

function fallbackCopy(txt, done) {
  const ta = document.createElement('textarea');
  ta.value = txt; document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); done(); } catch (e) { toast('复制失败，请手动选择复制'); }
  document.body.removeChild(ta);
}

function bindNav() {
  $('#resetBtn').onclick = async () => {
    if (!confirm('恢复成群聊原始种子？当前改动会丢失。')) return;
    const r = await api('/api/reset', { method: 'POST' });
    S.project = r.body.project; S.plans = null; S.selPlanId = null; S.votes = {};
    await refreshConflicts(); renderAll(); toast('已恢复种子');
  };
  $('#saveBtn').onclick = async () => { if (await saveState()) { toast('已保存'); renderAll(); } };
  $('#genBtn').onclick = generate;
  const seg = $('#weatherSeg');
  seg.querySelectorAll('button').forEach(b => b.onclick = () => {
    S.weather = b.dataset.w;
    seg.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
  });
}

init();

/* 显伴 · 小光 — client
   Talks only to same-origin /api/*. Identity lives in an HttpOnly cookie the
   script can't read; nothing here stores or sends a user id. */
'use strict';
(() => {
  /* ───────── utils ───────── */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const clip = (s, n) => (s = String(s || ''), s.length > n ? s.slice(0, n - 1) + '…' : s);
  const pad = n => String(n).padStart(2, '0');
  const dkey = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const fmtDay = k => {
    if (!k) return '';
    k = k.slice(0, 10);
    const today = dkey(), y = new Date(); y.setDate(y.getDate() - 1);
    if (k === today) return '今天';
    if (k === dkey(y)) return '昨天';
    const [, m, d] = k.split('-').map(Number);
    return `${m} 月 ${d} 日`;
  };
  const fmtTime = iso => (iso || '').slice(11, 16);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  const ICON = {
    chat: '<path d="M5 5.5h14a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5H10l-5 4v-4A1.5 1.5 0 0 1 3.5 15V7A1.5 1.5 0 0 1 5 5.5z"/>',
    me: '<circle cx="12" cy="8.8" r="3.8"/><path d="M4.5 20c1.2-3.6 4-5.4 7.5-5.4s6.3 1.8 7.5 5.4"/>',
    plan: '<path d="M4 18c3-1 4-7 8-7s4.5 4 8 3"/><circle cx="4" cy="18" r="1.4"/><circle cx="20" cy="14" r="1.4"/><path d="M12 4v4M10 6h4"/>',
    spark: '<path d="M12 3.5c.6 3.9 2.6 5.9 6.5 6.5-3.9.6-5.9 2.6-6.5 6.5-.6-3.9-2.6-5.9-6.5-6.5 3.9-.6 5.9-2.6 6.5-6.5zM18.5 15.5c.3 1.6 1 2.3 2.5 2.5-1.5.3-2.2 1-2.5 2.5-.3-1.5-1-2.2-2.5-2.5 1.5-.2 2.2-.9 2.5-2.5z"/>',
    bloom: '<path d="M12 20v-6M12 14c-4 0-6-3-6-7 3 0 6 2 6 7zM12 14c4 0 6-3 6-7-3 0-6 2-6 7z"/>',
    send: '<path d="M12 19V5.5M6.5 11 12 5.5l5.5 5.5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    close: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    moon: '<path d="M19.5 14.6A8 8 0 1 1 9.4 4.5a6.4 6.4 0 0 0 10.1 10.1z"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M5.5 18.5l1.7-1.7M16.8 7.2l1.7-1.7"/>',
    eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.6"/>',
    back: '<path d="M14.5 6 8.5 12l6 6"/>',
    share: '<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5M5 13v5.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V13"/>',
  };
  const ic = n => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICON[n]}</svg>`;
  const STAR_C = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)'];
  const star = (i = 0) => `<svg class="star" viewBox="0 0 24 24" aria-hidden="true"><path fill="${STAR_C[Math.abs(i) % 5]}" d="M12 2.6c1 2.4 1.8 4.8 3 6.7 2.4.2 4.6.3 6.6.8-1.7 1.5-3.6 3-5.2 4.6.5 2.3 1.2 4.6 1.4 6.8-2-1.1-4-2.5-5.9-3.3-2.1.9-4 2.4-6.1 3.3.5-2.3 1-4.6 1.6-6.8C5.8 13.2 4 11.6 2.3 10c2-.5 4.3-.4 6.6-.7 1-1.8 2.1-4.3 3.1-6.7z"/></svg>`;

  /* ───────── api ───────── */
  class HttpError extends Error { constructor(status, msg) { super(msg); this.status = status; } }
  async function api(path, body, method) {
    const r = await fetch(path, {
      method: method || (body === undefined ? 'GET' : 'POST'),
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
    });
    let data = null;
    try { data = await r.json(); } catch { /* empty */ }
    if (r.status === 401 && !path.startsWith('/api/auth/')) { showGate(); throw new HttpError(401, '请先登录'); }
    if (!r.ok) throw new HttpError(r.status, (data && data.error) || `请求失败（${r.status}）`);
    return data;
  }

  /* ───────── state ───────── */
  let S = null;              // last bootstrap payload
  const ui = { view: 'chat', busy: false, ctxOpen: null, recFilter: 'all', reportDays: 10, report: null,
               scene: null, ob: { i: 0, a: {} }, layer: null, composeMode: 'chat' };
  const orbs = {};           // named orb handles

  const P = () => (S && S.profile) || {};
  const agentName = () => P().agent_name || '小光';
  // Shades are mixed here rather than with CSS color-mix() so html2canvas
  // (which can't parse color-mix) renders the share card correctly.
  function mix(hex, other, t) {
    const p = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
    const a = p(hex), b = p(other);
    return '#' + a.map((v, i) => Math.round(v + (b[i] - v) * t).toString(16).padStart(2, '0')).join('');
  }
  function setHueVars(h) {
    const r = document.documentElement.style;
    const [R, G, B] = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
    r.setProperty('--hue', h);
    r.setProperty('--hue-soft', mix(h, '#ffffff', .86));
    r.setProperty('--hue-mid', mix(h, '#ffffff', .6));
    r.setProperty('--hue-deep', mix(h, '#000000', .3));
    r.setProperty('--hue-glow', `rgba(${R},${G},${B},.5)`);
    r.setProperty('--hue-faint', `rgba(${R},${G},${B},.18)`);
  }
  function applyHue() {
    const h = /^#[0-9a-f]{6}$/i.test(P().agent_hue || '') ? P().agent_hue : '#8a7dff';
    setHueVars(h);
    $('meta[name="theme-color"]').setAttribute('content', ui.view === 'chat' ? '#0c0d14' : '#ffffff');
  }

  let toastT = 0;
  function toast(msg, ms = 2200) {
    const t = $('#toast');
    t.textContent = msg; t.classList.add('show');
    clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), ms);
  }

  /* ───────── gate / auth ───────── */
  let authMode = 'login';
  function showGate() {
    $('#app').hidden = true; $('#onboard').hidden = true; $('#gate').hidden = false;
    $('#authForm').hidden = true; $('.gate-hero').hidden = false;
    if (!orbs.gate) orbs.gate = Orb.mount($('#gateOrb'), { size: 150, hue: '#8a7dff', emotion: '02' });
  }
  function showAuth(mode) {
    authMode = mode;
    $('.gate-hero').hidden = true; $('#authForm').hidden = false;
    $('#authTitle').textContent = mode === 'login' ? '登录' : (S && S.user && S.user.kind === 'guest' ? '保存我的记录' : '注册');
    $('#authSubmit').textContent = mode === 'login' ? '登录' : '注册';
    $('#authToggle').textContent = mode === 'login' ? '还没有账号？注册' : '已有账号？登录';
    $('#authForm [name=password]').autocomplete = mode === 'login' ? 'current-password' : 'new-password';
    $('#authErr').textContent = '';
    $('#authForm [name=username]').focus();
  }
  $('#authForm').addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target, btn = $('#authSubmit');
    btn.disabled = true; $('#authErr').textContent = '';
    try {
      await api(authMode === 'login' ? '/api/auth/login' : '/api/auth/register',
        { username: f.username.value.trim(), password: f.password.value });
      f.reset();
      await boot();
    } catch (err) {
      $('#authErr').textContent = err.message;
    } finally { btn.disabled = false; }
  });

  /* ───────── onboarding (8 questions from creative spec §A) ───────── */
  function showOnboard() {
    $('#gate').hidden = true; $('#app').hidden = true; $('#onboard').hidden = false;
    ui.ob = { i: 0, a: { agent_name: '小光' } };
    renderOb();
  }
  function renderOb() {
    const Q = S.onboarding, i = ui.ob.i, q = Q[i], a = ui.ob.a;
    const hue = (Q[1].options.find(o => o.v === a.agent_avatar_id) || {}).hue || '#8a7dff';
    setHueVars(hue);
    const cur = a[q.key];
    let field = '';
    if (q.type === 'text') {
      field = `<input class="ob-input" id="obText" maxlength="60" placeholder="${esc(q.ph || '')}" value="${esc(cur ?? (q.default || ''))}">`;
    } else {
      const opts = q.options.map(o => typeof o === 'string' ? { v: o, label: o } : o);
      const multi = q.type.startsWith('multi');
      field = `<div class="ob-chips" role="group">${opts.map(o => {
        const on = multi ? (cur || []).includes(o.v) : cur === o.v;
        return `<button class="chip${on ? ' on' : ''}" data-act="ob-pick" data-v="${esc(o.v)}" aria-pressed="${on}">${o.hue ? `<i class="dot" style="background:${o.hue}"></i>` : ''}${esc(o.label)}</button>`;
      }).join('')}</div>`;
      if (q.type.endsWith('_or_text')) {
        const custom = multi ? (cur || []).find(v => !opts.some(o => o.v === v)) : (opts.some(o => o.v === cur) ? '' : cur);
        field += `<input class="ob-input sm" id="obText" maxlength="40" placeholder="${esc(q.ph || '')}" value="${esc(custom || '')}">`;
      }
    }
    $('#onboard').innerHTML = `
      <header class="ob-top">
        ${i ? `<button class="icon-btn" data-act="ob-back" aria-label="上一题">${ic('back')}</button>` : '<span style="width:36px"></span>'}
        <div class="ob-bar" aria-hidden="true"><i style="width:${(i / Q.length) * 100}%"></i></div>
        <span class="ob-count">${i + 1} / ${Q.length}</span>
      </header>
      <div class="ob-body">
        <div class="ob-stage"><div id="obOrb"></div></div>
        <h1 class="ob-q" id="obQ">${esc(q.q)}</h1>
        ${q.max ? `<p class="ob-hint">最多选 ${q.max} 个</p>` : ''}
        ${field}
        <div class="ob-nav">
          ${q.optional ? `<button class="btn btn-ghost" data-act="ob-skip">跳过</button>` : ''}
          <button class="btn btn-ink" data-act="ob-next" id="obNext">${i === Q.length - 1 ? '完成' : '下一题'}</button>
        </div>
      </div>`;
    orbs.ob = Orb.mount($('#obOrb'), { size: 128, hue, emotion: i === 0 ? '01' : (i === Q.length - 1 ? '10' : '35') });
    const t = $('#obText');
    if (t && q.type === 'text') { t.focus(); t.select(); }
    t && t.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); obNext(); } });
  }
  function obCollect() {
    const q = S.onboarding[ui.ob.i], a = ui.ob.a, t = $('#obText');
    const txt = t ? t.value.trim() : '';
    if (q.type === 'text') a[q.key] = txt || q.default || '';
    else if (q.type === 'single_or_text' && txt) a[q.key] = txt;
    else if (q.type === 'multi_or_text') {
      const opts = q.options;
      a[q.key] = (a[q.key] || []).filter(v => opts.includes(v));
      if (txt) a[q.key].push(txt);
    }
  }
  async function obNext() {
    obCollect();
    const Q = S.onboarding, q = Q[ui.ob.i], v = ui.ob.a[q.key];
    const empty = v == null || v === '' || (Array.isArray(v) && !v.length);
    if (empty && !q.optional && q.key !== 'boundaries') { toast('先回答一下这一题'); return; }
    if (ui.ob.i < Q.length - 1) { ui.ob.i++; renderOb(); return; }
    $('#obNext').disabled = true;
    try {
      S = { ...S, ...(await api('/api/onboard', { answers: ui.ob.a })) };
      orbs.ob && orbs.ob.react('burst');
      await sleep(reduceMotion ? 0 : 700);
      enterApp();
    } catch (err) { toast(err.message); $('#obNext').disabled = false; }
  }
  /* ───────── shell ───────── */
  const NAV = [
    { id: 'chat', label: '对话', icon: 'chat' },
    { id: 'me', label: '画像', icon: 'me' },
    { id: 'plan', label: '计划', icon: 'plan' },
    { id: 'spark', label: '灵感', icon: 'spark' },
    { id: 'bloom', label: '蜕变', icon: 'bloom' },
  ];

  function enterApp() {
    $('#gate').hidden = true; $('#onboard').hidden = true; $('#app').hidden = false;
    applyHue();
    if (location.hash.slice(1) && NAV.some(n => n.id === location.hash.slice(1))) ui.view = location.hash.slice(1);
    ui.scene = S.scene ? { run: S.scene, step: null } : null;
    renderShell();
  }

  function renderShell() {
    applyHue();
    const unseen = (S.inbox || []).length;
    const nav = (cls) => NAV.map(n => `<button class="${cls}" data-act="nav" data-v="${n.id}" ${ui.view === n.id ? 'aria-current="page"' : ''}>
        ${ic(n.icon)}<span>${n.label}</span>${n.id === 'chat' && unseen ? '<i class="dot" aria-label="有新消息"></i>' : ''}</button>`).join('');
    $('#rail').innerHTML = `<div class="rail-brand" title="显伴">显</div>${nav('rail-btn')}
      <div class="rail-foot"><button class="rail-btn" data-act="settings" aria-label="设置">${ic('gear')}<span>设置</span></button></div>`;
    $('#tabbar').innerHTML = nav('tab-btn');
    renderView();
    renderSide();
  }

  function go(view) {
    if (view === ui.view) return;
    ui.view = view;
    history.replaceState(null, '', '#' + view);
    renderShell();
    $('#stage').scrollTop = 0;
  }

  function renderView() {
    const v = ui.view;
    $('#stage').dataset.view = v;
    if (v === 'chat') return renderChat();
    if (v === 'me') return renderMe();
    if (v === 'plan') return renderPlan();
    if (v === 'spark') return renderSpark();
    if (v === 'bloom') return renderBloom();
  }

  /* ───────── chat ───────── */
  function statusLine() {
    const c = S.counts, todo = (S.steps || []).filter(s => s.status === 'todo');
    if (ui.busy) return '正在想…';
    if (c.guesses) return `有 ${c.guesses} 条猜测等你确认`;
    if (todo.length) return `在陪你做：${clip(todo[0].title, 16)}`;
    return P().intent_primary ? `陪你靠近：${clip(P().intent_primary, 16)}` : '在这里';
  }

  function renderChat() {
    const st = $('#stage');
    st.innerHTML = `
      <header class="chat-top">
        <button class="who" data-act="activity" aria-label="查看${esc(agentName())}在做什么">
          <span class="who-stage"><span id="chatOrb"></span></span>
          <span class="who-txt"><b>${esc(agentName())}</b><small id="whoStatus">${esc(statusLine())}</small></span>
        </button>
        <span class="rank-chip" title="完成小步获得光点">${esc(S.rank.rank)} · ${S.rank.xp}</span>
      </header>
      <div class="thread" id="thread" aria-live="polite"><div class="thread-in" id="threadIn"></div></div>
      <div class="dock" id="dock"></div>`;
    orbs.chat = Orb.mount($('#chatOrb'), { size: 56, hue: P().agent_hue, emotion: '02' });
    renderThread();
    renderDock();
    if ((S.inbox || []).length) api('/api/inbox/seen', {}).then(() => { S.inbox = []; renderShellBadges(); }).catch(() => {});
  }

  function renderShellBadges() {
    $$('[data-act="nav"][data-v="chat"] .dot').forEach(d => d.remove());
  }

  function msgHtml(m) {
    const meta = m.meta || {};
    const isMe = m.role === 'user';
    let extra = '';
    if (!isMe && (meta.memories || []).length) {
      extra += `<button class="ctx-btn" data-act="ctx" data-id="${m.id}">${ic('eye')}参考了 ${meta.memories.length} 条记忆</button>`;
    }
    if (!isMe && (meta.tools || []).length) extra += meta.tools.map(toolChip).join('');
    return `<div class="msg ${isMe ? 'me' : 'ai'}${meta.proactive ? ' proactive' : ''}" data-mid="${m.id}">
      ${meta.proactive ? '<span class="msg-tag">主动来找你</span>' : ''}
      <div class="bubble">${fmtText(m.content)}</div>
      ${extra ? `<div class="msg-extra">${extra}</div>` : ''}
      <time>${fmtTime(m.created_at)}</time></div>`;
  }

  function fmtText(t) { return esc(t).replace(/\n/g, '<br>'); }

  const TOOL_LABEL = {
    log_good_news: a => `${star(1)}收下好消息`, log_lazy_day: () => `${ic('moon')}今天是偷懒日`,
    add_step: a => `${ic('plus')}加入计划：${esc(clip(a.title, 18))}`, complete_step: () => `${ic('check')}完成一小步 +10`,
    remember: a => `${ic('me')}记住了`, search_memory: () => `${ic('eye')}翻了翻记忆`, start_scene: () => `${ic('spark')}开始灵感场景`,
  };
  function toolChip(t) {
    const f = TOOL_LABEL[t.name];
    return f ? `<span class="tool-chip">${f(t.args || {})}</span>` : '';
  }

  function renderThread() {
    const box = $('#threadIn');
    if (!box) return;
    const msgs = S.messages || [];
    let html = '', lastDay = '';
    msgs.forEach(m => {
      const d = (m.created_at || '').slice(0, 10);
      if (d !== lastDay) { html += `<div class="day-sep"><span>${fmtDay(d)}</span></div>`; lastDay = d; }
      html += msgHtml(m);
    });
    if (!msgs.length) html = `<div class="thread-empty">${esc(agentName())}在这里。今天发生了什么？</div>`;
    html += guessCards();
    if (ui.scene) html += sceneCard();
    box.innerHTML = html;
    scrollThread(true);
  }

  function guessCards() {
    const g = (S.memories || []).filter(m => m.status === 'guess').slice(0, 2);
    return g.map(m => `<div class="card confirm" data-id="${m.id}">
      <p class="card-k">${esc(agentName())}猜的，对吗？</p>
      <p class="card-t">${esc(m.text)}</p>
      <div class="card-a"><button class="btn btn-ink btn-sm" data-act="mem" data-op="confirm" data-id="${m.id}">对，记下</button>
      <button class="btn btn-ghost btn-sm" data-act="mem" data-op="reject" data-id="${m.id}">不太对</button></div></div>`).join('');
  }

  function scrollThread(force) {
    const t = $('#thread');
    if (!t) return;
    const near = t.scrollHeight - t.scrollTop - t.clientHeight < 160;
    if (force || near) t.scrollTop = t.scrollHeight;
  }

  function renderDock() {
    const d = $('#dock');
    if (!d) return;
    const tips = S.counts.days <= 3 && !(S.messages || []).some(m => m.role === 'user');
    d.innerHTML = `
      ${tips ? `<div class="tips"><span>可以试试</span>
        <button data-act="say" data-t="今天有件小好事：">说一件小好事</button>
        <button data-act="say" data-t="帮我想一个今天能做的小步">要一个小步</button>
        <button data-act="scene" data-v="meditation">做 4 分钟冥想</button></div>` : ''}
      <form class="composer" id="composer">
        <button type="button" class="cmp-side" data-act="quick-good" title="记一条好消息" aria-label="记一条好消息">${star(1)}</button>
        <textarea id="input" rows="1" placeholder="跟${esc(agentName())}说说…" aria-label="消息" maxlength="2000"></textarea>
        <button type="button" class="cmp-side" data-act="quick-rest" title="今天想偷懒" aria-label="今天想偷懒">${ic('moon')}</button>
        <button type="submit" class="cmp-send" aria-label="发送" ${ui.busy ? 'disabled' : ''}>${ic('send')}</button>
      </form>`;
    const ta = $('#input');
    ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'; });
    ta.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('#composer').requestSubmit(); }
    });
    $('#composer').addEventListener('submit', e => { e.preventDefault(); send(ta.value); });
  }

  function setStatus(t) { const w = $('#whoStatus'); if (w) w.textContent = t; }
  function mood(id) { orbs.chat && orbs.chat.set(id); }

  async function send(text) {
    text = (text || '').trim();
    if (!text || ui.busy) return;
    ui.busy = true;
    const now = new Date().toISOString();
    S.messages.push({ id: 'tmp', role: 'user', content: text, meta: {}, created_at: localIso() });
    renderThread();
    $('#input').value = ''; $('#input').style.height = 'auto';
    $('.cmp-send').disabled = true;
    setStatus('正在想…');
    // live assistant bubble
    const box = $('#threadIn');
    const el = document.createElement('div');
    el.className = 'msg ai streaming';
    el.innerHTML = '<div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div><div class="msg-extra"></div>';
    box.appendChild(el);
    scrollThread(true);
    let reply = '', ctx = [], tools = [], gotText = false;
    try {
      const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                          body: JSON.stringify({ text }), credentials: 'same-origin' });
      if (r.status === 401) { showGate(); return; }
      if (!r.ok || !r.body) throw new Error('发送失败');
      const reader = r.body.getReader(), dec = new TextDecoder();
      let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const block = buf.slice(0, i); buf = buf.slice(i + 2);
          const ev = /^event: (.+)$/m.exec(block), dt = /^data: (.*)$/m.exec(block);
          if (!ev) continue;
          const data = dt ? JSON.parse(dt[1]) : {};
          const kind = ev[1];
          if (kind === 'mood') mood(data.id);
          else if (kind === 'context') { ctx = data.memories || []; if (ctx.length) setStatus(`想起了 ${ctx.length} 件事…`); }
          else if (kind === 'delta') {
            if (!gotText) { gotText = true; setStatus('正在回复…'); }
            reply += data.text;
            $('.bubble', el).innerHTML = fmtText(reply);
            scrollThread();
          } else if (kind === 'tool') {
            tools.push(data);
            $('.msg-extra', el).insertAdjacentHTML('beforeend', toolChip(data));
            onTool(data);
          } else if (kind === 'error') console.warn('[chat]', data.message);
        }
      }
    } catch (err) {
      if (!reply) $('.bubble', el).textContent = '连接断了一下。你刚才说的已经发出去了，可以再试一次。';
      mood('error');
    } finally {
      ui.busy = false;
      await refresh();          // pulls saved message ids, new memories (async extraction lands a moment later)
      renderView(); renderSide();
      setTimeout(async () => { await refresh(); if (ui.view === 'chat') { renderThread(); setStatus(statusLine()); } renderSide(); }, 4500);
    }
  }

  function localIso() {
    const d = new Date(), o = -d.getTimezoneOffset();
    return `${dkey(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}${o >= 0 ? '+' : '-'}${pad(Math.floor(Math.abs(o) / 60))}:${pad(Math.abs(o) % 60)}`;
  }

  function onTool(t) {
    const r = t.result || {};
    if (!r.ok) return;
    if (t.name === 'complete_step') { orbs.chat && orbs.chat.react('burst'); toast(`完成一小步 +${(r.xp || {}).gain || 10} 光点`); }
    if (t.name === 'log_good_news') { orbs.chat && orbs.chat.react('bounce'); }
    if (t.name === 'start_scene') { setTimeout(() => startScene(r.scene), 600); }
  }

  async function refresh() {
    try { S = await api('/api/bootstrap'); } catch { /* keep last */ }
  }
  /* ───────── scenes (灵感) — a real step machine on the server ───────── */
  async function startScene(id) {
    try {
      const d = await api('/api/scene/start', { scene: id });
      ui.scene = { run: d.run, step: d.step, title: d.scene.title };
      if (ui.view !== 'chat') go('chat'); else renderThread();
      mood('listening');
      setTimeout(() => { const i = $('#sceneInput'); i && i.focus(); }, 50);
    } catch (e) { toast(e.message); }
  }

  async function resumeScene() {
    // after a reload the server remembers the open run; ask it for the current step
    if (!ui.scene || ui.scene.step) return;
    try {
      const d = await api('/api/scene/start', { scene: ui.scene.run.scene, resume: ui.scene.run.id });
      ui.scene = { run: d.run, step: d.step, title: d.scene.title };
      renderThread();
    } catch { ui.scene = null; renderThread(); }
  }

  function sceneCard() {
    const sc = ui.scene;
    if (!sc.step) return `<div class="card scene-card"><p class="card-k">灵感场景</p><p class="card-t muted">正在接上次的进度…</p></div>`;
    const s = sc.step, title = sc.title || (S.scenes.find(x => x.id === sc.run.scene) || {}).title || '';
    const dots = Array.from({ length: s.total }, (_, i) => `<i class="${i < s.index ? 'on' : i === s.index ? 'cur' : ''}"></i>`).join('');
    const chips = (s.chips || []).map(c => `<button class="chip" data-act="scene-chip" data-v="${esc(c)}">${esc(c)}</button>`).join('');
    const timer = s.timer ? `<div class="breath" id="breath" data-in="${s.timer.inhale}" data-out="${s.timer.exhale}" data-rounds="${s.timer.rounds}">
        <div class="breath-ring"><span id="breathTxt">准备</span></div>
        <button class="btn btn-ghost btn-sm" data-act="breath-start">开始呼吸</button></div>` : '';
    const input = s.chips && !s.ph ? '' : `<form class="scene-form" data-form="scene">
        <input id="sceneInput" placeholder="${esc(s.ph || '写下你的回答')}" maxlength="200" autocomplete="off" aria-label="${esc(s.q)}">
        <button class="btn btn-ink btn-sm" type="submit">${s.index === s.total - 1 ? '完成' : '下一步'}</button></form>`;
    return `<div class="card scene-card" aria-live="polite">
      <div class="scene-head"><p class="card-k">${esc(title)}</p><span class="scene-dots" aria-label="第 ${s.index + 1} 步，共 ${s.total} 步">${dots}</span>
        <button class="icon-btn" data-act="scene-cancel" aria-label="先不做了">${ic('close')}</button></div>
      <p class="card-t">${esc(s.q)}</p>${timer}${chips ? `<div class="chips">${chips}</div>` : ''}${input}</div>`;
  }

  async function answerScene(text) {
    if (!ui.scene || !text) return;
    const s = ui.scene;
    try {
      const d = await api('/api/scene/answer', { run_id: s.run.id, text });
      S.messages.push({ id: 'tmp_q' + Date.now(), role: 'assistant', content: s.step.q, meta: { scene: true }, created_at: localIso() });
      S.messages.push({ id: 'tmp_a' + Date.now(), role: 'user', content: text, meta: { scene: true }, created_at: localIso() });
      if (!d.done) { ui.scene.step = d.step; renderThread(); setTimeout(() => { const i = $('#sceneInput'); i && i.focus(); }, 30); return; }
      ui.scene = null;
      mood('done'); orbs.chat && orbs.chat.react('burst');
      toast(d.wrote.map(w => w.label).join('、'));
      await refresh();
      renderThread(); renderSide();
      setTimeout(() => mood('idle'), 2400);
    } catch (e) { toast(e.message); }
  }

  let breathTimer = 0;
  function runBreath() {
    const b = $('#breath');
    if (!b) return;
    const inh = +b.dataset.in, exh = +b.dataset.out, rounds = +b.dataset.rounds;
    const ring = b.querySelector('.breath-ring'), txt = $('#breathTxt');
    b.querySelector('button').hidden = true;
    let r = 0, phase = 'in', left = inh;
    ring.style.setProperty('--dur', inh + 's'); ring.classList.add('in');
    txt.textContent = `吸 ${left}`;
    clearInterval(breathTimer);
    breathTimer = setInterval(() => {
      left--;
      if (left <= 0) {
        if (phase === 'in') { phase = 'out'; left = exh; ring.classList.remove('in'); ring.classList.add('out'); ring.style.setProperty('--dur', exh + 's'); }
        else { r++; if (r >= rounds) { clearInterval(breathTimer); txt.textContent = '做完了'; ring.classList.remove('out'); answerScene('做完了'); return; }
          phase = 'in'; left = inh; ring.classList.remove('out'); ring.classList.add('in'); ring.style.setProperty('--dur', inh + 's'); }
      }
      txt.textContent = `${phase === 'in' ? '吸' : '呼'} ${left} · ${r + 1}/${rounds}`;
    }, 1000);
  }

  /* ───────── side panel (today) ───────── */
  function renderSide() {
    const side = $('#side');
    if (!side || !S) return;
    const todo = (S.steps || []).filter(s => s.status === 'todo');
    const today = dkey();
    const recToday = (S.records || []).filter(r => (r.day || '').slice(0, 10) === today);
    const nextAct = (S.activity || [])[0];
    side.innerHTML = `
      <section class="side-sec">
        <h3>今天的一小步</h3>
        ${todo.length ? todo.slice(0, 2).map(s => `<div class="side-step">
            <button class="tick" data-act="step-done" data-id="${s.id}" aria-label="完成：${esc(s.title)}">${ic('check')}</button>
            <div><p>${esc(s.title)}</p>${s.why ? `<small>${esc(clip(s.why, 30))}</small>` : ''}</div></div>`).join('')
          : `<p class="muted small">还没有。跟${esc(agentName())}聊聊，或者去灵感区抽一张卡。</p>`}
      </section>
      <section class="side-sec">
        <h3>今天</h3>
        <div class="side-quick">
          <button class="btn btn-ghost btn-sm" data-act="quick-good">${star(1)}记好消息</button>
          <button class="btn btn-ghost btn-sm" data-act="quick-rest">${ic('moon')}今天偷懒</button>
        </div>
        ${recToday.length ? `<ul class="side-recs">${recToday.slice(0, 3).map((r, i) => `<li>${r.type === 'good' ? star(i) : r.type === 'rest' ? ic('moon') : ic('spark')}<span>${esc(clip(r.text, 26))}</span></li>`).join('')}</ul>` : ''}
      </section>
      <section class="side-sec">
        <h3>光点</h3>
        <div class="xp"><div class="xp-row"><b>${esc(S.rank.rank)}</b><span class="muted">${S.rank.xp}${S.rank.next_at ? ' / ' + S.rank.next_at : ''}</span></div>
          <div class="xp-bar"><i style="width:${S.rank.next_at ? Math.min(100, Math.round((S.rank.xp - S.rank.floor) / (S.rank.next_at - S.rank.floor) * 100)) : 100}%"></i></div>
          <small class="muted">${S.rank.next_rank ? `再完成 ${Math.ceil((S.rank.next_at - S.rank.xp) / 10)} 个小步，成为「${S.rank.next_rank}」` : '已经是最亮的星光'}</small></div>
      </section>
      <section class="side-sec side-act">
        <h3>${esc(agentName())}在做什么</h3>
        <p class="small">${S.proactive.ok ? '今天还会来找你一次' : esc(S.proactive.reason)}</p>
        ${nextAct ? `<p class="small muted">上一件事：${esc(clip(nextAct.text, 28))}</p>` : ''}
        <button class="link small" data-act="activity">查看全部记录</button>
      </section>`;
  }
  /* ───────── 画像 ───────── */
  const KIND_LABEL = { intent: '愿景', identity: '我是', preference: '偏好', boundary: '边界', insight: '新发现', event: '经历', good_news: '好事' };
  const SRC_LABEL = m => m.status === 'guess' ? '猜的，待确认' : m.source === 'confirmed' ? '你确认过' : m.source === 'onboarding' ? '建档时说的' : m.source && m.source.startsWith('scene') ? '灵感场景里说的' : '聊天里说的';

  function renderMe() {
    const p = P(), mems = S.memories || [];
    const guesses = mems.filter(m => m.status === 'guess');
    const facts = mems.filter(m => m.status === 'active');
    const groups = {};
    facts.forEach(m => (groups[m.kind] = groups[m.kind] || []).push(m));
    const order = ['intent', 'identity', 'insight', 'preference', 'boundary', 'event', 'good_news'];
    $('#stage').innerHTML = `<div class="page">
      <header class="page-head"><h1>画像</h1><p class="muted">${esc(agentName())}对你的了解，都在这里。哪里不对，直接改。</p></header>
      <section class="portrait-hero">
        <span class="portrait-orb"><span id="meOrb"></span></span>
        <div>
          <p class="portrait-name">${esc(p.nickname || '你')}<button class="link small" data-act="edit-profile">编辑</button></p>
          <p class="portrait-intent">想靠近「${esc(p.intent_primary || '还没说')}」</p>
          ${p.intent_why ? `<p class="muted">因为${esc(p.intent_why)}</p>` : ''}
          <div class="tags">${(p.traits || []).map(t => `<span class="tag">${esc(t)}</span>`).join('')}
            ${p.schedule_hint ? `<span class="tag">${esc(p.schedule_hint)}</span>` : ''}
            ${p.mbti_hint ? `<span class="tag tag-fun" title="只是好玩">${esc(p.mbti_hint)}</span>` : ''}</div>
          ${(p.boundaries || []).filter(b => b !== '无').length ? `<p class="small muted">${esc(agentName())}会注意：${esc(p.boundaries.filter(b => b !== '无').join('、'))}</p>` : ''}
        </div>
      </section>
      ${guesses.length ? `<section class="sec"><h2>${esc(agentName())}的猜测 <small class="muted">确认后才会算数</small></h2>
        ${guesses.map(m => `<div class="mem guess"><p>${esc(m.text)}</p><div class="mem-a">
          <button class="btn btn-ink btn-sm" data-act="mem" data-op="confirm" data-id="${m.id}">对</button>
          <button class="btn btn-ghost btn-sm" data-act="mem" data-op="reject" data-id="${m.id}">不对</button></div></div>`).join('')}</section>` : ''}
      <section class="sec"><div class="sec-head"><h2>记忆 <small class="muted">${facts.length} 条</small></h2>
        <button class="btn btn-ghost btn-sm" data-act="mem-add">${ic('plus')}自己写一条</button></div>
        ${order.filter(k => groups[k]).map(k => `<h3 class="mem-group">${KIND_LABEL[k]}</h3>
          ${groups[k].map(m => `<div class="mem" data-id="${m.id}"><div><p>${esc(m.text)}</p>
            <small class="muted">${SRC_LABEL(m)} · ${fmtDay(m.created_at)}${m.hits ? ` · 被想起 ${m.hits} 次` : ''}</small></div>
            <div class="mem-a"><button class="link small" data-act="mem-edit" data-id="${m.id}">改</button>
            <button class="link small" data-act="mem" data-op="forget" data-id="${m.id}">忘掉</button></div></div>`).join('')}`).join('')
          || `<p class="muted">还没有记忆。多聊几句，${esc(agentName())}会慢慢记住重要的事。</p>`}
      </section>
      <p class="fine">记忆只存在你自己的数据空间里，别的账号看不到。<button class="link" data-act="export">导出我的全部数据</button></p>
    </div>`;
    orbs.me = Orb.mount($('#meOrb'), { size: 96, hue: p.agent_hue, emotion: guesses.length ? '03' : '19' });
  }

  /* ───────── 计划 ───────── */
  function renderPlan() {
    const steps = S.steps || [], todo = steps.filter(s => s.status === 'todo'), done = steps.filter(s => s.status === 'done');
    const r = S.rank;
    const BADGE = { first_step: '第一步', first_good: '第一条好消息', week_one: '一周', seven_steps: '七步' };
    $('#stage').innerHTML = `<div class="page">
      <header class="page-head"><h1>计划</h1><p class="muted">不是待办清单。每天只要一小步，${esc(agentName())}陪你做。</p></header>
      <section class="rank-card">
        <div><p class="rank-name">${esc(r.rank)}</p><p class="muted small">${r.xp} 光点${r.next_rank ? ` · 距「${r.next_rank}」还差 ${r.next_at - r.xp}` : ''}</p></div>
        <div class="rank-path">${['萌芽', '微光', '小光', '星光'].map(n => `<span class="${n === r.rank ? 'cur' : ''}">${n}</span>`).join('<i></i>')}</div>
        ${(P().badges || []).length ? `<div class="badges">${P().badges.map(b => `<span class="badge">${star(b.length)}${BADGE[b] || b}</span>`).join('')}</div>` : ''}
      </section>
      <section class="sec"><div class="sec-head"><h2>正在做</h2></div>
        ${todo.map(s => `<div class="step"><button class="tick" data-act="step-done" data-id="${s.id}" aria-label="完成：${esc(s.title)}">${ic('check')}</button>
          <div class="step-b"><p>${esc(s.title)}</p>${s.why ? `<small class="muted">${esc(s.why)}</small>` : ''}</div>
          <button class="link small" data-act="step-drop" data-id="${s.id}">先放一放</button></div>`).join('')
          || `<p class="muted">现在没有进行中的小步。</p>`}
        <form class="add-step" data-form="add-step"><input name="title" maxlength="40" placeholder="加一个 5 分钟就能开始的小步" aria-label="新的小步">
          <button class="btn btn-ink btn-sm" type="submit">加入</button></form>
        <button class="link small" data-act="ask-step">让${esc(agentName())}帮我想一个</button>
      </section>
      ${done.length ? `<section class="sec"><h2>走过的路 <small class="muted">${done.length} 步</small></h2>
        <ol class="path">${done.map(s => `<li><span class="path-dot"></span><div><p>${esc(s.title)}</p><small class="muted">${fmtDay(s.done_at)}</small></div></li>`).join('')}</ol></section>` : ''}
    </div>`;
  }

  /* ───────── 灵感 ───────── */
  const METHOD = [['澄清', '说清想要什么'], ['信念', '我配得上'], ['感受', '提前感受实现'], ['行动', '今天一小步'],
                  ['感恩', '看见已有的'], ['释放', '放下执念'], ['见证', '看见变化']];
  function renderSpark() {
    $('#stage').innerHTML = `<div class="page">
      <header class="page-head"><h1>灵感</h1><p class="muted">显化七步，拆成几分钟就能做完的小练习。做完会自动记进画像或计划。</p></header>
      <ol class="method" aria-label="显化七步">${METHOD.map(([a, b]) => `<li><b>${a}</b><small>${b}</small></li>`).join('')}</ol>
      <section class="scenes">${S.scenes.map(sc => `<button class="scene" data-act="scene" data-v="${sc.id}">
        <span class="scene-stage">${esc(sc.stage)}</span>
        <b>${esc(sc.title)}</b><span class="muted small">${esc(sc.desc)}</span>
        <span class="scene-meta">${sc.minutes} 分钟 · ${sc.steps} 步</span></button>`).join('')}</section>
      <section class="sec"><h2>${esc(agentName())}多久来找你一次</h2>
        <div class="seg" role="radiogroup">${[['more', '多一点'], ['normal', '刚好'], ['less', '少一点'], ['off', '先别打扰']].map(([v, l]) =>
          `<button role="radio" aria-checked="${P().proactive === v}" data-act="freq" data-v="${v}">${l}</button>`).join('')}</div>
        <p class="small muted">${{ more: '空闲 12 小时后来问候一次', normal: '空闲 24 小时后来问候一次', less: '空闲两三天后再来', off: '不主动发消息' }[P().proactive || 'normal']}，23:00–08:00 不打扰。</p>
        <button class="link small" data-act="proactive-now">现在演示一次主动消息</button>
      </section>
    </div>`;
  }

  /* ───────── 蜕变 ───────── */
  function renderBloom() {
    const recs = S.records || [];
    const f = ui.recFilter;
    const shown = recs.filter(r => f === 'all' || r.type === f);
    const c = S.counts;
    $('#stage').innerHTML = `<div class="page">
      <header class="page-head"><h1>蜕变</h1><p class="muted">这 ${c.days} 天里，你收集了 ${c.good} 条好消息，完成了 ${c.done} 个小步${c.rest ? `，也给自己放了 ${c.rest} 天假` : ''}。</p></header>
      <section class="strip-wrap"><div class="strip" aria-label="最近 30 天">${stripCells()}</div>
        <p class="legend small muted">${star(0)} 好消息　${ic('moon')} 偷懒日　<i class="lg-step"></i> 完成小步</p></section>
      <section class="report-cta">
        <button class="report-btn" data-act="report" data-days="10"><b>10 天蜕变报告</b><span class="muted small">${c.days >= 10 ? '可以看了' : `还差 ${10 - c.days} 天，先看看草稿`}</span></button>
        <button class="report-btn" data-act="report" data-days="30"><b>30 天蜕变报告</b><span class="muted small">${c.days >= 30 ? '可以看了' : `还差 ${30 - c.days} 天`}</span></button>
      </section>
      <section class="sec"><div class="sec-head"><h2>记录</h2>
        <div class="seg seg-sm">${[['all', '全部'], ['good', '好消息'], ['find', '新发现'], ['rest', '偷懒日']].map(([v, l]) =>
          `<button aria-pressed="${f === v}" data-act="rec-filter" data-v="${v}">${l}</button>`).join('')}</div></div>
        <form class="add-step" data-form="add-good"><input name="text" maxlength="200" placeholder="今天的一件小好事" aria-label="记一条好消息">
          <button class="btn btn-ink btn-sm" type="submit">${star(1)}记下</button></form>
        <ul class="recs">${shown.map((r, i) => `<li class="rec rec-${r.type}">${r.type === 'good' ? star(i) : r.type === 'rest' ? ic('moon') : ic('spark')}
          <div><p>${esc(r.text)}</p><small class="muted">${fmtDay(r.day)}</small></div></li>`).join('') || '<li class="muted">还没有记录。</li>'}</ul>
      </section></div>`;
  }

  function stripCells() {
    const recs = S.records || [], done = (S.steps || []).filter(s => s.done_at);
    const out = [];
    for (let i = 29; i >= 0; i--) {
      const d = new Date(); d.setDate(d.getDate() - i);
      const k = dkey(d);
      const g = recs.some(r => r.type === 'good' && (r.day || '').startsWith(k));
      const rest = recs.some(r => r.type === 'rest' && (r.day || '').startsWith(k));
      const st = done.some(s => s.done_at.startsWith(k));
      out.push(`<span class="cell${st ? ' has-step' : ''}${i === 0 ? ' today' : ''}" title="${fmtDay(k)}">${g ? star(i) : rest ? ic('moon') : ''}</span>`);
    }
    return out.join('');
  }
  /* ───────── 蜕变报告 (modal) ───────── */
  async function openReport(days) {
    ui.reportDays = days;
    openLayer('modal', `<div class="report-wrap"><div class="report-loading"><span id="repOrb"></span><p>${esc(agentName())}正在翻这 ${days} 天的记录…</p></div></div>`);
    const lo = Orb.mount($('#repOrb'), { size: 72, hue: P().agent_hue, emotion: '37' });
    try {
      const d = await api('/api/report?days=' + days);
      if (d.empty) {
        $('#modal').innerHTML = `<div class="report-wrap"><div class="report-empty"><p>这 ${days} 天还没有记录。</p>
          <p class="muted">记几条好消息、完成一两个小步，再回来看。</p><button class="btn btn-ink" data-act="layer-close">好</button></div></div>`;
        return;
      }
      ui.report = d;
      renderReport();
    } catch (e) { toast(e.message); closeLayer(); }
  }

  function renderReport() {
    const d = ui.report, f = d.facts, L = d.letter || {};
    $('#modal').innerHTML = `<div class="report-wrap">
      <div class="report" id="reportCard">
        <div class="report-stage"><span id="repOrb2"></span></div>
        <p class="report-k">${f.days} 天蜕变报告 · ${esc(f.agent)}写给${esc(f.name || '你')}</p>
        <h2 class="report-title">${esc(L.title || `这 ${f.days} 天的你`)}</h2>
        <p class="report-letter">${esc(L.text || '')}</p>
        ${f.surprise ? `<div class="surprise"><span>${star(3)}你可能没注意到</span><p>${esc(f.surprise)}</p></div>` : ''}
        <div class="report-nums">
          <div><b>${f.good}</b><small>好消息</small></div><div><b>${f.done}</b><small>小步</small></div>
          <div><b>${f.rest}</b><small>偷懒日</small></div><div><b>${f.xp}</b><small>光点</small></div></div>
        ${f.done_samples.length ? `<div class="report-list"><small class="muted">走过的几步</small>${f.done_samples.map(s => `<p>${ic('check')}${esc(s)}</p>`).join('')}</div>` : ''}
        ${f.intent ? `<p class="report-foot">还在靠近「${esc(f.intent)}」</p>` : ''}
        <p class="report-brand">显伴 · manifest.noryx.cn</p>
      </div>
      <div class="report-actions">
        <button class="btn btn-ink" data-act="report-png">${ic('share')}保存为图片</button>
        <button class="btn btn-ghost" data-act="report-copy">复制文字</button>
        <button class="btn btn-ghost" data-act="layer-close">关闭</button>
      </div>
      <p class="fine center">图片在你的浏览器里生成，不会上传。</p></div>`;
    const o = Orb.mount($('#repOrb2'), { size: 110, hue: P().agent_hue, emotion: '10' });
    setTimeout(() => o.react('burst'), 400);
  }

  async function reportPng() {
    const el = $('#reportCard');
    if (!window.html2canvas) { toast('图片组件还在加载，稍等再试'); return; }
    try {
      const canvas = await html2canvas(el, { backgroundColor: '#ffffff', scale: 2, useCORS: false, logging: false });
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = `显伴-${ui.reportDays}天蜕变报告.png`;
      a.click();
      toast('已保存');
    } catch (e) { toast('生成失败：' + e.message); }
  }

  function reportText() {
    const d = ui.report, f = d.facts, L = d.letter || {};
    return `${L.title || ''}\n\n${L.text || ''}\n\n${f.surprise ? '你可能没注意到：' + f.surprise + '\n\n' : ''}好消息 ${f.good} · 小步 ${f.done} · 偷懒日 ${f.rest}\n—— 显伴 · ${f.days} 天蜕变报告`;
  }

  /* ───────── drawers / modals ───────── */
  function openLayer(kind, html) {
    ui.layer = kind;
    $('#scrim').hidden = false;
    const el = $('#' + kind);
    el.innerHTML = html; el.hidden = false;
    requestAnimationFrame(() => el.classList.add('open'));
    const f = el.querySelector('input, textarea, button');
    f && f.focus({ preventScroll: true });
  }
  function closeLayer() {
    ['drawer', 'modal'].forEach(k => { const el = $('#' + k); el.classList.remove('open'); el.hidden = true; el.innerHTML = ''; });
    $('#scrim').hidden = true; ui.layer = null;
    clearInterval(breathTimer);
  }

  function drawerActivity() {
    const acts = S.activity || [];
    const plan = [];
    const h = new Date().getHours();
    if (S.proactive.ok) plan.push(['稍后', '主动来问问你今天怎么样']);
    else plan.push(['等待', S.proactive.reason]);
    if (h < 23) plan.push(['每次聊完', '整理对话，把重要的事记进记忆；猜的会先问你']);
    openLayer('drawer', `<header class="drawer-h"><h2 id="drawerTitle">${esc(agentName())}在做什么</h2>
        <button class="icon-btn" data-act="layer-close" aria-label="关闭">${ic('close')}</button></header>
      <div class="drawer-b">
        <div class="drawer-orb"><span id="actOrb"></span></div>
        <h3>接下来</h3>${plan.map(([t, x]) => `<div class="act"><b>${esc(t)}</b><p>${esc(x)}</p></div>`).join('')}
        <button class="btn btn-ghost btn-sm" data-act="proactive-now">现在主动发一条（演示）</button>
        <h3>做过的</h3>${acts.map(a => `<div class="act"><b>${fmtDay(a.at)} ${fmtTime(a.at)}</b><p>${esc(a.text)}</p></div>`).join('') || '<p class="muted">还没有。</p>'}
        <h3>约定</h3>
        <ul class="pact"><li>你可以没有结论，也可以只是想被听见。</li><li>偷懒不会清零任何东西。</li>
          <li>${esc(agentName())}猜的事，你说对才算。</li><li>23:00–08:00 不会主动打扰你。</li></ul>
      </div>`);
    Orb.mount($('#actOrb'), { size: 84, hue: P().agent_hue, emotion: '35' });
  }

  function drawerContext(mid) {
    const m = (S.messages || []).find(x => x.id === mid);
    const ids = (m && m.meta && m.meta.memories) || [];
    const mems = ids.map(id => (S.memories || []).find(x => x.id === id)).filter(Boolean);
    const tools = (m && m.meta && m.meta.tools) || [];
    openLayer('drawer', `<header class="drawer-h"><h2 id="drawerTitle">这句回复参考了什么</h2>
        <button class="icon-btn" data-act="layer-close" aria-label="关闭">${ic('close')}</button></header>
      <div class="drawer-b">
        <p class="muted small">回复前，${esc(agentName())}在你的记忆里检索了和这句话相关的内容（中文二元分词 + BM25，结合时间远近和记忆类型排序）。</p>
        ${mems.map(x => `<div class="mem${x.status === 'guess' ? ' guess' : ''}"><div><p>${esc(x.text)}</p><small class="muted">${KIND_LABEL[x.kind] || ''} · ${SRC_LABEL(x)}</small></div></div>`).join('')
          || `<p class="muted">（这些记忆后来被改过或忘掉了）</p>`}
        ${tools.length ? `<h3>还做了</h3>${tools.map(t => `<p class="tool-line">${toolChip(t)}</p>`).join('')}` : ''}
      </div>`);
  }

  function drawerSettings() {
    const p = P(), u = S.user;
    const FREQ = [['more', '多一点', '半天没聊就来找你'], ['normal', '刚好', '一天没聊来问一句'], ['less', '少一点', '两三天来一次'], ['off', '先别打扰', '不主动发消息']];
    const HUES = ['#8a7dff', '#ff8fb1', '#5c6b7a', '#3fbf9f', '#ffa465', '#5b9dff'];
    openLayer('drawer', `<header class="drawer-h"><h2 id="drawerTitle">设置</h2>
        <button class="icon-btn" data-act="layer-close" aria-label="关闭">${ic('close')}</button></header>
      <div class="drawer-b">
        <h3>账号</h3>
        <p>${u.kind === 'guest' ? '体验账号（关掉浏览器的 cookie 就找不回了）' : '已登录：' + esc(u.username)}</p>
        ${u.kind === 'guest' ? '<button class="btn btn-ink btn-sm" data-act="show-auth" data-mode="register">注册，保留这些记录</button>' : ''}
        <h3>伙伴</h3>
        <label class="field">名字<input id="setName" value="${esc(p.agent_name)}" maxlength="12"></label>
        <div class="hues" role="radiogroup" aria-label="颜色">${HUES.map(h => `<button class="hue${h === p.agent_hue ? ' on' : ''}" style="--c:${h}" data-act="set-hue" data-v="${h}" role="radio" aria-checked="${h === p.agent_hue}" aria-label="${h}"></button>`).join('')}</div>
        <h3>主动消息</h3>
        <div class="freq">${FREQ.map(([v, l, d]) => `<button class="freq-o${p.proactive === v ? ' on' : ''}" data-act="set-freq" data-v="${v}"><b>${l}</b><small>${d}</small></button>`).join('')}</div>
        <p class="small muted">23:00–08:00 永远不会主动打扰。</p>
        <h3>数据</h3>
        <button class="link" data-act="export">导出我的全部数据（JSON）</button>
        <h3>关于</h3>
        <p class="small muted">小光的形象基于 Emotion Ball 表情引擎（sam70361/aora-bot），按其社区许可仅用于非商业演示；正式产品会换成自有形象。</p>
        <button class="btn btn-ghost btn-sm" data-act="logout">退出登录</button>
      </div>`);
  }

  function modalMemEdit(m) {
    openLayer('modal', `<form class="sheet" data-form="mem-edit" data-id="${m ? m.id : ''}">
      <h2>${m ? '改一下这条记忆' : '自己写一条'}</h2>
      <textarea name="text" rows="3" maxlength="120" placeholder="比如：和熟悉的人在一起时更敢表达">${esc(m ? m.text : '')}</textarea>
      <div class="sheet-a"><button type="button" class="btn btn-ghost" data-act="layer-close">取消</button><button class="btn btn-ink" type="submit">保存</button></div></form>`);
  }

  function modalProfile() {
    const p = P();
    openLayer('modal', `<form class="sheet" data-form="profile">
      <h2>编辑画像</h2>
      <label class="field">怎么称呼你<input name="nickname" value="${esc(p.nickname)}" maxlength="12"></label>
      <label class="field">现在最想靠近<input name="intent_primary" value="${esc(p.intent_primary)}" maxlength="40"></label>
      <label class="field">为什么重要<input name="intent_why" value="${esc(p.intent_why)}" maxlength="60"></label>
      <label class="field">别人常觉得你是（用顿号分隔）<input name="traits" value="${esc((p.traits || []).join('、'))}"></label>
      <label class="field">别碰的（用顿号分隔）<input name="boundaries" value="${esc((p.boundaries || []).join('、'))}"></label>
      <div class="sheet-a"><button type="button" class="btn btn-ghost" data-act="layer-close">取消</button><button class="btn btn-ink" type="submit">保存</button></div></form>`);
  }

  function modalQuick(type) {
    openLayer('modal', `<form class="sheet" data-form="quick" data-type="${type}">
      <h2>${type === 'good' ? '记一条好消息' : '今天想偷懒'}</h2>
      <p class="muted small">${type === 'good' ? '再小也算。' : '偷懒不会清零任何东西。'}</p>
      <textarea name="text" rows="2" maxlength="200" placeholder="${type === 'good' ? '比如：室友帮我带了奶茶' : '想说点什么吗？不写也行'}"></textarea>
      <div class="sheet-a"><button type="button" class="btn btn-ghost" data-act="layer-close">取消</button><button class="btn btn-ink" type="submit">${type === 'good' ? '收下' : '今天就休息'}</button></div></form>`);
  }
  /* ───────── actions ───────── */
  async function patchProfile(patch, msg) {
    try { S = { ...S, ...(await api('/api/profile', patch)) }; applyHue(); if (msg) toast(msg); return true; }
    catch (e) { toast(e.message); return false; }
  }
  async function memOp(op, id, text) {
    try {
      const d = await api('/api/memory', { action: op, id, text });
      S.memories = d.memories; S.counts = d.counts;
      toast({ confirm: '记下了', reject: '好，删掉了', forget: '忘掉了', edit: '改好了', add: '写进画像了' }[op] || '好');
      if (op === 'confirm') mood('happy');
      renderView(); renderSide();
    } catch (e) { toast(e.message); }
  }
  async function stepOp(op, id, title) {
    try {
      const d = await api('/api/step', { action: op, id, title });
      S = { ...S, ...d };
      if (op === 'done') { toast(`完成一小步 +${(d.xp || {}).gain || 10} 光点`); orbs.chat && orbs.chat.react('burst'); orbs.me && orbs.me.react('burst'); }
      renderView(); renderSide();
    } catch (e) { toast(e.message); }
  }
  async function addRecord(type, text) {
    try {
      const d = await api('/api/record', { type, text });
      S = { ...S, ...d };
      toast(type === 'good' ? `收下了，第 ${S.counts.good} 条好消息` : '今天就好好休息。什么都没有清零。');
      if (type === 'good') { orbs.chat && orbs.chat.react('bounce'); mood('happy'); }
      else mood('tired');
      renderView(); renderSide();
      setTimeout(() => mood('idle'), 2500);
    } catch (e) { toast(e.message); }
  }

  const ACT = {
    'guest': async (el) => {
      el.disabled = true;
      try { await api('/api/auth/guest', {}); await boot(); }
      catch (e) { toast(e.message); el.disabled = false; }
    },
    'show-auth': (el) => { closeLayer(); if ($('#gate').hidden) { $('#app').hidden = true; $('#gate').hidden = false; } showAuth(el.dataset.mode || 'login'); },
    'toggle-auth': () => showAuth(authMode === 'login' ? 'register' : 'login'),
    'hide-auth': () => { if (S && S.user) { $('#gate').hidden = true; $('#app').hidden = false; return; } $('#authForm').hidden = true; $('.gate-hero').hidden = false; },
    'logout': async () => { await api('/api/auth/logout', {}).catch(() => {}); S = null; closeLayer(); showGate(); },

    'ob-pick': (el) => {
      const q = S.onboarding[ui.ob.i], v = el.dataset.v, a = ui.ob.a;
      if (q.type.startsWith('multi')) {
        let cur = (a[q.key] || []).slice();
        if (v === '无') cur = cur.includes('无') ? [] : ['无'];
        else { cur = cur.filter(x => x !== '无'); cur = cur.includes(v) ? cur.filter(x => x !== v) : cur.concat(v); }
        if (q.max && cur.length > q.max) { toast(`最多选 ${q.max} 个`); return; }
        a[q.key] = cur; renderOb();
      } else {
        a[q.key] = v;
        if (q.key === 'agent_avatar_id' || q.type === 'single') { renderOb(); setTimeout(obNext, reduceMotion ? 0 : 260); }
        else renderOb();
      }
    },
    'ob-next': () => obNext(),
    'ob-back': () => { obCollect(); ui.ob.i = Math.max(0, ui.ob.i - 1); renderOb(); },
    'ob-skip': () => { const q = S.onboarding[ui.ob.i]; ui.ob.a[q.key] = ''; ui.ob.i++; renderOb(); },

    'nav': (el) => go(el.dataset.v),
    'settings': () => drawerSettings(),
    'activity': () => drawerActivity(),
    'ctx': (el) => drawerContext(el.dataset.id),
    'layer-close': () => closeLayer(),

    'say': (el) => { const t = el.dataset.t; const i = $('#input'); if (!i) return; i.value = t; i.focus(); if (!t.endsWith('：')) send(t); },
    'mem': (el) => memOp(el.dataset.op, el.dataset.id),
    'mem-add': () => modalMemEdit(null),
    'mem-edit': (el) => modalMemEdit((S.memories || []).find(m => m.id === el.dataset.id)),
    'edit-profile': () => modalProfile(),
    'export': async () => {
      try {
        const d = await api('/api/export');
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([JSON.stringify(d, null, 1)], { type: 'application/json' }));
        a.download = `显伴-我的数据-${dkey()}.json`; a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      } catch (e) { toast(e.message); }
    },

    'step-done': (el) => stepOp('done', el.dataset.id),
    'step-drop': (el) => stepOp('drop', el.dataset.id),
    'ask-step': () => { go('chat'); setTimeout(() => send('帮我想一个今天能做的小步'), 50); },

    'quick-good': () => modalQuick('good'),
    'quick-rest': () => modalQuick('rest'),
    'rec-filter': (el) => { ui.recFilter = el.dataset.v; renderView(); },

    'scene': (el) => startScene(el.dataset.v),
    'scene-chip': (el) => answerScene(el.dataset.v),
    'scene-cancel': async () => {
      try { await api('/api/scene/cancel', {}); } catch { /* ignore */ }
      ui.scene = null; renderThread(); mood('idle');
    },
    'breath-start': () => runBreath(),

    'freq': async (el) => { if (await patchProfile({ proactive: el.dataset.v }, '好，按这个频率来')) renderView(); },
    'set-freq': async (el) => { if (await patchProfile({ proactive: el.dataset.v })) drawerSettings(); },
    'set-hue': async (el) => {
      if (await patchProfile({ agent_hue: el.dataset.v })) { drawerSettings(); renderShell(); }
    },
    'proactive-now': async () => {
      try {
        const d = await api('/api/proactive/now', {});
        await refresh(); closeLayer(); go('chat'); renderChat(); renderSide();
        if (d.sent) { mood('happy'); orbs.chat && orbs.chat.react('bounce'); }
        toast(d.sent ? `${agentName()}主动发来一条消息` : d.reason);
      } catch (e) { toast(e.message); }
    },

    'report': (el) => openReport(+el.dataset.days),
    'report-png': () => reportPng(),
    'report-copy': async () => {
      try { await navigator.clipboard.writeText(reportText()); toast('已复制'); }
      catch { toast('浏览器不允许复制，可以手动选中文字'); }
    },
  };

  document.addEventListener('click', e => {
    const el = e.target.closest('[data-act]');
    if (!el || el.disabled) return;
    const fn = ACT[el.dataset.act];
    if (fn) { e.preventDefault(); fn(el, e); }
  });
  $('#scrim').addEventListener('click', closeLayer);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && ui.layer) closeLayer(); });

  document.addEventListener('submit', async e => {
    const f = e.target.closest('[data-form]');
    if (!f) return;
    e.preventDefault();
    const kind = f.dataset.form, v = n => (f.elements[n] ? f.elements[n].value.trim() : '');
    if (kind === 'chat') { const t = v('text'); f.elements.text.value = ''; autosize(f.elements.text); send(t); }
    else if (kind === 'scene') { const t = $('#sceneInput').value.trim(); if (t) answerScene(t); else toast('写一句也行'); }
    else if (kind === 'add-step') { const t = v('title'); if (!t) return; f.reset(); stepOp('add', null, t); }
    else if (kind === 'add-good') { const t = v('text'); if (!t) return; f.reset(); addRecord('good', t); }
    else if (kind === 'quick') { closeLayer(); addRecord(f.dataset.type, v('text') || (f.dataset.type === 'good' ? '' : '今天想休息')); }
    else if (kind === 'mem-edit') {
      const t = v('text'); if (!t) { toast('内容不能为空'); return; }
      closeLayer(); memOp(f.dataset.id ? 'edit' : 'add', f.dataset.id || undefined, t);
    } else if (kind === 'profile') {
      const split = s => s.split(/[、,，\s]+/).map(x => x.trim()).filter(Boolean);
      const ok = await patchProfile({ nickname: v('nickname'), intent_primary: v('intent_primary'), intent_why: v('intent_why'),
        traits: split(v('traits')), boundaries: split(v('boundaries')) }, '画像更新了');
      if (ok) { closeLayer(); renderView(); }
    }
  });

  document.addEventListener('change', async e => {
    if (e.target.id === 'setName') {
      const name = e.target.value.trim();
      if (name && await patchProfile({ agent_name: name }, `以后叫我「${name}」`)) renderShell();
    }
  });

  function autosize(t) { if (!t) return; t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 160) + 'px'; }
  document.addEventListener('input', e => { if (e.target.id === 'input') autosize(e.target); });
  document.addEventListener('keydown', e => {
    if (e.target.id === 'input' && e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); e.target.form.requestSubmit(); }
  });

  /* ───────── boot ───────── */
  async function boot() {
    try {
      S = await api('/api/bootstrap');
    } catch (e) {
      if (e.status !== 401) { toast('连不上服务器：' + e.message, 5000); }
      showGate();
      return;
    }
    if (!S.profile.onboarded) showOnboard();
    else { enterApp(); resumeScene(); }
  }
  boot();
})();

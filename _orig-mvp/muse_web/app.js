/* manifest · Muse 式个人伙伴原型
   纯前端演示：状态保存在 localStorage，伙伴回复由本地脚本生成，不调用模型。 */
'use strict';
(() => {
  const KEY = 'manifest-muse-proto-v1';

  const HUES = [
    { id: 'mist', name: '晨雾蓝', c: '#7fa8ff' },
    { id: 'mint', name: '薄荷', c: '#4fcb98' },
    { id: 'apricot', name: '杏子', c: '#ffa465' },
    { id: 'lilac', name: '丁香', c: '#ad8cff' },
  ];
  const DEPTHS = [
    { id: 's', label: '1–5 分钟', desc: '几个轻问题，先认识一下' },
    { id: 'm', label: '5–15 分钟', desc: '多聊一点，画像更具体' },
    { id: 'l', label: '15–30 分钟', desc: '慢慢聊，适合今天有空' },
  ];
  const TYPE_LABEL = { good: '好消息', step: '小行动', rest: '偷懒日', find: '新发现' };
  const SOURCE_LABEL = { self: '你说的', guess: '伙伴猜的，等你确认', confirmed: '你确认过' };
  const FREQ = [
    { id: 'more', label: '多一点', note: '早上一个问题，中午一句提醒，晚上 8 点聊聊收获。' },
    { id: 'normal', label: '刚好', note: '早上带来一个问题，晚上 8 点问问今天的收获。' },
    { id: 'less', label: '少一点', note: '每两三天来找你一次，只说值得说的。' },
    { id: 'off', label: '先别打扰', note: '不主动发消息。你来找我时，我都在。' },
  ];
  const DISCOVERY = [
    '最近哪件小事，让你不知不觉做了很久？',
    '别人常找你帮什么忙？那可能是你没注意到的长处。',
    '这周有没有一个瞬间，你觉得比以前的自己好一点？',
    '什么事情做完会累，但你还是觉得很满足？',
    '如果明天完全自由，你会先做什么？',
    '最近一次改变主意，是因为什么？',
    '你羡慕过谁？羡慕的那一点，也许正是你想要的方向。',
  ];

  /* ───────── utils ───────── */
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const uid = () => Math.random().toString(36).slice(2, 9);
  const pad = n => String(n).padStart(2, '0');
  const dkey = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const parseKey = k => { const [y, m, d] = k.split('-').map(Number); return new Date(y, m - 1, d); };
  const daysBetween = (a, b) => Math.round((parseKey(b) - parseKey(a)) / 864e5);
  const fmtDay = k => {
    if (k === dkey()) return '今天';
    if (k === dkey(addDays(new Date(), -1))) return '昨天';
    const d = parseKey(k); return `${d.getMonth() + 1} 月 ${d.getDate()} 日`;
  };
  const fmtTime = ts => { const d = new Date(ts); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
  const pick = arr => arr[Math.floor(Math.random() * arr.length)];
  const words = t => t.split(/[\s,，、。;；/]+/).map(s => s.trim()).filter(Boolean).slice(0, 3);
  const clip = (t, n = 26) => (t.length > n ? t.slice(0, n) + '…' : t);

  /* ───────── icons ───────── */
  const I = {
    chat: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5.5h14a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5H10l-5 4v-4h0A1.5 1.5 0 0 1 3.5 15V7A1.5 1.5 0 0 1 5 5.5z"/></svg>',
    spark: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5c.6 3.9 2.6 5.9 6.5 6.5-3.9.6-5.9 2.6-6.5 6.5-.6-3.9-2.6-5.9-6.5-6.5 3.9-.6 5.9-2.6 6.5-6.5zM18.5 15.5c.3 1.6 1 2.3 2.5 2.5-1.5.3-2.2 1-2.5 2.5-.3-1.5-1-2.2-2.5-2.5 1.5-.2 2.2-.9 2.5-2.5z"/></svg>',
    sun: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 19h18M6.5 19a5.5 5.5 0 0 1 11 0M12 5.5V8M5.4 9.9l1.7 1.6M18.6 9.9l-1.7 1.6"/></svg>',
    cal: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5.5" width="16" height="14.5" rx="3"/><path d="M4 10h16M9 3.5v4M15 3.5v4"/></svg>',
    me: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="9" r="3.8"/><path d="M4.5 20c1.2-3.6 4-5.4 7.5-5.4s6.3 1.8 7.5 5.4"/></svg>',
    send: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5.5M6.5 11 12 5.5l5.5 5.5"/></svg>',
    plus: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
    close: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>',
    list: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h11M4 12h16M4 17h8"/></svg>',
    back: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M14.5 6 8.5 12l6 6"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  };
  const STAR_COLORS = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)'];
  const star = (i = 0) => `<svg class="star" viewBox="0 0 24 24" aria-hidden="true"><path fill="${STAR_COLORS[Math.abs(i) % 5]}" d="M12 2.6c1 2.4 1.8 4.8 3 6.7 2.4.2 4.6.3 6.6.8-1.7 1.5-3.6 3-5.2 4.6.5 2.3 1.2 4.6 1.4 6.8-2-1.1-4-2.5-5.9-3.3-2.1.9-4 2.4-6.1 3.3.5-2.3 1-4.6 1.6-6.8C5.8 13.2 4 11.6 2.3 10c2-.5 4.3-.4 6.6-.7 1-1.8 2.1-4.3 3.1-6.7z"/></svg>`;
  const moon = '<svg class="moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M19.5 14.6A8 8 0 1 1 9.4 4.5a6.4 6.4 0 0 0 10.1 10.1z"/></svg>';
  const orb = (extra = '') => `<span class="orb ${extra}" aria-hidden="true"></span>`;

  /* ───────── state ───────── */
  function fresh() {
    return {
      v: 1, onboarded: false,
      companion: { name: '小光', hue: 'mist' },
      depth: 'm', view: 'chat', active: 'main',
      threads: { main: { id: 'main', title: '主线', msgs: [] } },
      side: [],
      records: [], wishes: [], memory: [],
      profile: { praise: [], flaws: [], mbti: '', star: '', high: '' },
      ideasHidden: [], proactive: 'normal', tipsHidden: false,
      start: dkey(), ob: null, lastProactive: '', activity: [], genericCount: 0, unread: false,
    };
  }
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)); } catch { return null; } };
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch { /* storage full or blocked */ } };
  let S = load() || fresh();

  // view-only state
  const ui = { composeMode: 'text', recFilter: 'all', quickType: 'good', editingMem: null, editingWish: null, report: null, layer: null, obStep: 0, busy: null, picks: {} };

  const hueColor = () => (HUES.find(h => h.id === S.companion.hue) || HUES[0]).c;
  const T = id => S.threads[id];
  const log = text => { S.activity.push({ t: Date.now(), text }); if (S.activity.length > 60) S.activity.shift(); };
  const push = (tid, m) => { const msg = { id: uid(), t: Date.now(), ...m }; T(tid).msgs.push(msg); save(); return msg; };
  const findMsg = id => { for (const t of Object.values(S.threads)) { const m = t.msgs.find(x => x.id === id); if (m) return m; } return null; };
  const addRecord = (type, text, date = dkey()) => { const r = { id: uid(), type, text, date, t: Date.now() }; S.records.push(r); return r; };
  const count = type => S.records.filter(r => r.type === type).length;
  const dayCount = type => new Set(S.records.filter(r => r.type === type).map(r => r.date)).size;
  const pendingGuesses = () => S.memory.filter(m => m.source === 'guess');
  const discoveryToday = () => DISCOVERY[Math.max(0, daysBetween(S.start, dkey())) % DISCOVERY.length];
  const activeWish = () => S.wishes.find(w => !w.parked);
  const nextStep = w => w && w.steps.find(s => !s.done);

  /* ───────── companion replies ───────── */
  function aiSay(tid, items, delay = 650) {
    ui.busy = tid;
    setThinking(true);
    renderThread();
    let i = 0;
    const next = () => {
      if (i >= items.length) { ui.busy = null; setThinking(false); renderThread(); renderDock(); renderSide(); renderRail(); return; }
      const m = items[i++];
      if (typeof m === 'function') m(); else push(tid, { from: 'ai', ...m });
      renderThread();
      const len = (items[i] && items[i].text || '').length;
      setTimeout(next, i >= items.length ? 0 : 500 + Math.min(1100, len * 22));
    };
    setTimeout(next, delay);
  }

  function userSend(tid, text, opts = {}) {
    text = text.trim();
    if (!text || ui.busy) return;
    const good = ui.composeMode === 'good' && !opts.plain;
    push(tid, { from: 'me', text, good });
    ui.composeMode = 'text';
    renderThread(); renderDock();
    if (good) return goodFlow(tid, text);
    respond(tid, text);
  }

  function lastAi(tid) { const ms = T(tid).msgs; for (let i = ms.length - 2; i >= 0; i--) if (ms[i].from === 'ai') return ms[i]; return null; }

  function respond(tid, text) {
    if (tid === 'main' && S.ob) return obReply(text);
    const th = T(tid);
    if (th.stage) return sideReply(th, text);
    if (/偷懒|休息一天|好累|不想动|摆烂|躺平/.test(text)) return restFlow(tid);
    const prev = lastAi(tid);
    if (prev && prev.discovery) return discoveryFlow(tid, prev.discovery, text);
    if (/一年后|想成为|希望自己|我想要|愿望|想变得/.test(text)) return wishOfferFlow(tid, text);
    if (/做了|完成了|读了|跑了|写了|学了|练了/.test(text)) return stepTextFlow(tid, text);
    if (/开心|好事|高兴|顺利|收到|被夸/.test(text)) return goodFlow(tid, text, true);
    return genericFlow(tid, text);
  }

  function goodFlow(tid, text, inferred = false) {
    if (inferred) {
      return aiSay(tid, [
        { text: '听起来是件好事。要把它存进你的好消息里吗？', card: { type: 'saveGood', text, state: 'pending' } },
      ]);
    }
    addRecord('good', text);
    log(`收下一条好消息：「${clip(text, 16)}」`);
    const n = count('good');
    aiSay(tid, [
      { text: `收好了，这是你的第 ${n} 条好消息。` },
      { text: pick(['这件事里，你最喜欢哪个瞬间？', '是你让它发生的，还是它刚好发生在你身上？两种都很好。', '把它记下来这件事本身，就说明你在留意生活。']) },
    ]);
  }

  function restFlow(tid) {
    if (!S.records.some(r => r.type === 'rest' && r.date === dkey())) addRecord('rest', '今天偷懒');
    log('把今天标成偷懒日');
    aiSay(tid, [
      { text: '好，今天就是偷懒日。' },
      { card: { type: 'rest', goods: count('good'), steps: dayCount('step') } },
      { text: '明天想回来的时候，我们从一件很小的事开始。今天就好好休息。' },
    ]);
  }

  function discoveryFlow(tid, q, text) {
    addRecord('find', `${q.replace(/？.*$/, '？')} ${text}`);
    const mem = { id: uid(), text: guessFromAnswer(text), source: 'guess', t: Date.now() };
    S.memory.push(mem);
    log('把今天的回答放进「新发现」，提出一条猜测等你确认');
    aiSay(tid, [
      { text: '这条我放进「新发现」了。' },
      { text: '我有一个小猜测，不一定对：', card: { type: 'memory', mid: mem.id } },
    ]);
  }

  function guessFromAnswer(text) {
    if (/帮|别人|朋友|讲题|照顾/.test(text)) return '你在帮助别人时，会变得特别投入';
    if (/读|书|写|画|音乐|歌/.test(text)) return `「${clip(text, 12)}」这类事能让你安静地专注很久`;
    if (/跑|运动|走|骑/.test(text)) return '身体动起来的时候，你的心情会变好';
    return `「${clip(text, 14)}」对你来说，比你以为的更重要`;
  }

  function wishOfferFlow(tid, text) {
    aiSay(tid, [
      { text: '听起来这是你很想要的东西。' },
      { text: '要不要把它放进「愿景」，再开一个旁聊，专门慢慢聊它？', card: { type: 'wishOffer', text, state: 'pending' } },
    ]);
  }

  function stepTextFlow(tid, text) {
    addRecord('step', text);
    const w = activeWish();
    if (w) w.tries = (w.tries || 0) + 1;
    log(`记下一次小行动：「${clip(text, 16)}」`);
    aiSay(tid, [
      { text: w ? `这算为「${clip(w.title, 14)}」做的一次小行动，记下了。` : '这算一次小行动，记下了。' },
      { text: '做的时候感觉怎么样？轻松、勉强，还是有点意外地顺利？' },
    ]);
  }

  function genericFlow(tid, text) {
    S.genericCount++;
    const p = S.profile;
    const pool = [
      { text: '嗯，我在听。这件事里，让你最有感觉的是哪一部分？' },
      { text: '如果用一个词形容你现在的心情，会是什么？' },
      { text: '你希望我帮你想想办法，还是只是想说说？', card: { type: 'choices', options: ['帮我想想', '只是想说说'] } },
    ];
    if (p.praise[0]) pool.push({ text: `这让我想起你说自己「${p.praise[0]}」。今天也是这样吗？` });
    const items = [pick(pool)];
    if (S.genericCount % 3 === 0) {
      const mem = { id: uid(), text: `「${clip(text, 16)}」这件事对你挺重要`, source: 'guess', t: Date.now() };
      S.memory.push(mem);
      items.push({ text: '我想记下这一点，可以吗？', card: { type: 'memory', mid: mem.id } });
    }
    aiSay(tid, items);
  }

  function choiceFollow(tid, label) {
    if (label === '只是想说说') return aiSay(tid, [{ text: '好，那我就听着。想说多少都行。' }]);
    if (label === '帮我想想') return aiSay(tid, [{ text: '那我们从最小的地方开始：如果只能改变其中一件事，你会选哪件？' }]);
    respond(tid, label);
  }

  function suggestStep(text, alt = 0) {
    const map = [
      [/钱|收入|赚|副业|财/, ['写下 3 件你做得比别人好一点的事', '查一个你感兴趣的兼职或接单方式', '记一周的花销，只看不改']],
      [/写|作家|文章|博客|投稿/, ['写 100 字，写什么都行', '读 10 页书，划一句喜欢的话', '找一个可以投稿的平台看看']],
      [/读|书|阅读/, ['读 10 页书', '睡前只读 2 页', '把一本想读的书放到枕边']],
      [/自信|表达|社交|说话|勇敢/, ['今天主动和一个人多说一句话', '在课上或会上说一次自己的想法', '写下一件你上周做得不错的事']],
      [/健康|瘦|运动|跑|身体|睡/, ['饭后走 10 分钟', '今晚比平时早 15 分钟放下手机', '喝够 6 杯水']],
      [/学|考|英语|成绩|技能|编程/, ['只学 15 分钟就停下', '背 10 个单词', '把下一步要学的内容写成一行']],
      [/旅行|旅游|出国|远方|看世界/, ['查一个想去的地方，存下三张照片', '算一算一次短途旅行要花多少钱', '这个周末去一个没去过的街区走走']],
    ];
    for (const [re, steps] of map) if (re.test(text)) return steps[alt % steps.length];
    return ['花 5 分钟写下：一年后的某个普通早上，你在做什么', '告诉一个信任的人你想做的这件事', '找一个已经做到的人，看看他们的第一步'][alt % 3];
  }

  /* onboarding conversation (认识自己 → 想象理想自我) */
  function startObChat() {
    S.onboarded = true; S.ob = { step: 'praise' }; S.start = dkey(); S.lastProactive = dkey();
    log('第一次见面');
    save(); render();
    const name = S.companion.name;
    aiSay('main', [
      { text: `你好，我是${name}。接下来的日子，我陪你一点点认识自己。` },
      { text: '先从轻松的开始：用三个词夸夸自己。可以点下面的词，也可以自己写。', card: { type: 'choices', multi: 3, options: ['好奇', '认真', '温柔', '有趣', '靠谱', '能吃苦', '会照顾人', '有想法'] } },
    ], 500);
  }

  function obReply(text) {
    const p = S.profile, step = S.ob.step;
    if (step === 'praise') {
      p.praise = words(text);
      p.praise.forEach(w => S.memory.push({ id: uid(), text: `你夸自己「${w}」`, source: 'self', t: Date.now() }));
      S.ob.step = 'flaws';
      return aiSay('main', [
        { text: `「${p.praise.join('、')}」，记下了。` },
        { text: '再用三个词，说说你不太满意自己的地方。说出来，不代表你就是这样。', card: { type: 'choices', multi: 3, options: ['拖延', '三分钟热度', '容易焦虑', '不够自信', '想太多', '太在意别人看法'] } },
      ]);
    }
    if (step === 'flaws') {
      p.flaws = words(text);
      p.flaws.forEach(w => S.memory.push({ id: uid(), text: `你觉得自己「${w}」`, source: 'self', t: Date.now() }));
      const items = [{ text: '谢谢你愿意说。这些是你现在对自己的看法，以后我们可以一起再看看它们准不准。' }];
      if (S.depth === 's') { S.ob.step = 'future'; return aiSay('main', items.concat(profileItems())); }
      S.ob.step = 'type';
      items.push({ text: '要不要加点趣味信息？比如 MBTI 或星座。只是好玩，我不会拿它来判断你。', card: { type: 'choices', options: ['INFP', 'ENFP', 'INTJ', 'ISFJ', '不知道', '跳过'] } });
      return aiSay('main', items);
    }
    if (step === 'type') {
      const mb = text.match(/[EI][NS][TF][JP]/i);
      const st = text.match(/(白羊|金牛|双子|巨蟹|狮子|处女|天秤|天蝎|射手|摩羯|水瓶|双鱼)/);
      if (mb) p.mbti = mb[0].toUpperCase();
      if (st) p.star = st[1] + '座';
      if (S.depth === 'l') {
        S.ob.step = 'high';
        return aiSay('main', [{ text: mb || st ? '好，当作一点小彩蛋。' : '没关系，不需要标签也能认识你。' }, { text: '再多问一个：最近一次觉得自己挺棒的，是什么时候？' }]);
      }
      S.ob.step = 'future';
      return aiSay('main', [{ text: mb || st ? '好，当作一点小彩蛋。' : '没关系，不需要标签也能认识你。' }].concat(profileItems()));
    }
    if (step === 'high') {
      p.high = text;
      S.memory.push({ id: uid(), text: `你觉得挺棒的时刻：「${clip(text, 20)}」`, source: 'self', t: Date.now() });
      addRecord('good', text);
      S.ob.step = 'future';
      return aiSay('main', [{ text: '这件事我也放进你的好消息里了。' }].concat(profileItems()));
    }
    if (step === 'future') {
      const w = { id: uid(), title: text, why: '', steps: [{ text: suggestStep(text), done: false }], tries: 0, t: Date.now() };
      S.wishes.push(w);
      S.ob = null; S.tipsHidden = false;
      log(`记下第一个愿景：「${clip(text, 16)}」`);
      return aiSay('main', [
        { text: '记下了。这是一个随时可以改的方向，不是承诺。' },
        { text: '为了靠近它，今天可以只做很小的一步：', card: { type: 'step', wid: w.id, text: w.steps[0].text, state: 'pending' } },
        { text: '以后我每天会带来一个关于你的小问题。也可以随时跟我说一件小好事，或者告诉我今天想偷懒。' },
      ]);
    }
  }

  function profileItems() {
    const p = S.profile;
    const guesses = [];
    if (p.flaws.includes('三分钟热度') && p.praise.includes('好奇')) guesses.push('你的「三分钟热度」，也许是好奇心在找方向');
    if (p.praise.some(w => /照顾|温柔|靠谱/.test(w))) guesses.push('有具体的人需要你时，你更容易开始行动');
    if (p.flaws.some(w => /拖延|焦虑|想太多/.test(w))) guesses.push('你拖着不做的事，常常是你特别在意、怕做不好的事');
    if (guesses.length < 2 && p.praise[0] && p.flaws[0]) guesses.push(`你说自己「${p.praise[0]}」又「${p.flaws[0]}」，这两点可能来自同一种认真`);
    if (guesses.length < 2) guesses.push('你对自己的要求，比对别人高一点');
    const mems = guesses.slice(0, 2).map(text => { const m = { id: uid(), text, source: 'guess', t: Date.now() }; S.memory.push(m); return m; });
    log('生成初步画像，提出 2 条猜测等你确认');
    return [
      { text: '根据你刚才说的，我整理了一份初步画像：', card: { type: 'profile' } },
      { text: '下面两条是我猜的，对不对由你决定：', card: { type: 'memory', mid: mems[0].id } },
      { card: { type: 'memory', mid: mems[1].id } },
      { text: '最后一个问题，不用急着回答好：一年后的你，想成为什么样的人？' },
    ];
  }

  /* side chats (旁聊) */
  function openSide(title, wishId) {
    const id = 's' + uid();
    S.threads[id] = { id, title: title || '新旁聊', wishId: wishId || null, msgs: [], stage: wishId ? 'why' : 'topic' };
    S.side.unshift(id);
    S.active = id; S.view = 'chat';
    save(); render();
    const w = S.wishes.find(x => x.id === wishId);
    if (w) aiSay(id, [{ text: `这里专门聊「${clip(w.title, 20)}」。主线里说过的事，我都记得。` }, { text: '先说说：你为什么想要它？' }]);
    else aiSay(id, [{ text: '想单独聊点什么？说一句就好，我用它给这个旁聊起名字。' }]);
    return id;
  }

  function sideReply(th, text) {
    const w = S.wishes.find(x => x.id === th.wishId);
    if (th.stage === 'topic') {
      th.title = clip(text, 14); th.stage = null;
      renderRail();
      return respond(th.id, text);
    }
    if (th.stage === 'why' && w) {
      w.why = text; th.stage = 'have';
      return aiSay(th.id, [{ text: '这个理由很好，我把它写进愿景里了。' }, { text: '那你觉得，自己现在已经有哪些东西能帮上忙？技能、时间、认识的人都算。' }]);
    }
    if (th.stage === 'have' && w) {
      th.stage = null;
      S.memory.push({ id: uid(), text: `为了「${clip(w.title, 10)}」，你已经有：${clip(text, 20)}`, source: 'self', t: Date.now() });
      const s = suggestStep(w.title, w.steps.length);
      w.steps.push({ text: s, done: false });
      return aiSay(th.id, [{ text: '你拥有的比你想的多。' }, { text: '我加了一个小尝试，做不做都由你：', card: { type: 'step', wid: w.id, text: s, state: 'pending' } }]);
    }
    th.stage = null;
    respond(th.id, text);
  }

  /* proactive messages (Muse 的主动消息，频率可控) */
  function maybeProactive() {
    if (!S.onboarded || S.ob || S.proactive === 'off' || S.lastProactive === dkey()) return;
    if (S.proactive === 'less' && S.lastProactive && daysBetween(S.lastProactive, dkey()) < 2) return;
    const h = new Date().getHours();
    S.lastProactive = dkey();
    if (h >= 19) {
      push('main', { from: 'ai', proactive: true, text: '晚上好。今天过得怎么样？有一件小好事也算，什么都没有也没关系。' });
      log('晚间来找你聊聊今天');
    } else {
      push('main', { from: 'ai', proactive: true, text: (h < 11 ? '早上好。' : '') + `今天的问题：${discoveryToday()}`, discovery: discoveryToday() });
      log('带来今天的问题');
    }
    S.unread = true;
    save();
  }

  /* ───────── rendering ───────── */
  function setThinking(on) { document.querySelectorAll('.who .orb').forEach(o => o.classList.toggle('is-thinking', on)); }

  function statusLine() {
    if (ui.busy) return '正在想…';
    if (S.ob) return '正在认识你';
    const g = pendingGuesses().length;
    if (g) return `有 ${g} 条猜测等你确认`;
    const h = new Date().getHours();
    if (S.proactive === 'off') return '安静陪着你，你来找我时都在';
    if (h < 20) return '晚上 8 点来找你聊聊今天';
    return '明早给你带一个新问题';
  }

  const NAV = [
    { id: 'chat', label: '对话', icon: I.chat },
    { id: 'ideas', label: '灵感', icon: I.spark },
    { id: 'goals', label: '愿景', icon: I.sun },
    { id: 'records', label: '记录', icon: I.cal },
    { id: 'me', label: '我', icon: I.me },
  ];

  function render() {
    document.documentElement.style.setProperty('--hue', hueColor());
    renderOnboard();
    if (!S.onboarded) return;
    renderRail(); renderTop(); renderView(); renderSide(); renderTabbar(); renderLayer();
  }

  function renderRail() {
    const side = S.side.map(id => T(id)).filter(Boolean);
    $('#rail').innerHTML = `
      <div class="brand"><i></i>manifest</div>
      ${NAV.map(n => `<button class="nav-btn" data-act="nav" data-v="${n.id}" ${S.view === n.id && (n.id !== 'chat' || S.active === 'main') ? 'aria-current="page"' : ''}>${n.icon}<span>${n.label}</span>${n.id === 'chat' && S.unread ? '<span class="badge" aria-label="有新消息"></span>' : ''}${n.id === 'me' && pendingGuesses().length ? '<span class="badge" aria-label="有待确认"></span>' : ''}</button>`).join('')}
      <div class="rail-sub"><span>旁聊</span><button data-act="new-side" aria-label="新旁聊" title="新旁聊">${I.plus}</button></div>
      ${side.length ? side.map(t => `<button class="thread-btn" data-act="thread" data-id="${t.id}" ${S.view === 'chat' && S.active === t.id ? 'aria-current="true"' : ''}>${esc(t.title)}</button>`).join('') : '<p class="rail-foot" style="margin:0;padding:4px 10px">某件事想单独慢慢聊时，就开一个旁聊。</p>'}
      <p class="rail-foot">原型演示：内容只存在这台设备的浏览器里。</p>`;
  }

  function renderTop() {
    const th = T(S.active);
    const inSide = S.view === 'chat' && S.active !== 'main';
    $('#top').innerHTML = `
      ${inSide ? `<button class="icon-btn" data-act="thread" data-id="main" aria-label="回到主线">${I.back}</button>` : ''}
      <button class="who" data-act="open-activity" aria-label="查看${esc(S.companion.name)}在做什么">
        <span class="orb-ring ${S.unread || pendingGuesses().length ? 'has-news' : ''}">${orb(ui.busy ? 'is-thinking' : '')}</span>
        <span style="min-width:0"><span class="who-name">${esc(S.companion.name)}</span><span class="who-status" style="display:block">${esc(statusLine())}</span></span>
      </button>
      <span class="top-title">${inSide ? `旁聊：${esc(th.title)}` : ''}</span>
      ${S.view === 'chat' ? `<button class="icon-btn only-mobile" data-act="open-threads" aria-label="旁聊列表">${I.list}</button>` : ''}`;
  }

  function renderTabbar() {
    $('#tabbar').innerHTML = NAV.map(n => `<button data-act="nav" data-v="${n.id}" ${S.view === n.id ? 'aria-current="page"' : ''}>${n.icon}<span>${n.label}</span>${n.id === 'chat' && S.unread ? '<span class="badge"></span>' : ''}</button>`).join('');
  }

  function renderView() {
    const v = $('#view');
    if (S.view === 'chat') {
      if (S.active === 'main') S.unread = false;
      v.innerHTML = `<div class="chat"><div class="thread" id="thread" aria-live="polite"><div class="thread-inner" id="threadInner"></div></div><div class="dock"><div class="dock-inner" id="dock"></div></div></div>`;
      renderThread(); renderDock(true);
      save();
      return;
    }
    const pages = { ideas: pageIdeas, goals: pageGoals, records: pageRecords, me: pageMe };
    v.innerHTML = `<div class="scroll"><div class="page">${pages[S.view]()}</div></div>`;
  }

  /* chat thread */
  function renderThread() {
    const box = $('#threadInner');
    if (!box) return;
    const th = T(S.active);
    let html = '', lastDay = '', lastFrom = '';
    th.msgs.forEach((m, i) => {
      const day = dkey(new Date(m.t));
      if (day !== lastDay) { html += `<div class="day-sep">${fmtDay(day)}</div>`; lastDay = day; lastFrom = ''; }
      if (m.proactive) { html += `<div class="proactive-tag">${esc(S.companion.name)} 主动来找你，${fmtTime(m.t)}</div>`; lastFrom = ''; }
      const nextM = th.msgs[i + 1];
      const lastOfGroup = !nextM || nextM.from !== m.from || dkey(new Date(nextM.t)) !== day || nextM.proactive;
      html += msgHtml(m, lastOfGroup);
      lastFrom = m.from;
    });
    if (ui.busy === S.active) html += `<div class="row ai">${orb()}<div class="bubble typing" aria-label="${esc(S.companion.name)}正在输入"><i></i><i></i><i></i></div></div>`;
    if (!th.msgs.length && !ui.busy) html += `<p class="empty" style="text-align:center">这里还没有消息。</p>`;
    box.innerHTML = html;
    const sc = $('#thread');
    requestAnimationFrame(() => { sc.scrollTop = sc.scrollHeight; });
    renderTop();
  }

  function msgHtml(m, lastOfGroup) {
    if (m.from === 'me') {
      return `<div class="row me"><div class="stack"><div class="bubble ${m.good ? 'is-good' : ''}">${m.good ? star(m.t % 5) : ''}${esc(m.text)}</div>${lastOfGroup ? `<span class="meta">${fmtTime(m.t)}</span>` : ''}</div></div>`;
    }
    const parts = [];
    if (m.text) parts.push(`<div class="bubble">${esc(m.text)}</div>`);
    let choices = '';
    if (m.card) {
      if (m.card.type === 'choices') choices = choicesHtml(m);
      else parts.push(cardHtml(m));
    }
    const avatar = lastOfGroup && !choices ? orb() : '<span class="spacer"></span>';
    return `<div class="row ai">${avatar}<div class="stack">${parts.join('')}</div></div>${choices}`;
  }

  function choicesHtml(m) {
    const c = m.card;
    if (c.used) return `<div class="row ai"><span class="spacer"></span><div class="stack"></div></div>`;
    const picked = ui.picks[m.id] || [];
    const chips = c.options.map((o, i) => `<button class="chip" data-act="choice" data-m="${m.id}" data-i="${i}" ${c.multi ? `aria-pressed="${picked.includes(o)}"` : ''}>${esc(o)}</button>`).join('');
    const done = c.multi ? `<button class="btn btn-ink btn-sm" data-act="choice-done" data-m="${m.id}" ${picked.length ? '' : 'disabled style="opacity:.35"'}>就这些${picked.length ? `（${picked.length}）` : ''}</button>` : '';
    return `<div class="choices"><div class="chips">${chips}</div>${done}</div>`;
  }

  function cardHtml(m) {
    const c = m.card;
    if (c.type === 'memory') {
      const mem = S.memory.find(x => x.id === c.mid);
      if (!mem) return `<div class="card is-settled"><div class="card-body">${esc(c.lastText || '这条已经忘掉了')}</div><p class="settled-note">不记了</p></div>`;
      c.lastText = mem.text;
      if (mem.source !== 'guess') return `<div class="card is-settled"><div class="card-title">记忆</div><div class="card-body">${esc(mem.text)}</div><p class="settled-note">已记下，可以在「我」里修改</p></div>`;
      return `<div class="card"><div class="card-title">想记住这条</div><div class="card-body">${esc(mem.text)}</div>
        <div class="card-actions"><button class="btn btn-ink btn-sm" data-act="mem-yes" data-id="${mem.id}">对，记下</button><button class="btn btn-line btn-sm" data-act="mem-no" data-id="${mem.id}">不太对</button></div></div>`;
    }
    if (c.type === 'step') {
      const settled = { done: '做到了，这一步算数', skip: '今天先不做，它会在愿景里等你' }[c.state];
      return `<div class="card ${settled ? 'is-settled' : ''}"><div class="card-title">今天的一小步</div><div class="card-body">${esc(c.text)}</div>
        ${settled ? `<p class="settled-note">${settled}</p>` : `<div class="card-actions"><button class="btn btn-ink btn-sm" data-act="step-done" data-m="${m.id}">做到了</button><button class="btn btn-line btn-sm" data-act="step-swap" data-m="${m.id}">换一个</button><button class="btn btn-ghost btn-sm" data-act="step-skip" data-m="${m.id}">今天不做</button></div>`}</div>`;
    }
    if (c.type === 'rest') {
      return `<div class="card"><div class="card-title">${moon} 偷懒日</div><div class="card-body">之前的 ${c.goods} 条好消息、${c.steps} 天小行动都还在，不会因为今天休息而清零。</div></div>`;
    }
    if (c.type === 'saveGood') {
      if (c.state === 'saved') return `<div class="card is-settled"><div class="card-body">${star(2)} ${esc(c.text)}</div><p class="settled-note">已存进好消息</p></div>`;
      if (c.state === 'no') return '';
      return `<div class="card"><div class="card-body">${star(2)} ${esc(c.text)}</div><div class="card-actions"><button class="btn btn-ink btn-sm" data-act="good-yes" data-m="${m.id}">存下</button><button class="btn btn-ghost btn-sm" data-act="good-no" data-m="${m.id}">不用</button></div></div>`;
    }
    if (c.type === 'wishOffer') {
      if (c.state === 'yes') return `<div class="card is-settled"><div class="card-body">${esc(c.text)}</div><p class="settled-note">已放进愿景，并开了旁聊</p></div>`;
      if (c.state === 'no') return '';
      return `<div class="card"><div class="card-title">新的愿景</div><div class="card-body">${esc(c.text)}</div><div class="card-actions"><button class="btn btn-ink btn-sm" data-act="wish-yes" data-m="${m.id}">放进愿景并开旁聊</button><button class="btn btn-ghost btn-sm" data-act="wish-no" data-m="${m.id}">先不用</button></div></div>`;
    }
    if (c.type === 'profile') {
      const p = S.profile;
      const fun = [p.mbti, p.star].filter(Boolean);
      return `<div class="card profile-card"><div class="card-title">初步画像</div><dl>
        <dt>你夸自己</dt><dd class="tagline">${p.praise.map(w => `<span class="tag is-hue">${esc(w)}</span>`).join('') || '—'}</dd>
        <dt>想改变的</dt><dd class="tagline">${p.flaws.map(w => `<span class="tag">${esc(w)}</span>`).join('') || '—'}</dd>
        ${fun.length ? `<dt>趣味信息</dt><dd>${esc(fun.join('，'))}<span style="color:var(--ink-3)">（只是好玩）</span></dd>` : ''}
        </dl><p class="fine">画像会随着我们聊天慢慢变。哪里不对，都可以在「我」里改。</p></div>`;
    }
    if (c.type === 'report') {
      const st = reportStats(c.days);
      return `<div class="card"><div class="card-title">${c.days} 天蜕变报告</div><div class="report-teaser"><span class="big">${st.good}</span><span>条好消息，<br>${st.stepDays} 天小行动，${st.rest} 天偷懒</span></div>
        <div class="card-actions"><button class="btn btn-ink btn-sm" data-act="open-report" data-days="${c.days}">打开报告</button></div></div>`;
    }
    return '';
  }

  function renderDock(focus) {
    const d = $('#dock');
    if (!d) return;
    const prev = $('#input');
    const val = prev ? prev.value : '';
    const good = ui.composeMode === 'good';
    const showTips = !S.tipsHidden && !S.ob && S.active === 'main';
    const tips = ['今天有件小好事', '我想聊聊一年后的我', '今天读了 10 页书', '今天想偷懒'];
    d.innerHTML = `
      ${showTips ? `<div class="tips"><span class="tips-label">可以试试</span>${tips.map(t => `<button class="tip" data-act="tip" data-t="${esc(t)}">${esc(t)}</button>`).join('')}<button class="icon-btn" data-act="tips-hide" aria-label="收起提示">${I.close}</button></div>` : ''}
      ${good ? `<div class="mode-bar">${star(1)} 记一条好消息，再小的事也算<button data-act="mode-text">取消</button></div>` : ''}
      <form class="composer ${good ? 'is-good' : ''}" id="composer">
        <button type="button" class="cbtn" data-act="mode-good" aria-pressed="${good}" aria-label="记一条好消息" title="记一条好消息">${star(good ? 1 : 3)}</button>
        <textarea id="input" rows="1" placeholder="${good ? '今天有什么小好事？' : `给${esc(S.companion.name)}发消息`}" aria-label="消息"></textarea>
        <button type="button" class="cbtn" data-act="rest" aria-label="今天想偷懒" title="今天想偷懒">${moon}</button>
        <button type="submit" class="send" aria-label="发送">${I.send}</button>
      </form>`;
    const ta = $('#input');
    ta.value = val;
    autosize(ta);
    if (focus && window.matchMedia('(min-width: 761px)').matches) ta.focus();
  }

  function autosize(ta) { ta.style.height = 'auto'; ta.style.height = Math.min(160, ta.scrollHeight) + 'px'; }

  /* ideas page (Muse 的 Ideas：基于目标与习惯的建议) */
  function ideaList() {
    const out = [];
    const p = S.profile;
    S.wishes.filter(w => !w.parked).forEach(w => {
      const s = suggestStep(w.title, w.steps.length + 1);
      if (!w.steps.some(x => x.text === s)) out.push({ id: 'w' + w.id + s, from: `来自愿景「${clip(w.title, 14)}」`, text: `再加一小步：${s}`, kind: 'try', wid: w.id, step: s });
    });
    if (p.flaws.includes('拖延')) out.push({ id: 'f-tuo', from: '因为你说自己拖延', text: '试试「两分钟开始」：只做两分钟，做完就可以停。', kind: 'try', step: '只做两分钟，做完就可以停' });
    if (p.flaws.includes('三分钟热度')) out.push({ id: 'f-san', from: '因为你说自己三分钟热度', text: '把一件喜欢的事拆成 3 天的小实验，看看哪天最投入。', kind: 'chat' });
    if (p.flaws.some(f => /焦虑|想太多/.test(f))) out.push({ id: 'f-jiao', from: '因为你说自己容易焦虑', text: '睡前写下一件今天没出错的事。', kind: 'try', step: '睡前写下一件今天没出错的事' });
    if (count('good') >= 5) out.push({ id: 'r-sort', from: `你已经有 ${count('good')} 条好消息`, text: '把它们排个序，看看哪一种最常出现。', kind: 'chat' });
    const conf = S.memory.find(m => m.source === 'confirmed');
    if (conf) out.push({ id: 'm-' + conf.id, from: '来自你确认过的记忆', text: `「${clip(conf.text, 22)}」：要不要想想这一点还能用在哪里？`, kind: 'chat' });
    out.push({ id: 'g-future', from: '想象理想自我', text: '写下一年后某个普通周二的样子：几点起床，在做什么，和谁在一起。', kind: 'chat' });
    return out.filter(x => !S.ideasHidden.includes(x.id));
  }

  function pageIdeas() {
    const q = discoveryToday();
    const ideas = ideaList();
    const f = FREQ.find(x => x.id === S.proactive);
    return `
      <div class="page-head"><h1>灵感</h1><p>${esc(S.companion.name)}根据你的愿景、记录和聊天想到的事。挑感兴趣的试，不感兴趣就划掉。</p></div>
      <div class="discovery">
        <div class="when">${orb()}<span>今日发现</span></div>
        <p class="q">${esc(q)}</p>
        <button class="btn btn-ink" data-act="answer-discovery">在对话里回答</button>
      </div>
      <div class="section"><h2>可以试试</h2><p class="sub">每条都写了它从哪里来。</p>
        <div class="idea-list">${ideas.length ? ideas.map(x => `
          <div class="idea"><span class="idea-from">${esc(x.from)}</span><span class="idea-text">${esc(x.text)}</span>
            <span class="idea-acts">${x.kind === 'try' ? `<button class="btn btn-line btn-sm" data-act="idea-try" data-id="${esc(x.id)}">试试看</button>` : `<button class="btn btn-line btn-sm" data-act="idea-chat" data-id="${esc(x.id)}">聊聊这个</button>`}
            <button class="icon-btn" data-act="idea-hide" data-id="${esc(x.id)}" aria-label="不感兴趣" title="不感兴趣">${I.close}</button></span></div>`).join('') : '<p class="empty">暂时没有新想法了。多聊几次，我会想到更多。</p>'}</div>
      </div>
      <div class="section"><h2>${esc(S.companion.name)}多久来找你一次</h2><p class="sub">只在值得打扰的时候来。</p>
        <div class="seg" role="group" aria-label="主动消息频率">${FREQ.map(x => `<button data-act="freq" data-v="${x.id}" aria-pressed="${S.proactive === x.id}">${x.label}</button>`).join('')}</div>
        <p class="freq-note">${esc(f.note)}</p>
      </div>`;
  }

  /* goals page (Muse 的 Goals：伙伴在追踪的事和计划) */
  function pageGoals() {
    const list = S.wishes.filter(w => !w.parked);
    const parked = S.wishes.filter(w => w.parked);
    return `
      <div class="page-head"><h1>愿景</h1><p>你想靠近的样子。方向可以随时改，步子可以很小。</p></div>
      ${list.length ? list.map(wishHtml).join('') : '<p class="empty">还没有愿景。写下一个模糊的也可以，我们一起把它聊清楚。</p>'}
      <form class="add-wish" data-form="add-wish"><label for="wishInput">一年后的你，还想成为什么样？</label>
        <div class="inline-field"><input id="wishInput" placeholder="比如：更自在地表达自己" autocomplete="off"><button class="btn btn-ink" type="submit">添加</button></div></form>
      ${parked.length ? `<div class="section"><h2>先放一放的</h2><p class="sub">放下不代表放弃，想回来就点回来。</p>${parked.map(w => `<div class="tl-item"><span class="tl-text" style="color:var(--ink-2)">${esc(w.title)}</span><button class="btn btn-ghost btn-sm" data-act="wish-unpark" data-id="${w.id}">回来</button></div>`).join('')}</div>` : ''}`;
  }

  function wishHtml(w) {
    const editing = ui.editingWish === w.id;
    const done = w.steps.filter(s => s.done).length;
    return `<article class="wish">
      ${editing ? `<form class="inline-field" data-form="edit-wish" data-id="${w.id}"><input value="${esc(w.title)}" aria-label="愿景"><button class="btn btn-ink" type="submit">保存</button></form>` : `<h2 class="wish-title">${esc(w.title)}</h2>`}
      <p class="wish-why">${w.why ? `<span>因为</span> ${esc(w.why)}` : '<span>还没聊过为什么想要它</span>'}</p>
      <p class="wish-meta">试过 ${w.tries || 0} 次，完成 ${done} 个小步骤。不算进度，只是记录你走过的路。</p>
      <ul class="steps">${w.steps.map((s, i) => `<li class="${s.done ? 'done' : ''}"><button data-act="wish-step" data-id="${w.id}" data-i="${i}" aria-pressed="${s.done}"><span class="check">${I.check}</span><span class="step-text">${esc(s.text)}</span></button></li>`).join('')}</ul>
      <div class="wish-acts">
        <button class="btn btn-line btn-sm" data-act="wish-chat" data-id="${w.id}">在旁聊里细聊</button>
        <button class="btn btn-ghost btn-sm" data-act="wish-edit" data-id="${w.id}">改一改</button>
        <button class="btn btn-ghost btn-sm" data-act="wish-park" data-id="${w.id}">先放一放</button>
      </div></article>`;
  }

  /* records page (好消息 + 小行动 + 偷懒日 + 新发现) */
  function pageRecords() {
    const today = dkey();
    const days = [...Array(30)].map((_, i) => dkey(addDays(new Date(), i - 29)));
    const by = {};
    S.records.forEach(r => { (by[r.date] = by[r.date] || []).push(r); });
    const strip = days.map(k => {
      const rs = by[k] || [];
      const g = rs.some(r => r.type === 'good'), s = rs.some(r => r.type === 'step'), rest = rs.some(r => r.type === 'rest');
      const before = k < S.start;
      const label = `${fmtDay(k)}：${rs.length ? rs.map(r => TYPE_LABEL[r.type]).join('，') : '没有记录'}`;
      return `<div class="cell ${before ? 'is-before' : ''} ${k === today ? 'is-today' : ''}" title="${esc(label)}" aria-label="${esc(label)}">${g ? `<span class="mk-good">${star(parseKey(k).getDate())}</span>` : ''}${s ? '<span class="mk-step"></span>' : ''}${rest ? `<span class="mk-rest">${moon}</span>` : ''}</div>`;
    }).join('');
    const f = ui.recFilter;
    const list = S.records.filter(r => f === 'all' || r.type === f).slice().sort((a, b) => (a.date === b.date ? b.t - a.t : a.date < b.date ? 1 : -1));
    const groups = [];
    list.forEach(r => { const g = groups[groups.length - 1]; if (g && g.date === r.date) g.items.push(r); else groups.push({ date: r.date, items: [r] }); });
    const since = daysBetween(S.start, today) + 1;
    const qt = ui.quickType;
    const ph = { good: '今天有什么小好事？', step: '今天为愿景做了什么小事？', find: '今天发现了自己的什么？' }[qt];
    return `
      <div class="page-head"><h1>记录</h1><p>不比连续天数，也不会清零。空着的日子，也是你生活的一部分。</p></div>
      <div class="strip" aria-label="最近 30 天">${strip}</div>
      <div class="strip-legend"><span>${star(0)} 好消息</span><span><i class="mk-step"></i> 小行动</span><span>${moon} 偷懒日</span><span style="margin-left:auto">最近 30 天</span></div>
      <p class="tally">这 ${since} 天里，你收集了 <b>${count('good')}</b> 条好消息，有 <b>${dayCount('step')}</b> 天为愿景做了点事，也给自己放了 <b>${dayCount('rest')}</b> 天假。</p>
      <div class="card-actions" style="margin-top:14px">
        <button class="btn btn-ink btn-sm" data-act="open-report" data-days="10">看 10 天蜕变报告</button>
        <button class="btn btn-line btn-sm" data-act="open-report" data-days="30">看 30 天蜕变报告</button>
      </div>
      <div class="section">
        <form class="quick" data-form="quick">
          <div class="quick-top"><div class="seg" role="group" aria-label="记录类型">${['good', 'step', 'find'].map(t => `<button type="button" data-act="quick-type" data-v="${t}" aria-pressed="${qt === t}">${TYPE_LABEL[t]}</button>`).join('')}</div>
          <button type="button" class="btn btn-ghost btn-sm" data-act="rest-here">${moon} 今天偷懒</button></div>
          <div class="inline-field"><input id="quickInput" placeholder="${ph}" autocomplete="off" aria-label="${ph}"><button class="btn btn-ink" type="submit">存下</button></div>
        </form>
      </div>
      <div class="section">
        <div class="seg" role="group" aria-label="筛选">${[['all', '全部'], ['good', '好消息'], ['step', '小行动'], ['find', '新发现'], ['rest', '偷懒日']].map(([v, l]) => `<button data-act="rec-filter" data-v="${v}" aria-pressed="${f === v}">${l}</button>`).join('')}</div>
        <div class="timeline">${groups.length ? groups.map(g => `<div class="tl-day"><h3>${fmtDay(g.date)}</h3>${g.items.map(r => `<div class="tl-item"><span class="tl-mark">${markHtml(r)}</span><span class="tl-text">${esc(r.text)}</span><span class="tl-type">${TYPE_LABEL[r.type]}</span></div>`).join('')}</div>`).join('') : '<p class="empty">这里还空着。今天有什么小事，都可以从上面记下。</p>'}</div>
      </div>`;
  }
  const markHtml = r => r.type === 'good' ? star(r.t % 5) : r.type === 'rest' ? moon : r.type === 'find' ? '<span class="mk-find"></span>' : '<span class="mk-step"></span>';

  /* me page (画像 + 可编辑记忆 + 伙伴设置) */
  function pageMe() {
    const p = S.profile;
    const order = { guess: 0, confirmed: 1, self: 2 };
    const mems = S.memory.slice().sort((a, b) => order[a.source] - order[b.source] || b.t - a.t);
    return `
      <div class="page-head"><h1>关于你</h1><p>${esc(S.companion.name)}记得的一切都在这里。你可以确认、修改，或者让它忘掉。</p></div>
      <div class="profile-card card" style="max-width:none"><div class="card-title">画像</div><dl>
        <dt>你夸自己</dt><dd class="tagline">${p.praise.map(w => `<span class="tag is-hue">${esc(w)}</span>`).join('') || '—'}</dd>
        <dt>想改变的</dt><dd class="tagline">${p.flaws.map(w => `<span class="tag">${esc(w)}</span>`).join('') || '—'}</dd>
        <dt>趣味信息</dt><dd>${esc([p.mbti, p.star].filter(Boolean).join('，') || '没有填')}<span style="color:var(--ink-3)">（只是好玩，不作判断）</span></dd>
      </dl></div>
      <div class="section"><h2>${esc(S.companion.name)}记得的事</h2><p class="sub">「伙伴猜的」在你确认之前，不会被当成事实。</p>
        <div>${mems.length ? mems.map(memHtml).join('') : '<p class="empty">还没有记忆。</p>'}</div></div>
      <div class="section"><h2>伙伴</h2><p class="sub">名字和颜色，随时可以换。</p>
        <form class="inline-field" data-form="rename" style="max-width:360px"><input id="renameInput" value="${esc(S.companion.name)}" maxlength="8" aria-label="伙伴名字"><button class="btn btn-line" type="submit">改名</button></form>
        <div class="swatches" style="margin-top:14px">${HUES.map(h => `<button class="swatch" data-act="hue" data-v="${h.id}" aria-pressed="${S.companion.hue === h.id}" style="--hue:${h.c}">${orb()}<span>${h.name}</span></button>`).join('')}</div></div>
      <div class="section"><h2>探索深度</h2><p class="sub">每天的问题会按这个长度准备。想多聊时，可以随时补几道题。</p>
        <div class="seg" role="group" aria-label="探索深度">${DEPTHS.map(d => `<button data-act="depth" data-v="${d.id}" aria-pressed="${S.depth === d.id}">${d.label}</button>`).join('')}</div>
        <div style="margin-top:12px"><button class="btn btn-line btn-sm" data-act="more-q">现在补几道题</button></div></div>
      <div class="section"><h2>原型数据</h2><p class="sub">只保存在这台设备的浏览器里。</p>
        <div class="card-actions"><button class="btn btn-line btn-sm" data-act="demo">载入 12 天示例</button><button class="btn btn-ghost btn-sm danger" data-act="reset">清空，重新开始</button></div></div>`;
  }

  function memHtml(m) {
    if (ui.editingMem === m.id) return `<div class="mem"><form class="inline-field" data-form="edit-mem" data-id="${m.id}" style="grid-column:1/-1"><input value="${esc(m.text)}" aria-label="修改记忆"><button class="btn btn-ink btn-sm" type="submit">保存</button></form></div>`;
    return `<div class="mem"><span class="mem-src ${m.source === 'guess' ? 'is-guess' : ''}">${SOURCE_LABEL[m.source]}</span>
      <span class="mem-acts">${m.source === 'guess' ? `<button class="btn btn-ink btn-sm" data-act="mem-yes" data-id="${m.id}">对</button>` : ''}<button class="btn btn-ghost btn-sm" data-act="mem-edit" data-id="${m.id}">改</button><button class="btn btn-ghost btn-sm" data-act="mem-forget" data-id="${m.id}">忘掉</button></span>
      <span>${esc(m.text)}</span></div>`;
  }

  /* context column (desktop) */
  function renderSide() {
    if (!S.onboarded) return;
    const w = activeWish(), s = nextStep(w);
    const now = new Date();
    const wk = '日一二三四五六'[now.getDay()];
    $('#context').innerHTML = `
      <div class="ctx-date">星期${wk}<b>${now.getMonth() + 1} 月 ${now.getDate()} 日</b></div>
      <div class="ctx-block"><h3>今日发现</h3><p class="ctx-q">${esc(discoveryToday())}</p><button class="btn btn-line btn-sm" data-act="answer-discovery">回答它</button></div>
      ${s ? `<div class="ctx-block"><h3>为「${esc(clip(w.title, 12))}」</h3><div class="ctx-step"><span>${esc(s.text)}</span></div><button class="btn btn-line btn-sm" data-act="wish-step-next" data-id="${w.id}">做到了</button></div>` : ''}
      <div class="ctx-block"><h3>到现在为止</h3><div class="ctx-counts"><div><b>${count('good')}</b><span>好消息</span></div><div><b>${dayCount('step')}</b><span>行动天</span></div><div><b>${dayCount('rest')}</b><span>偷懒天</span></div></div></div>
      <p class="ctx-note">偷懒也算数。休息过的日子，不会让之前的努力清零。</p>`;
  }

  /* layers: activity drawer, thread list, report */
  function renderLayer() {
    const scrim = $('#scrim'), drawer = $('#drawer'), modal = $('#modal');
    scrim.hidden = !ui.layer; drawer.hidden = !(ui.layer === 'activity' || ui.layer === 'threads'); modal.hidden = ui.layer !== 'report';
    if (ui.layer === 'activity') drawer.innerHTML = activityHtml();
    if (ui.layer === 'threads') drawer.innerHTML = threadsHtml();
    if (ui.layer === 'report') modal.innerHTML = reportHtml();
  }

  function activityHtml() {
    const h = new Date().getHours();
    const planned = [];
    if (S.proactive !== 'off' && h < 20) planned.push(['20:00', '来找你聊聊今天的收获']);
    planned.push(['23:00', '整理今天的对话；新的猜测会先交给你确认']);
    if (S.proactive !== 'off') planned.push(['明早', '带来一个新的「今日发现」问题']);
    const done = S.activity.slice(-12).reverse();
    return `<div class="drawer-head"><button class="icon-btn" data-act="layer-close" aria-label="关闭">${I.close}</button></div>
      <div class="drawer-hero">${orb()}<h2>${esc(S.companion.name)}</h2><p>${esc(statusLine())}</p></div>
      <div class="section"><h2>接下来打算做的</h2><ul class="log">${planned.map(([t, x]) => `<li><time>${t}</time><span class="is-planned">${esc(x)}</span></li>`).join('')}</ul></div>
      <div class="section"><h2>做过的事</h2><ul class="log">${done.length ? done.map(a => `<li><time>${fmtDay(dkey(new Date(a.t))) === '今天' ? fmtTime(a.t) : fmtDay(dkey(new Date(a.t))).replace(' 月 ', '/').replace(' 日', '')}</time><span>${esc(a.text)}</span></li>`).join('') : '<li><time></time><span>还没有。</span></li>'}</ul></div>
      <div class="section"><h2>${esc(S.companion.name)}的约定</h2><ul class="log">
        <li><time>记忆</time><span>猜测只有你确认后才记下，随时能改、能删</span></li>
        <li><time>主动</time><span>${esc(FREQ.find(f => f.id === S.proactive).note)}</span></li>
        <li><time>分享</time><span>报告只在你选择后才会分享，内容由你挑</span></li></ul>
        <div class="card-actions"><button class="btn btn-line btn-sm" data-act="goto" data-v="ideas">调整主动频率</button><button class="btn btn-line btn-sm" data-act="goto" data-v="me">查看记忆</button></div></div>`;
  }

  function threadsHtml() {
    const ids = ['main', ...S.side];
    return `<div class="drawer-head"><button class="icon-btn" data-act="layer-close" aria-label="关闭">${I.close}</button></div>
      <div class="section" style="margin-top:0"><h2>对话</h2><p class="sub">主线一直都在。某件事想单独慢慢聊，就开一个旁聊。</p>
      ${ids.map(id => `<button class="thread-btn" data-act="thread" data-id="${id}" ${S.active === id ? 'aria-current="true"' : ''}>${esc(id === 'main' ? '主线' : T(id).title)}</button>`).join('')}
      <div class="card-actions"><button class="btn btn-ink btn-sm" data-act="new-side">新旁聊</button></div></div>`;
  }

  function reportStats(days) {
    const from = dkey(addDays(new Date(), -(days - 1)));
    const rs = S.records.filter(r => r.date >= from);
    const span = Math.min(days, daysBetween(S.start, dkey()) + 1);
    return {
      from, span,
      good: rs.filter(r => r.type === 'good').length,
      stepDays: new Set(rs.filter(r => r.type === 'step').map(r => r.date)).size,
      rest: new Set(rs.filter(r => r.type === 'rest').map(r => r.date)).size,
      finds: rs.filter(r => r.type === 'find'),
      goods: rs.filter(r => r.type === 'good').slice(-3).reverse(),
    };
  }

  function reportHtml() {
    const R = ui.report;
    const st = reportStats(R.days);
    const p = S.profile;
    const confirmed = S.memory.filter(m => m.source === 'confirmed').slice(-3);
    const w = activeWish(), s = nextStep(w);
    const on = k => !R.hide.includes(k);
    const start = parseKey(st.from < S.start ? S.start : st.from);
    const title = confirmed.length ? `你比自己以为的，更能坚持喜欢的事。` : `你在一点点认识自己。`;
    const story = `${st.span} 天前，你说自己${p.flaws.length ? `「${p.flaws.join('、')}」` : '还说不清自己是什么样'}。这 ${st.span} 天里，你记下了 ${st.good} 条好消息，有 ${st.stepDays} 天为愿景做了一点事，也给自己放了 ${st.rest} 天假。休息的日子也在这个故事里。`;
    const blocks = [
      ['story', '开头的话', true],
      ['nums', '数字', true],
      ['shift', '对自己的新认识', confirmed.length > 0],
      ['goods', '值得庆祝的小事', st.goods.length > 0],
      ['next', '下一段想探索', !!w],
    ].filter(b => b[2]);
    R.text = [title, on('story') ? story : '', on('nums') ? `好消息 ${st.good} 条，行动 ${st.stepDays} 天，偷懒 ${st.rest} 天` : '',
      on('shift') && confirmed.length ? '新认识：' + confirmed.map(m => m.text).join('；') : '',
      on('goods') && st.goods.length ? '值得庆祝：' + st.goods.map(r => r.text).join('；') : '',
      on('next') && w ? `下一段：${w.title}${s ? `，先从「${s.text}」开始` : ''}` : '', '—— 来自 manifest'].filter(Boolean).join('\n');
    return `<div class="sheet">
      <div class="report" id="reportCard">
        ${orb()}
        <p class="report-range">${start.getMonth() + 1} 月 ${start.getDate()} 日起的 ${R.days} 天</p>
        <h2>${esc(title)}</h2>
        ${on('story') ? `<p class="report-story">${esc(story)}</p>` : ''}
        ${on('nums') ? `<div class="report-nums"><div><b>${st.good}</b><span>条好消息</span></div><div><b>${st.stepDays}</b><span>天小行动</span></div><div><b>${st.rest}</b><span>天偷懒，也算数</span></div></div>` : ''}
        ${on('shift') && confirmed.length ? `<div class="report-block"><h3>对自己的新认识</h3>${p.flaws.length ? `<p class="then">开始时，你说自己「${esc(p.flaws.join('、'))}」。现在你发现：</p>` : ''}<ul>${confirmed.map(m => `<li>${esc(m.text)}</li>`).join('')}</ul></div>` : ''}
        ${on('goods') && st.goods.length ? `<div class="report-block"><h3>值得庆祝的小事</h3><ul>${st.goods.map((r, i) => `<li>${star(i)}<span>${esc(r.text)}</span></li>`).join('')}</ul></div>` : ''}
        ${on('next') && w ? `<div class="report-block"><h3>下一段想探索</h3><p>${esc(w.title)}${s ? `<br><span style="color:var(--ink-2)">先从「${esc(s.text)}」开始</span>` : ''}</p></div>` : ''}
        <div class="report-foot"><span>manifest</span><span>和${esc(S.companion.name)}一起整理</span></div>
      </div>
      <div class="sheet-side">
        <div class="drawer-head"><button class="icon-btn" data-act="layer-close" aria-label="关闭">${I.close}</button></div>
        <div class="seg" role="group" aria-label="报告范围" style="margin-bottom:18px">${[10, 30].map(d => `<button data-act="report-days" data-v="${d}" aria-pressed="${R.days === d}">${d} 天</button>`).join('')}</div>
        <h3>分享时显示哪些</h3><p class="sub">报告默认只有你自己能看到。</p>
        ${blocks.map(([k, l]) => `<label class="toggle">${l}<input type="checkbox" data-act="report-toggle" data-v="${k}" ${on(k) ? 'checked' : ''}></label>`).join('')}
        <button class="btn btn-ink" data-act="report-copy">复制文字版</button>
        <button class="btn btn-ghost" data-act="layer-close">关闭</button>
      </div></div>`;
  }

  /* onboarding (创建伙伴 → 选择深度 → 在对话里认识你) */
  function renderOnboard() {
    const el = $('#onboard');
    if (S.onboarded) { el.hidden = true; el.innerHTML = ''; return; }
    el.hidden = false;
    const st = ui.obStep;
    const dots = `<div class="ob-dots" aria-label="第 ${st + 1} 步，共 2 步"><i class="${st >= 0 ? 'on' : ''}"></i><i class="${st >= 1 ? 'on' : ''}"></i></div>`;
    const body = st === 0 ? `
      <div class="ob-orb">${orb()}</div>
      <h1>每一天，多认识自己一点</h1>
      <p class="lead">先给陪你的伙伴起个名字，再挑一个颜色。之后都能改。</p>
      <div class="ob-field">
        <input id="obName" value="${esc(S.companion.name)}" maxlength="8" aria-label="伙伴名字" autocomplete="off">
        <div class="swatches" role="group" aria-label="颜色">${HUES.map(h => `<button class="swatch" data-act="hue" data-v="${h.id}" aria-pressed="${S.companion.hue === h.id}" style="--hue:${h.c}">${orb()}<span>${h.name}</span></button>`).join('')}</div>
      </div>` : `
      <div class="ob-orb" style="margin-bottom:22px">${orb()}</div>
      <h1>第一次，想聊多久？</h1>
      <p class="lead">${esc(S.companion.name)}会按你的时间准备问题。没聊完的，以后随时可以补。</p>
      <div class="depths" role="group" aria-label="探索深度">${DEPTHS.map(d => `<button class="depth" data-act="depth" data-v="${d.id}" aria-pressed="${S.depth === d.id}"><b>${d.label}</b><span class="radio"></span><span>${d.desc}</span></button>`).join('')}</div>`;
    el.innerHTML = `<div class="ob-wrap">
      <div class="ob-top"><div class="brand"><i></i>manifest</div>${dots}</div>
      <div class="ob-main">${body}</div>
      <div class="ob-foot">
        ${st === 0 ? `<button class="btn btn-ink" data-act="ob-next">下一步</button><button class="btn btn-ghost" data-act="demo">先看一份 12 天的示例</button>`
        : `<button class="btn btn-ink" data-act="ob-start">开始和${esc(S.companion.name)}聊天</button><button class="btn btn-ghost" data-act="ob-back">上一步</button>`}
      </div></div>`;
  }

  /* ───────── interactions ───────── */
  function go(view) { S.view = view; if (view === 'chat' && !S.threads[S.active]) S.active = 'main'; ui.layer = null; save(); render(); $('#view .scroll')?.scrollTo(0, 0); }

  let toastTimer;
  function toast(text) { const t = $('#toast'); t.textContent = text; t.classList.add('is-on'); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('is-on'), 2200); }

  function sendToMain(text) {
    S.active = 'main'; S.view = 'chat'; ui.layer = null; save(); render();
    if (text) setTimeout(() => userSend('main', text, { plain: true }), 150);
  }

  function askInMain(q, discovery) {
    S.active = 'main'; S.view = 'chat'; ui.layer = null;
    save(); render();
    aiSay('main', [{ text: q, discovery: discovery ? q : undefined }], 250);
  }

  const handlers = {
    nav: d => { if (d.v === 'chat') S.active = 'main'; go(d.v); },
    goto: d => go(d.v),
    thread: d => { S.active = d.id; go('chat'); },
    'new-side': () => { ui.layer = null; openSide(); },
    'open-threads': () => { ui.layer = 'threads'; renderLayer(); },
    'open-activity': () => { ui.layer = 'activity'; S.unread = false; save(); renderLayer(); renderTop(); renderRail(); renderTabbar(); },
    'layer-close': () => { ui.layer = null; renderLayer(); },

    choice: d => {
      const m = findMsg(d.m); if (!m || ui.busy) return;
      const opt = m.card.options[+d.i];
      if (m.card.multi) {
        const p = ui.picks[m.id] = ui.picks[m.id] || [];
        const at = p.indexOf(opt);
        if (at >= 0) p.splice(at, 1); else if (p.length < m.card.multi) p.push(opt);
        return renderThread();
      }
      m.card.used = true; save();
      push(S.active, { from: 'me', text: opt }); renderThread();
      if (S.ob) return obReply(opt);
      choiceFollow(S.active, opt);
    },
    'choice-done': d => {
      const m = findMsg(d.m); const p = ui.picks[d.m] || [];
      if (!m || !p.length || ui.busy) return;
      const typed = $('#input')?.value.trim();
      const all = typed ? p.concat(words(typed)).slice(0, 3) : p;
      if ($('#input')) $('#input').value = '';
      m.card.used = true; save();
      userSend(S.active, all.join('、'), { plain: true });
    },
    'mem-yes': d => { const m = S.memory.find(x => x.id === d.id); if (!m) return; m.source = 'confirmed'; log(`你确认了：「${clip(m.text, 16)}」`); save(); toast('记下了'); refresh(); },
    'mem-no': d => {
      S.memory = S.memory.filter(x => x.id !== d.id); save(); refresh();
      aiSay(S.active, [{ text: '好，我不这么记。哪里不对？说一句就行，我会重新想。' }]);
    },
    'mem-edit': d => { ui.editingMem = d.id; refresh(); setTimeout(() => $('[data-form="edit-mem"] input')?.focus(), 0); },
    'mem-forget': d => { const m = S.memory.find(x => x.id === d.id); S.memory = S.memory.filter(x => x.id !== d.id); if (m) log(`按你的要求忘掉了一条记忆`); save(); toast('已经忘掉了'); refresh(); },

    'step-done': d => {
      const m = findMsg(d.m); if (!m) return;
      m.card.state = 'done';
      addRecord('step', m.card.text);
      const w = S.wishes.find(x => x.id === m.card.wid);
      if (w) { w.tries = (w.tries || 0) + 1; const s = w.steps.find(x => x.text === m.card.text); if (s) s.done = true; }
      log(`完成一小步：「${clip(m.card.text, 16)}」`);
      save(); renderThread(); renderSide();
      aiSay(S.active, [{ text: pick(['好，这一步算数。', '做到了。小步子也是步子。', '记下了。今天的你，往那边走了一点。']) }]);
    },
    'step-swap': d => {
      const m = findMsg(d.m); if (!m) return;
      const w = S.wishes.find(x => x.id === m.card.wid);
      m.card.alt = (m.card.alt || 0) + 1;
      const old = m.card.text;
      m.card.text = suggestStep(w ? w.title : '', m.card.alt);
      if (m.card.text === old) m.card.text = suggestStep('', m.card.alt);
      if (w) { const s = w.steps.find(x => x.text === old && !x.done); if (s) s.text = m.card.text; }
      save(); renderThread(); renderSide();
    },
    'step-skip': d => { const m = findMsg(d.m); if (!m) return; m.card.state = 'skip'; save(); renderThread(); },

    'good-yes': d => { const m = findMsg(d.m); if (!m) return; m.card.state = 'saved'; addRecord('good', m.card.text); log(`收下一条好消息：「${clip(m.card.text, 16)}」`); save(); renderThread(); renderSide(); aiSay(S.active, [{ text: `存好了，这是第 ${count('good')} 条。` }]); },
    'good-no': d => { const m = findMsg(d.m); if (!m) return; m.card.state = 'no'; save(); renderThread(); },
    'wish-yes': d => {
      const m = findMsg(d.m); if (!m) return;
      m.card.state = 'yes';
      const w = { id: uid(), title: m.card.text, why: '', steps: [{ text: suggestStep(m.card.text), done: false }], tries: 0, t: Date.now() };
      S.wishes.push(w); log(`新愿景：「${clip(w.title, 16)}」`);
      openSide(clip(w.title, 14), w.id);
    },
    'wish-no': d => { const m = findMsg(d.m); if (!m) return; m.card.state = 'no'; save(); renderThread(); aiSay(S.active, [{ text: '好，先放在对话里。哪天想认真聊，跟我说一声。' }]); },

    'open-report': d => { ui.report = { days: +d.days, hide: [] }; ui.layer = 'report'; renderLayer(); },
    'report-days': d => { ui.report.days = +d.v; renderLayer(); },
    'report-toggle': (d, el) => { const h = ui.report.hide; const i = h.indexOf(d.v); if (el.checked && i >= 0) h.splice(i, 1); if (!el.checked && i < 0) h.push(d.v); renderLayer(); },
    'report-copy': () => {
      const txt = ui.report.text || '';
      (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(() => toast('已复制文字版'), () => toast('浏览器不允许复制，请手动选择文字'));
    },

    tip: d => { if (d.t === '今天想偷懒') return userSend('main', d.t, { plain: true }); const ta = $('#input'); ta.value = d.t; autosize(ta); ta.focus(); },
    'tips-hide': () => { S.tipsHidden = true; save(); renderDock(); },
    'mode-good': () => { ui.composeMode = ui.composeMode === 'good' ? 'text' : 'good'; renderDock(true); },
    'mode-text': () => { ui.composeMode = 'text'; renderDock(true); },
    rest: () => { if (ui.busy) return; push(S.active, { from: 'me', text: '今天想偷懒' }); renderThread(); restFlow(S.active); },
    'rest-here': () => {
      if (!S.records.some(r => r.type === 'rest' && r.date === dkey())) { addRecord('rest', '今天偷懒'); log('把今天标成偷懒日'); }
      save(); toast('今天是偷懒日，之前的记录都还在'); refresh();
    },

    'answer-discovery': () => askInMain((new Date().getHours() < 11 ? '早上好。' : '') + `今天的问题：${discoveryToday()}`, true),
    'idea-chat': d => { const x = ideaList().find(i => i.id === d.id); if (x) askInMain(`我们聊聊这个吧：${x.text}`); },
    'idea-try': d => {
      const x = ideaList().find(i => i.id === d.id); if (!x) return;
      const w = S.wishes.find(v => v.id === x.wid) || activeWish();
      if (w) { w.steps.push({ text: x.step, done: false }); toast(`加到了「${clip(w.title, 10)}」`); }
      else { S.wishes.push({ id: uid(), title: '照顾好自己', why: '', steps: [{ text: x.step, done: false }], tries: 0, t: Date.now() }); toast('加到了愿景'); }
      S.ideasHidden.push(x.id); log(`把「${clip(x.step, 14)}」加进愿景`);
      save(); refresh();
    },
    'idea-hide': d => { S.ideasHidden.push(d.id); save(); refresh(); },
    freq: d => { S.proactive = d.v; log(`主动频率改为「${FREQ.find(f => f.id === d.v).label}」`); save(); refresh(); },

    'wish-step': d => {
      const w = S.wishes.find(x => x.id === d.id); const s = w && w.steps[+d.i]; if (!s) return;
      s.done = !s.done;
      if (s.done) { addRecord('step', s.text); w.tries = (w.tries || 0) + 1; toast('这一步算数'); }
      save(); refresh();
    },
    'wish-step-next': d => { const w = S.wishes.find(x => x.id === d.id); const s = nextStep(w); if (!s) return; s.done = true; addRecord('step', s.text); w.tries = (w.tries || 0) + 1; log(`完成一小步：「${clip(s.text, 16)}」`); save(); toast('这一步算数'); refresh(); },
    'wish-chat': d => {
      const w = S.wishes.find(x => x.id === d.id); if (!w) return;
      const existing = S.side.find(id => T(id) && T(id).wishId === w.id);
      if (existing) { S.active = existing; return go('chat'); }
      openSide(clip(w.title, 14), w.id);
    },
    'wish-edit': d => { ui.editingWish = d.id; refresh(); setTimeout(() => $('[data-form="edit-wish"] input')?.focus(), 0); },
    'wish-park': d => { const w = S.wishes.find(x => x.id === d.id); if (w) { w.parked = true; toast('先放一放，随时可以回来'); } save(); refresh(); },
    'wish-unpark': d => { const w = S.wishes.find(x => x.id === d.id); if (w) w.parked = false; save(); refresh(); },

    'quick-type': d => { ui.quickType = d.v; refresh(); $('#quickInput')?.focus(); },
    'rec-filter': d => { ui.recFilter = d.v; refresh(); },

    hue: d => { S.companion.hue = d.v; save(); if (!S.onboarded) { const n = $('#obName'); if (n) S.companion.name = n.value.trim() || '小光'; } render(); },
    depth: d => {
      S.depth = d.v; save();
      if (!S.onboarded) return renderOnboard();
      refresh();
    },
    'more-q': () => askInMain('那我们多聊一点：最近一次觉得自己挺棒的，是什么时候？'),
    demo: () => { S = demoState(); ui.obStep = 0; maybeProactive(); save(); render(); toast('已载入 12 天示例'); },
    reset: () => {
      if (!confirm('清空所有对话、记录和记忆，重新开始？这一步不能撤销。')) return;
      localStorage.removeItem(KEY); S = fresh(); ui.obStep = 0; ui.layer = null; render();
    },

    'ob-next': () => { const n = $('#obName'); S.companion.name = (n && n.value.trim()) || '小光'; ui.obStep = 1; save(); renderOnboard(); },
    'ob-back': () => { ui.obStep = 0; renderOnboard(); },
    'ob-start': () => startObChat(),
  };

  function refresh() { renderView(); renderRail(); renderTop(); renderSide(); renderTabbar(); }

  document.addEventListener('click', e => {
    const el = e.target.closest('[data-act]');
    if (!el || el.tagName === 'INPUT') return;
    const h = handlers[el.dataset.act];
    if (h) { e.preventDefault(); h(el.dataset, el); }
  });
  document.addEventListener('change', e => {
    const el = e.target;
    if (el.matches('input[data-act]')) handlers[el.dataset.act]?.(el.dataset, el);
  });

  document.addEventListener('submit', e => {
    const f = e.target;
    e.preventDefault();
    if (f.id === 'composer') {
      const ta = $('#input'); const v = ta.value; ta.value = ''; autosize(ta);
      return userSend(S.active, v);
    }
    const input = f.querySelector('input');
    const v = input ? input.value.trim() : '';
    const kind = f.dataset.form;
    if (kind === 'add-wish' && v) {
      const w = { id: uid(), title: v, why: '', steps: [{ text: suggestStep(v), done: false }], tries: 0, t: Date.now() };
      S.wishes.push(w); log(`新愿景：「${clip(v, 16)}」`); save(); toast('加好了，第一小步也准备好了'); refresh();
    }
    if (kind === 'edit-wish') { const w = S.wishes.find(x => x.id === f.dataset.id); if (w && v) w.title = v; ui.editingWish = null; save(); refresh(); }
    if (kind === 'edit-mem') { const m = S.memory.find(x => x.id === f.dataset.id); if (m && v) { m.text = v; m.source = 'confirmed'; } ui.editingMem = null; save(); toast('改好了'); refresh(); }
    if (kind === 'rename' && v) { S.companion.name = v.slice(0, 8); save(); toast(`以后叫我${S.companion.name}`); render(); }
    if (kind === 'quick' && v) {
      addRecord(ui.quickType, v); log(`记下${TYPE_LABEL[ui.quickType]}：「${clip(v, 14)}」`); save();
      toast(ui.quickType === 'good' ? `存好了，第 ${count('good')} 条好消息` : '存好了'); refresh();
      setTimeout(() => $('#quickInput')?.focus(), 0);
    }
  });

  document.addEventListener('keydown', e => {
    if (e.target.id === 'input' && e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('#composer').requestSubmit(); }
    if (e.target.id === 'obName' && e.key === 'Enter') handlers['ob-next']();
    if (e.key === 'Escape' && ui.layer) { ui.layer = null; renderLayer(); }
  });
  document.addEventListener('input', e => { if (e.target.id === 'input') autosize(e.target); });

  /* ───────── demo data (12 天示例) ───────── */
  function demoState() {
    const s = fresh();
    s.onboarded = true; s.companion = { name: '小光', hue: 'mist' }; s.depth = 'm';
    const base = addDays(new Date(), -11);
    s.start = dkey(base);
    const at = (off, h, m = 0) => { const d = addDays(base, off); d.setHours(h, m, 0, 0); return d.getTime(); };
    s.profile = { praise: ['好奇', '认真', '会照顾人'], flaws: ['拖延', '三分钟热度', '容易焦虑'], mbti: 'INFP', star: '双鱼座', high: '' };
    const mem = (text, source, off) => ({ id: uid(), text, source, t: at(off, 21) });
    const m1 = mem('你在读书这件事上，比自己以为的更能坚持', 'confirmed', 6);
    const m2 = mem('有具体的人需要你时，你更容易开始行动', 'guess', 10);
    s.memory = [
      ...s.profile.praise.map(w => mem(`你夸自己「${w}」`, 'self', 0)),
      ...s.profile.flaws.map(w => mem(`你觉得自己「${w}」`, 'self', 0)),
      mem('「三分钟热度」更像是好奇心在找方向', 'confirmed', 3),
      m1, m2,
      mem('早上比晚上更容易进入状态', 'guess', 9),
    ];
    s.wishes = [
      { id: 'w1', title: '一年后，能靠写作有一点自己的收入', why: '想证明自己能把一件喜欢的事做久', tries: 9, t: at(0, 21),
        steps: [{ text: '每天读 10 页书', done: true }, { text: '写一段 200 字的读书笔记', done: true }, { text: '找一个可以投稿的平台看看', done: false }] },
      { id: 'w2', title: '更自在地表达自己', why: '在课上和小组里，常常想好了却没说出口', tries: 2, t: at(4, 20),
        steps: [{ text: '在课上说一次自己的想法', done: true }, { text: '今天主动和一个人多说一句话', done: false }] },
    ];
    const R = [
      [0, 'good', '第一次认真想了一年后的自己', 22], [0, 'step', '读了 10 页《被讨厌的勇气》', 23],
      [1, 'good', '食堂阿姨多给了一块排骨', 12], [1, 'step', '读了 12 页', 22],
      [2, 'rest', '今天偷懒', 20],
      [3, 'good', '小组作业被老师点名表扬', 15], [3, 'find', '原来我读书的时候不会分心', 21],
      [4, 'step', '写了第一段读书笔记，213 字', 22], [4, 'good', '和室友聊到很晚，很开心', 23],
      [5, 'good', '雨停的时候看到了彩虹', 17],
      [6, 'step', '读了 10 页', 21], [6, 'find', '帮朋友改简历时，我特别投入', 21],
      [7, 'rest', '今天偷懒', 19],
      [8, 'good', '终于把拖了一周的邮件发出去了', 11], [8, 'step', '读了 15 页', 22],
      [9, 'good', '跑步时随机到了最喜欢的歌', 19],
      [10, 'step', '在课上举手回答了一个问题', 10], [10, 'good', '学妹说我讲题讲得很清楚', 16],
      [11, 'good', '早起看到很好看的云', 7],
    ];
    s.records = R.map(([off, type, text, h]) => ({ id: uid(), type, text, date: dkey(addDays(base, off)), t: at(off, h, 10) }));
    const M = (off, h, mi, from, text, extra = {}) => ({ id: uid(), from, text, t: at(off, h, mi), ...extra });
    s.threads.main.msgs = [
      M(0, 21, 0, 'ai', '你好，我是小光。接下来的日子，我陪你一点点认识自己。'),
      M(0, 21, 5, 'ai', '最后一个问题，不用急着回答好：一年后的你，想成为什么样的人？'),
      M(0, 21, 6, 'me', '一年后，能靠写作有一点自己的收入'),
      M(0, 21, 6, 'ai', '记下了。这是一个随时可以改的方向，不是承诺。'),
      M(0, 21, 6, 'ai', '为了靠近它，今天可以只做很小的一步：', { card: { type: 'step', wid: 'w1', text: '每天读 10 页书', state: 'done' } }),
      M(6, 20, 0, 'ai', '晚上好。今天过得怎么样？有一件小好事也算，什么都没有也没关系。', { proactive: true }),
      M(6, 21, 2, 'me', '今天读书的时候完全没看手机'),
      M(6, 21, 2, 'ai', '这是你第三次提到读书时很专注。你说过自己「三分钟热度」，但在读书这件事上，好像不太一样。'),
      M(6, 21, 3, 'ai', '我想记住这条：', { card: { type: 'memory', mid: m1.id } }),
      M(7, 19, 40, 'me', '今天想偷懒'),
      M(7, 19, 40, 'ai', '好，今天就是偷懒日。'),
      M(7, 19, 41, 'ai', '', { card: { type: 'rest', goods: 6, steps: 4 } }),
      M(10, 9, 0, 'ai', '早上好。今天的问题：别人常找你帮什么忙？那可能是你没注意到的长处。', { proactive: true, discovery: DISCOVERY[1] }),
      M(10, 16, 20, 'me', '好像经常有人找我讲题，今天学妹还说我讲得很清楚', { good: true }),
      M(10, 16, 20, 'ai', '收好了。会讲题，说明你能把复杂的东西说清楚。这和你想靠写作有收入，是不是有点关系？'),
      M(10, 16, 21, 'ai', '我有一个小猜测，不一定对：', { card: { type: 'memory', mid: m2.id } }),
      M(10, 20, 30, 'ai', '这 10 天的蜕变报告整理好了。不是打卡统计，是你这段时间的样子。', { card: { type: 'report', days: 10 } }),
    ];
    s.threads.side1 = { id: 'side1', title: '靠写作有收入', wishId: 'w1', stage: null, msgs: [
      M(1, 22, 0, 'ai', '这里专门聊「一年后，能靠写作有一点自己的收入」。主线里说过的事，我都记得。'),
      M(1, 22, 0, 'ai', '先说说：你为什么想要它？'),
      M(1, 22, 3, 'me', '想证明自己能把一件喜欢的事做久'),
      M(1, 22, 3, 'ai', '这个理由很好，我把它写进愿景里了。'),
    ] };
    s.side = ['side1'];
    s.activity = [
      { t: at(0, 21), text: '第一次见面' }, { t: at(0, 21, 6), text: '记下第一个愿景：「一年后，能靠写作有一点…」' },
      { t: at(6, 21, 3), text: '你确认了：「你在读书这件事上，比自己以为的…」' },
      { t: at(7, 19, 40), text: '把今天标成偷懒日' },
      { t: at(9, 23), text: '整理昨天的对话，提出 1 条猜测等你确认' },
      { t: at(10, 9), text: '带来今天的问题' }, { t: at(10, 20, 30), text: '整理好 10 天蜕变报告' },
    ];
    s.lastProactive = dkey(addDays(new Date(), -1));
    s.view = 'chat'; s.active = 'main';
    return s;
  }

  /* ───────── boot ───────── */
  // index.html#demo loads the 12-day sample; #demo/records etc. also opens that page
  const hash = location.hash.slice(1).split('/');
  if (hash[0] === 'demo') {
    S = demoState();
    if (NAV.some(n => n.id === hash[1])) S.view = hash[1];
    if (hash[2] === 'report') { ui.report = { days: 10, hide: [] }; ui.layer = 'report'; }
    if (hash[2] === 'activity') ui.layer = 'activity';
    history.replaceState(null, '', location.pathname);
  }
  maybeProactive();
  save();
  render();
})();

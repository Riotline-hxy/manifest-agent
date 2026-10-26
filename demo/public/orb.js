/* orb.js — 小光's face. Thin adapter over the Emotion Ball engine
   (github.com/sam70361/aora-bot, community license: non-commercial demo use;
   the ball body visual may never be used commercially — see vendor/emotion-ball/NOTICE.md).

   Orb.mount(el, {size, hue, emotion}) -> handle {set(id), react(kind), hue(c), destroy()}
   Every mounted orb follows the pointer. If the engine fails to load, a CSS orb
   with the same API is used so the page never breaks. */
(function () {
  'use strict';
  var live = [];
  var hasEngine = !!(window.EmotionBall && window.EmotionBall.create);

  // product state -> emotion id (ids are the engine's stable public contract)
  var STATE = {
    idle: '02', curious: '03', happy: '10', sad: '12', surprised: '13', shy: '14', tired: '15',
    focused: '16', satisfied: '19', thinking: '30', receiving: '31', done: '33', error: '34',
    listening: '35', recall: '37', replying: '39', searching: '40', sleep: '00', wake: '01'
  };

  function cssOrb(el, o) {
    el.classList.add('orb-css');
    el.innerHTML = '<i class="orb-eye"></i><i class="orb-eye"></i>';
    el.style.setProperty('--hue', o.hue);
    return {
      set: function (id) { el.dataset.emotion = id; },
      react: function () {},
      hue: function (c) { el.style.setProperty('--hue', c); },
      gaze: function () {},
      destroy: function () { el.innerHTML = ''; }
    };
  }

  function mount(el, opts) {
    var o = Object.assign({ size: 64, hue: '#8a7dff', emotion: '02', lite: null }, opts || {});
    el.classList.add('orb');
    el.style.width = el.style.height = o.size + 'px';
    var h;
    if (!hasEngine) {
      h = cssOrb(el, o);
    } else {
      try {
        var ball = window.EmotionBall.create(el, {
          emotion: o.emotion, shape: 'blob', color: o.hue,
          eyeScale: o.size < 80 ? 1.6 : 1, lite: o.lite != null ? o.lite : o.size < 120,
          idle: o.size >= 120 ? { standbyAfter: 60000, sleepAfter: 300000 } : false
        });
        var cur = o.emotion;
        h = {
          ball: ball,
          set: function (id) {
            id = STATE[id] || id;
            if (id === cur) return;
            cur = id;
            ball.setEmotion(id);
            if (id === '30') ball.spin(1);
          },
          react: function (kind) {
            if (kind === 'bounce') ball.bounce();
            else if (kind === 'burst') { ball.burst(28); ball.spin(2); }
            else if (kind === 'spin') ball.spin(2);
          },
          hue: function (c) {
            // engine reads colour at create time; rebuild keeps the API simple
            ball.destroy(); el.innerHTML = '';
            var n = mount(el, Object.assign({}, o, { hue: c, emotion: cur }));
            Object.assign(h, n);
          },
          gaze: function (x, y) { ball.setGaze(x, y); },
          destroy: function () { ball.destroy(); }
        };
        el.dataset.emotionEngine = 'emotion-ball';
      } catch (e) {
        console.warn('[orb] engine failed, using CSS orb', e);
        h = cssOrb(el, o);
      }
    }
    h.el = el;
    live = live.filter(function (x) { return x.el !== el; });
    live.push(h);
    return h;
  }

  // one listener drives every orb's gaze, relative to each orb's own centre
  var raf = 0, px = 0, py = 0;
  window.addEventListener('pointermove', function (e) {
    px = e.clientX; py = e.clientY;
    if (raf) return;
    raf = requestAnimationFrame(function () {
      raf = 0;
      live = live.filter(function (h) { return h.el.isConnected; });
      live.forEach(function (h) {
        var r = h.el.getBoundingClientRect();
        if (!r.width) return;
        var nx = (px - (r.left + r.width / 2)) / (window.innerWidth / 2);
        var ny = (py - (r.top + r.height / 2)) / (window.innerHeight / 2);
        h.gaze(Math.max(-1, Math.min(1, nx)), Math.max(-1, Math.min(1, ny)));
      });
    });
  }, { passive: true });

  // pause off-screen engines
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        var h = live.find(function (x) { return x.el === e.target; });
        if (h && h.ball) h.ball.setActive(e.isIntersecting);
      });
    });
    var _mount = mount;
    mount = function (el, opts) { var h = _mount(el, opts); io.observe(el); return h; };
  }

  window.Orb = { mount: function (el, o) { return mount(el, o); }, STATE: STATE, engine: hasEngine };
})();

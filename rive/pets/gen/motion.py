"""宠物动作设计：一套共用动作 + 每条路线一个招式。

原则：动作少而精、要有重量感。每个动作都有预备、主动作、跟随和回弹，
节奏放慢到像真的小动物（参考宝可梦 / 洛克王国的宠物待机和互动），不做弹球式的快速蹦跳。

  待机 Idle      呼吸、慢慢环顾、偶尔抖耳朵、尾巴轻摆、随机眨眼
  打招呼 Greet   指针移入：轻轻挺身、竖耳、歪头（一次）
  关注 Attention 保持歪头、竖耳、尾巴慢摇
  摸一摸 Petting 放松地闭眼（∪）、腮红、把头蹭向手、尾巴摇、冒一颗心
  庆祝 Celebrate 下蹲蓄力 → 轻轻跳起、在空中停一下 → 软着陆 → 开心地左右晃，眼睛 ^^（∩）
  犯困 Doze      眼皮慢慢往下掉、撑开一下、再合上，头一点一点低下去
  睡觉 Sleep     闭眼（∪）、低头歪头、耳朵耷拉、深呼吸、Zz
  醒来 Wake      半睁眼 → 又眯一下 → 睁开 → 伸懒腰 → 慢慢甩头
  招式 Skill     路线专属（余温 / 留芳 / 回澜 / 连星），初生和抽芽期没有

眼皮：睫毛（按原画轮廓做的）往下走，它上面盖上皮肤；合上后换成一条闭眼线。
"""
from riv import Anim, fmt, wave

SM_EASE = '<CubicEaseInterpolator x1="0.4" y1="0" x2="0.2" y2="1"/>'

# 眼睛状态：睫毛往下走了多少（相对完全闭上）
PARTIAL = {"quarter": 0.25, "half": 0.5, "low": 0.75}
CLOSED = ("shut", "joy", "blink")
# 睫毛走到底时压扁到多少（1 = 原画的弧度）：放松闭眼压成几乎平的一条，开心闭眼保留一点 ∩
FLAT = {"shut": 0.32, "joy": 0.72, "blink": 0.35}


def eye_points(L, seq, close_ease="sio", open_ease="sio"):
    """把眼睛状态序列 [(帧, 状态)] 展开成关键点。

    闭眼分三段：① 睫毛往下走、慢慢压扁，皮肤跟着从上往下盖（裁剪边始终藏在睫毛下面）
               ② 睫毛到位，皮肤把剩下的一点眼睛盖满
               ③ 睫毛淡出、闭眼线淡入（形状已经很接近，看起来是同一条线）
    睁眼倒过来。"""
    def V(st):
        if st == "open":
            return dict(edge=L["edge_open"], ly=0.0, sy=1.0, lo=0, so=0, jo=0, bo=1)
        if st in PARTIAL:
            ly = L["lash_shut"] * PARTIAL[st]
            return dict(edge=ly + L["cover"], ly=ly, sy=1.0 - 0.25 * PARTIAL[st], lo=1, so=0, jo=0, bo=0)
        ty = L["lash_joy"] if st == "joy" else L["lash_shut"] * (0.85 if st == "blink" else 1)
        return dict(edge=L["edge_full"], ly=ty, sy=FLAT[st], lo=1 if st == "blink" else 0,
                    so=1 if st == "shut" else 0, jo=1 if st == "joy" else 0, bo=0)

    def follow(st):  # 睫毛已到位、皮肤还没盖满的那一刻
        v = V(st)
        return dict(v, edge=v["ly"] + L["cover"], lo=1, so=0, jo=0)

    def covered(st):  # 皮肤盖满、闭眼线还没出来
        return dict(V(st), lo=1, so=0, jo=0)

    pts = []  # [frame, values, 位置缓动, 透明度插值]
    for i, (f1, s1) in enumerate(seq):
        if i == 0:
            pts.append([f1, V(s1), close_ease, "hold"])
            continue
        f0, s0 = seq[i - 1]
        d = f1 - f0
        if s1 == s0:
            pts.append([f1, V(s1), close_ease, "hold"])
            continue
        closing = s1 in CLOSED and s0 not in CLOSED
        opening = s0 in CLOSED and s1 not in CLOSED
        if closing:
            pts[-1][1] = {**pts[-1][1], "lo": 1, "bo": 0}       # 睫毛月牙接替原画睫毛，眨眼暂停
            pts[-1][2] = close_ease
            if s1 == "blink":
                pts.append([f1, V(s1), open_ease, "hold"])
            else:
                pts.append([f0 + max(1, round(0.66 * d)), follow(s1), "sio", "hold"])
                pts.append([f0 + max(2, round(0.8 * d)), covered(s1), "sio", "linear"])
                pts.append([f1, V(s1), open_ease, "hold"])
        elif opening:
            pts[-1][2] = open_ease
            if s0 == "blink":
                pts.append([f1, dict(V(s1), lo=1), close_ease, "hold"])
            else:
                pts[-1][3] = "linear"                        # 闭眼线淡出、睫毛淡入
                pts.append([f0 + max(1, round(0.18 * d)), covered(s0), "sio", "hold"])
                pts.append([f0 + max(2, round(0.32 * d)), follow(s0), open_ease, "hold"])
                pts.append([f1, dict(V(s1), lo=1), close_ease, "hold"])
            if s1 == "open":
                pts.append([f1 + 1, V("open"), close_ease, "hold"])
        else:
            if s0 == "open" and s1 != "open":
                pts[-1][1] = {**pts[-1][1], "lo": 1, "bo": 0}   # 开始动的那一刻就由睫毛月牙接替，眨眼暂停
            if s1 == "open":
                pts.append([f1, dict(V(s1), lo=1), close_ease, "hold"])
                pts.append([f1 + 1, V("open"), close_ease, "hold"])
            else:
                pts.append([f1, V(s1), close_ease, "hold"])
    return pts


def eye_keys(a, eyes, seq, kind="Hold", **kw):
    for side, e in zip("LR", eyes):
        L = e["lid"]
        pts = eye_points(L, seq, **kw)
        a.key(f"{kind}Edge{side}", "y", [(f, v["edge"], pe) for f, v, pe, _ in pts])
        a.key(f"{kind}Lash{side}", "y", [(f, L["lash_c0"] + v["ly"], pe) for f, v, pe, _ in pts])
        a.key(f"{kind}Lash{side}", "scaleY", [(f, v["sy"], pe) for f, v, pe, _ in pts])
        a.key(f"{kind}Lash{side}", "opacity", [(f, v["lo"], po) for f, v, _, po in pts])
        if kind == "Hold":
            a.key(f"BlinkSet{side}", "opacity", [(f, v["bo"], "hold") for f, v, _, _ in pts])
            a.key(f"HoldShut{side}", "opacity", [(f, v["so"], po) for f, v, _, po in pts])
            a.key(f"HoldJoy{side}", "opacity", [(f, v["jo"], po) for f, v, _, po in pts])


def motion(ctx, ids):
    B, W, spec = ctx["bones"], ctx["W"], ctx["spec"]
    chains, eyes = ctx["chains"], ctx["eyes"]
    ears = [c for c in chains if c["kind"] in ("ear", "gill")]
    tails = [c for c in chains if c["kind"] == "tail"]
    tilt = spec.get("tilt", 1)
    H = ctx["h_world"]
    for c in chains:  # 幅度系数：让不同长度的耳朵 / 尾巴尖端摆动距离差不多
        ref = 0.3 if c["kind"] in ("ear", "gill") else 0.5
        c["k"] = max(0.35, min(1.25, ref * H / c["length"]))
    hop = H * 0.13
    route = spec.get("route")

    # ── 头部附近的特效位置（世界坐标）──
    head_xs = [W(p)[0] for p in spec["head"]]
    hx0, hx1 = min(head_xs), max(head_xs)
    hy0 = W(spec["crown"])[1]  # 特效以头顶为准（不算鹿角、耳朵）
    hcx, hw = (hx0 + hx1) / 2, hx1 - hx0
    ground = W(spec["ground"])

    # ── 静止值：每个动作动画都把这些属性全写上，状态之间才能平滑混合 ──
    L_body = B["Body"]["length"]
    rest = {
        ("Root", "x"): B["Root"]["local"][0], ("Root", "y"): B["Root"]["local"][1],
        ("Root", "rotation"): B["Root"]["rel"], ("Root", "scaleX"): 1, ("Root", "scaleY"): 1,
        ("Body", "rotation"): B["Body"]["rel"], ("Body", "length"): L_body,
        ("Head", "rotation"): B["Head"]["rel"],
        ("Shadow", "scaleX"): 1, ("Shadow", "opacity"): 1,
        ("Sparkles", "opacity"): 0, ("Heart", "opacity"): 0, ("Zz", "opacity"): 0,
    }
    for c in chains:
        for nm in c["bones"]:
            rest[(nm, "rotation")] = B[nm]["rel"]
    for side, e in zip("LR", eyes):
        rest[(f"HoldEdge{side}", "y")] = e["lid"]["edge_open"]
        rest[(f"HoldLash{side}", "y")] = e["lid"]["lash_c0"]
        rest[(f"HoldLash{side}", "scaleY")] = 1
        rest[(f"HoldLash{side}", "opacity")] = 0
        rest[(f"HoldShut{side}", "opacity")] = 0
        rest[(f"HoldJoy{side}", "opacity")] = 0
        rest[(f"Blush{side}", "opacity")] = 0
        rest[(f"BlinkSet{side}", "opacity")] = 1
    if route:
        rest[("Skill", "opacity")] = 0

    def act(name, dur, loop="oneShot"):
        a = Anim(name, dur, loop)
        for (o, p), v in rest.items():
            a.key(o, p, [(0, v)])
        return a

    def off(a, obj, prop, keys, ease="sio"):
        """关键帧写成相对静止值的偏移。"""
        r = rest[(obj, prop)]
        a.key(obj, prop, [(k[0], r + k[1]) + tuple(k[2:]) for k in keys], ease)

    def both(a, prefix, prop, keys, ease="sio"):
        for side in "LR":
            a.key(f"{prefix}{side}", prop, keys, ease)

    def ears_off(a, keys, lag=4, tip=0.7):
        """耳朵：keys 是“竖起”方向的角度（正 = 竖起，负 = 耷拉），尖端骨骼滞后几帧、幅度小一点。"""
        for c in ears:
            for i, nm in enumerate(c["bones"]):
                k = 1 if i == 0 else tip
                d = 0 if i == 0 else lag * i
                off(a, nm, "rotation", [(min(f + d, a.dur) if 0 < f < a.dur else f, v * c["perk"] * k * c["k"]) + tuple(r)
                                        for f, v, *r in keys])

    def tails_wave(a, amp, period, start, end, env=None, base=0.0):
        for c in tails:
            n = len(c["bones"])
            for i, nm in enumerate(c["bones"]):
                k = (0.75 + 0.5 * i / max(n - 1, 1)) * c["k"]
                a.key(nm, "rotation", wave(rest[(nm, "rotation")] + base, amp * k, period, start + i * (period // 4),
                                           start, end, env))

    def env_ramp(t0, t1, r=12):
        return lambda t: max(0.0, min(1.0, (t - t0) / r, (t1 - t) / r))

    def eyes_seq(a, seq, **kw):
        eye_keys(a, eyes, seq, "Hold", **kw)

    anims = []

    # ── 呼吸层（身体骨骼沿脊柱轻微伸缩）──
    a = Anim("BreathAwake", 228, "loop")
    a.key("Body", "scaleX", [(0, 1, "sio"), (114, 1.02, "sio"), (228, 1)])
    anims.append(a)
    a = Anim("BreathSleep", 300, "loop")
    a.key("Body", "scaleX", [(0, 0.99, "sio"), (150, 1.032, "sio"), (300, 0.99)])
    anims.append(a)

    # ── 眨眼层：一次单眨 + 一次连眨，间隔不规则；合眼快、睁眼慢 ──
    a = Anim("Blink", 384, "loop")
    seq = [(0, "open")]
    for t in (124, 296, 312):
        seq += [(t, "open"), (t + 5, "blink"), (t + 7, "blink"), (t + 15, "open")]
    seq.append((384, "open"))
    eye_keys(a, eyes, seq, "Blink", close_ease="in", open_ease="outs")
    anims.append(a)

    # ── 动作层 ──
    # 待机：8 秒一轮，慢慢环顾，左右耳各抖一次，尾巴摆
    a = act("Idle", 480, "loop")
    a.key("Head", "rotation", wave(rest[("Head", "rotation")], 0.022, 480, 0, 0, 480))
    for c, f0 in zip(ears, (150, 340, 250, 60)):
        for i, nm in enumerate(c["bones"]):
            k, d = (1, 0) if i == 0 else (0.8, 4 * i)
            r0 = rest[(nm, "rotation")]
            v = -0.15 * c["perk"] * k * c["k"]
            a.key(nm, "rotation", [(0, r0), (f0 + d, r0, "outs"), (f0 + d + 7, r0 + v), (f0 + d + 17, r0 - v * 0.35),
                                   (f0 + d + 28, r0 + v * 0.1), (f0 + d + 40, r0), (480, r0)])
    tails_wave(a, 0.045, 240, 0, 480)
    anims.append(a)

    # 打招呼：轻轻挺身、竖耳、歪头（1 秒）
    a = act("Greet", 60)
    off(a, "Root", "y", [(0, 0), (10, 0), (28, -hop * 0.08), (44, 0), (60, 0)])
    a.key("Root", "scaleX", [(0, 1), (10, 0.975), (28, 1.035), (44, 1.018), (60, 1.02)], "sio")
    a.key("Root", "scaleY", [(0, 1), (10, 1.015), (28, 0.985), (44, 0.992), (60, 0.99)], "sio")
    off(a, "Head", "rotation", [(0, 0), (8, 0), (32, tilt * 0.095, "outs"), (48, tilt * 0.075), (60, tilt * 0.08)])
    ears_off(a, [(0, 0), (10, -0.03), (26, 0.16), (40, 0.07), (52, 0.1), (60, 0.09)])
    tails_wave(a, 0.09, 32, 4, 60, env_ramp(4, 60, 12))
    anims.append(a)

    # 关注：保持
    a = act("Attention", 120, "loop")
    a.key("Root", "scaleX", [(0, 1.02)])
    a.key("Root", "scaleY", [(0, 0.99)])
    a.key("Head", "rotation", wave(rest[("Head", "rotation")] + tilt * 0.08, 0.012, 120, 0, 0, 120))
    ears_off(a, [(0, 0.09)])
    tails_wave(a, 0.08, 40, 0, 120)
    anims.append(a)

    # 摸一摸：3 秒，放松地闭眼
    a = act("Petting", 180)
    eyes_seq(a, [(0, "open"), (6, "open"), (28, "shut"), (146, "shut"), (172, "open")])
    both(a, "Blush", "opacity", [(0, 0), (30, 0.8), (142, 0.8), (178, 0)])
    hr = rest[("Head", "rotation")] + tilt * 0.11
    a.key("Head", "rotation", [(0, rest[("Head", "rotation")], "sio"), (30, hr, "sout")]
          + wave(hr, 0.028, 60, 30, 30, 150)[1:-1] + [(150, hr, "sio"), (178, rest[("Head", "rotation")])])
    off(a, "Body", "rotation", [(0, 0), (32, tilt * 0.03), (150, tilt * 0.03), (178, 0)])
    a.key("Root", "scaleX", [(0, 1), (28, 0.972), (150, 0.972), (178, 1)], "sio")
    a.key("Root", "scaleY", [(0, 1), (28, 1.012), (150, 1.012), (178, 1)], "sio")
    ears_off(a, [(0, 0), (28, -0.14), (150, -0.14), (176, 0)])
    tails_wave(a, 0.11, 36, 10, 170, env_ramp(10, 170, 18))
    hx, hy = hcx + tilt * hw * 0.32, hy0 + H * 0.02
    a.key("Heart", "opacity", [(0, 0, "hold"), (40, 0, "linear"), (50, 1), (110, 1), (136, 0), (180, 0)])
    a.key("Heart", "y", [(0, hy, "hold"), (40, hy, "outs"), (136, hy - H * 0.2), (180, hy - H * 0.2)])
    a.key("Heart", "scaleX", [(0, 0.4, "hold"), (40, 0.4, "out"), (60, 1), (136, 0.85)])
    a.key("Heart", "scaleY", [(0, 0.4, "hold"), (40, 0.4, "out"), (60, 1), (136, 0.85)])
    anims.append(a)

    # 庆祝：2.8 秒。下蹲蓄力 → 轻轻跳起、在最高处停一下 → 软着陆 → 开心地左右晃
    a = act("Celebrate", 170)
    eyes_seq(a, [(0, "open"), (10, "open"), (28, "joy"), (140, "joy"), (164, "open")])
    both(a, "Blush", "opacity", [(0, 0), (30, 0.75), (140, 0.75), (168, 0)])
    off(a, "Root", "y", [(0, 0), (24, 0, "outs"), (60, -hop, "sio"), (78, -hop * 1.04, "ins"), (112, 0, "outs"), (170, 0)])
    a.key("Root", "scaleX", [(0, 1), (22, 0.92, "outs"), (32, 1.06), (50, 1.0), (78, 1.0, "ins"), (106, 1.03, "outs"),
                             (114, 0.94), (126, 1.02), (138, 0.995), (150, 1), (170, 1)], "sio")
    a.key("Root", "scaleY", [(0, 1), (22, 1.06, "outs"), (32, 0.97), (50, 1.0), (78, 1.0, "ins"), (106, 0.99, "outs"),
                             (114, 1.05), (126, 0.99), (150, 1), (170, 1)], "sio")
    sway = wave(rest[("Root", "rotation")], 0.035, 30, 118, 118, 166, env_ramp(118, 166, 10))
    a.key("Root", "rotation", [(0, rest[("Root", "rotation")]), (118, rest[("Root", "rotation")], sway[0][2])] + sway[1:]
          + [(170, rest[("Root", "rotation")])])
    off(a, "Head", "rotation", [(0, 0), (22, tilt * 0.035), (60, -tilt * 0.03), (100, tilt * 0.02), (118, tilt * 0.035),
                                (134, -tilt * 0.02), (150, tilt * 0.01), (170, 0)])
    ears_off(a, [(0, 0), (22, -0.06), (36, -0.16), (62, 0.1), (90, 0.12), (110, 0.14), (118, -0.15), (130, 0.06),
                 (142, -0.03), (154, 0), (170, 0)])
    tails_wave(a, 0.12, 30, 112, 170, env_ramp(112, 170, 12))
    a.key("Shadow", "scaleX", [(0, 1), (22, 1.05, "outs"), (60, 0.74), (78, 0.72, "ins"), (112, 1.06, "outs"), (126, 1), (170, 1)], "sio")
    a.key("Shadow", "opacity", [(0, 1), (24, 1, "outs"), (60, 0.55), (78, 0.53, "ins"), (112, 1), (170, 1)], "sio")
    a.key("Sparkles", "opacity", [(0, 1)])
    for i, t in enumerate((54, 62, 70)):
        nm = f"Spark{i}"
        a.key(nm, "opacity", [(0, 0, "hold"), (t, 0, "linear"), (t + 6, 1), (t + 30, 1), (t + 52, 0), (170, 0)])
        a.key(nm, "scaleX", [(0, 0.2, "hold"), (t, 0.2, "out"), (t + 16, 1.1), (t + 52, 0.6)])
        a.key(nm, "scaleY", [(0, 0.2, "hold"), (t, 0.2, "out"), (t + 16, 1.1), (t + 52, 0.6)])
        a.key(nm, "rotation", [(0, 0, "hold"), (t, 0, "linear"), (t + 52, 0.7 * (1 if i % 2 else -1))])
    anims.append(a)

    # 犯困：2.5 秒，眼皮往下掉 → 撑开一下 → 再合上，头一点一点低下去；结束时和「睡觉」的姿势接上
    sleep_head = rest[("Head", "rotation")] + tilt * 0.075
    a = act("Doze", 150)
    eyes_seq(a, [(0, "open"), (26, "half"), (44, "half"), (56, "quarter"), (76, "low"), (98, "low"), (126, "shut"), (150, "shut")])
    a.key("Head", "rotation", [(0, rest[("Head", "rotation")]), (60, rest[("Head", "rotation")] + tilt * 0.03),
                               (100, rest[("Head", "rotation")] + tilt * 0.065, "outs"), (106, rest[("Head", "rotation")] + tilt * 0.05),
                               (150, sleep_head)], "sio")
    a.key("Body", "length", [(0, L_body), (150, L_body * 0.95)], "sio")
    a.key("Root", "scaleX", [(0, 1), (150, 0.97)], "sio")
    a.key("Root", "scaleY", [(0, 1), (150, 1.02)], "sio")
    ears_off(a, [(0, 0), (60, -0.08), (150, -0.24)], tip=1.3)
    tails_wave(a, 0.03, 60, 0, 120, env_ramp(0, 120, 30))
    anims.append(a)

    # 睡觉
    a = act("Sleep", 240, "loop")
    eyes_seq(a, [(0, "shut"), (240, "shut")])
    a.key("Body", "length", [(0, L_body * 0.95)])
    a.key("Head", "rotation", wave(sleep_head, 0.012, 240, 0, 0, 240))
    a.key("Root", "scaleX", [(0, 0.97)])
    a.key("Root", "scaleY", [(0, 1.02)])
    ears_off(a, [(0, -0.24)], tip=1.3)
    tails_wave(a, 0.015, 240, 0, 240)
    a.key("Zz", "opacity", [(0, 1)])
    z0 = hy0 + H * 0.06
    a.key("Z1", "y", [(0, z0 + 6, "linear"), (240, z0 - H * 0.16)])
    a.key("Z1", "opacity", [(0, 0), (50, 1), (180, 1), (240, 0)])
    a.key("Z2", "y", [(0, z0 - H * 0.11, "linear"), (120, z0 - H * 0.2, "hold"), (121, z0 - H * 0.04, "linear"), (240, z0 - H * 0.11)])
    a.key("Z2", "opacity", [(0, 1), (70, 1), (120, 0, "hold"), (121, 0), (170, 1), (240, 1)])
    anims.append(a)

    # 醒来：2.6 秒。半睁眼 → 又眯一下 → 睁开 → 伸懒腰 → 慢慢甩头
    a = act("Wake", 156)
    eyes_seq(a, [(0, "shut"), (24, "low"), (38, "half"), (50, "half"), (58, "low"), (68, "half"), (88, "open"), (156, "open")])
    a.key("Body", "length", [(0, L_body * 0.95), (40, L_body)], "sio")
    a.key("Root", "scaleX", [(0, 0.97), (40, 1.0), (76, 1.065), (96, 0.97), (108, 1.01), (120, 1), (156, 1)], "sio")
    a.key("Root", "scaleY", [(0, 1.02), (40, 1.0), (76, 0.955), (96, 1.03), (108, 1.0), (156, 1)], "sio")
    shake = [(0, tilt * 0.075), (40, 0), (76, -tilt * 0.05), (96, 0), (104, 0.05), (114, -0.05), (124, 0.03),
             (134, -0.015), (144, 0), (156, 0)]
    off(a, "Head", "rotation", shake)
    ear_keys = [(0, -0.24), (40, -0.1), (76, 0.12), (96, 0)]
    ear_keys += [(f + 3, -v * 1.5) for f, v in shake if 104 <= f <= 134] + [(148, 0), (156, 0)]
    ears_off(a, ear_keys)
    tails_wave(a, 0.07, 36, 96, 156, env_ramp(96, 156, 12))
    anims.append(a)

    fx = fx_rml(ctx, ids, hcx, hw, hy0, H, tilt)
    if route:
        sk, sk_fx = skill(route, ctx, ids, act, off, ears_off, tails_wave, env_ramp, rest, hop, H, hcx, hw, hy0, ground, tilt)
        anims.append(sk)
        fx = sk_fx + fx
    return fx, anims, state_machine(ids, bool(route)), view_model(ids)


# ── 特效图形 ──────────────────────────────────────────────────────────
def star(name, size, color, ids, x=0, y=0):
    return (f'<Node x="{fmt(x)}" y="{fmt(y)}" opacity="0" name="{name}" id="{ids[name]}"><Shape name="{name}Shape">'
            f'<Star width="{fmt(size)}" height="{fmt(size)}" points="4" innerRadius="0.36" cornerRadius="1" '
            f'originX="0.5" originY="0.5" name="Path"/><Fill name="F"><SolidColor colorValue="{color}" name="C"/></Fill></Shape></Node>')


def heart_shape(size, color):
    k = size / 20
    return (f'<Ellipse x="{fmt(-4.6 * k)}" y="{fmt(-2.6 * k)}" width="{fmt(12 * k)}" height="{fmt(12 * k)}" originX="0.5" originY="0.5" name="L"/>'
            f'<Ellipse x="{fmt(4.6 * k)}" y="{fmt(-2.6 * k)}" width="{fmt(12 * k)}" height="{fmt(12 * k)}" originX="0.5" originY="0.5" name="R"/>'
            f'<Rectangle x="0" y="{fmt(1.6 * k)}" rotation="0.7853982" width="{fmt(12.2 * k)}" height="{fmt(12.2 * k)}" '
            f'cornerRadiusTL="{fmt(1.5 * k)}" originX="0.5" originY="0.5" name="B"/>'
            f'<Fill name="F"><SolidColor colorValue="{color}" name="C"/></Fill>')


def z_letter(name, size, ids, x=0, y=0):
    k = size / 14
    path = "".join(f'<StraightVertex x="{fmt(px * k)}" y="{fmt(py * k)}"/>' for px, py in ((-7, -7), (7, -7), (-7, 7), (7, 7)))
    return (f'<Node x="{fmt(x)}" y="{fmt(y)}" name="{name}" id="{ids[name]}"><Shape name="{name}Shape">'
            f'<PointsPath isClosed="false" name="Path">{path}</PointsPath>'
            f'<Stroke thickness="{fmt(3.2 * k)}" cap="round" join="round" name="S"><SolidColor colorValue="FF8FA8C8" name="C"/></Stroke>'
            f'</Shape></Node>')


def fx_rml(ctx, ids, hcx, hw, hy0, H, tilt):
    sp = H * 0.075
    sparks = "".join(star(f"Spark{i}", sz, col, ids, x, y) for i, (x, y, sz, col) in enumerate((
        (hcx - hw * 0.52, hy0 + H * 0.05, sp, "FFFFD25A"),
        (hcx + hw * 0.55, hy0 - H * 0.02, sp * 1.25, "FFFFE38A"),
        (hcx + hw * 0.08, hy0 - H * 0.12, sp * 0.8, "FFFFC94A"))))
    hx, hy = hcx + tilt * hw * 0.32, hy0 + H * 0.02
    heart = (f'<Node x="{fmt(hx)}" y="{fmt(hy)}" opacity="0" name="Heart" id="{ids["Heart"]}">'
             f'<Shape name="HeartShape">{heart_shape(H * 0.085, "FFFF8FA6")}</Shape></Node>')
    zx = hcx + tilt * hw * 0.45
    zz = (f'<Node x="{fmt(zx)}" y="0" opacity="0" name="Zz" id="{ids["Zz"]}">'
          + z_letter("Z1", H * 0.05, ids, 0, hy0 + H * 0.06)
          + z_letter("Z2", H * 0.036, ids, tilt * H * 0.07, hy0 - H * 0.05) + '</Node>')
    return (f'<Node opacity="0" name="Sparkles" id="{ids["Sparkles"]}">{sparks}</Node>' + heart + zz)


# ── 路线招式（2.5 秒，眼睛保持睁开，特效避开五官）──────────────────────────
def skill(route, ctx, ids, act, off, ears_off, tails_wave, env_ramp, rest, hop, H, hcx, hw, hy0, ground, tilt):
    a = act("Skill", 150)
    gx, gy = ground
    shapes = []
    # 共同的身体动作：蓄力（低头、压低）→ 释放（挺身、竖耳）→ 收势
    a.key("Root", "scaleX", [(0, 1), (24, 0.95), (42, 1.05), (60, 1), (150, 1)], "sio")
    a.key("Root", "scaleY", [(0, 1), (24, 1.035), (42, 0.975), (60, 1), (150, 1)], "sio")
    off(a, "Head", "rotation", [(0, 0), (24, tilt * 0.045), (44, -tilt * 0.035), (76, 0), (150, 0)])
    ears_off(a, [(0, 0), (24, -0.09), (42, 0.17), (60, 0.07), (96, 0.08), (130, 0), (150, 0)])
    a.key("Skill", "opacity", [(0, 1)])
    tails = [c for c in ctx["chains"] if c["kind"] == "tail"]

    if route == "fox":  # 余温：尾尖亮起，暖光从脚边铺开，光点升起收淡
        tails_wave(a, 0.13, 36, 16, 88, env_ramp(16, 88, 12))
        tip = ctx["W"](tails[0]["points"][-1]) if tails else (gx + hw * 0.6, gy - H * 0.5)
        shapes.append(f'<Node x="{fmt(tip[0])}" y="{fmt(tip[1])}" opacity="0" name="TipGlow" id="{ids["TipGlow"]}">'
                      f'<Shape name="S"><Ellipse width="{fmt(H * 0.11)}" height="{fmt(H * 0.11)}" originX="0.5" originY="0.5" name="P"/>'
                      f'<Fill fillRule="clockwise" name="F"><SolidColor colorValue="AAFFC46A" name="C"/><Feather strength="{fmt(H * 0.035)}" name="Fe"/></Fill></Shape></Node>')
        shapes.append(f'<Node x="{fmt(gx)}" y="{fmt(gy + 4)}" scaleX="0" scaleY="0" name="Warm" id="{ids["Warm"]}">'
                      f'<Shape name="S"><Ellipse width="{fmt(H * 1.1)}" height="{fmt(H * 0.2)}" originX="0.5" originY="0.5" name="P"/>'
                      f'<Fill fillRule="clockwise" name="F"><SolidColor colorValue="99FFA54A" name="C"/><Feather strength="{fmt(H * 0.07)}" name="Fe"/></Fill></Shape></Node>')
        a.key("TipGlow", "opacity", [(0, 0), (20, 0), (36, 0.85), (72, 0.7), (104, 0), (150, 0)])
        a.key("TipGlow", "scaleX", [(0, 0.5), (20, 0.5, "out"), (40, 1.2), (104, 0.8)])
        a.key("TipGlow", "scaleY", [(0, 0.5), (20, 0.5, "out"), (40, 1.2), (104, 0.8)])
        a.key("Warm", "scaleX", [(0, 0), (40, 0, "out"), (92, 1), (150, 1.08)])
        a.key("Warm", "scaleY", [(0, 0), (40, 0, "out"), (92, 1), (150, 1.08)])
        a.key("Warm", "opacity", [(0, 0), (40, 0), (54, 0.8), (108, 0.65), (144, 0), (150, 0)])
        for i, (dx, t) in enumerate(((-0.32, 56), (0.05, 64), (0.36, 60), (-0.12, 74))):
            nm = f"Ember{i}"
            x0, y0 = gx + dx * H, gy - H * 0.02
            shapes.append(f'<Node x="{fmt(x0)}" y="{fmt(y0)}" opacity="0" name="{nm}" id="{ids[nm]}"><Shape name="S">'
                          f'<Ellipse width="{fmt(H * 0.03)}" height="{fmt(H * 0.03)}" originX="0.5" originY="0.5" name="P"/>'
                          f'<Fill name="F"><SolidColor colorValue="FFFFC46A" name="C"/></Fill></Shape></Node>')
            a.key(nm, "y", [(0, y0), (t, y0, "outs"), (t + 60, y0 - H * 0.28)])
            a.key(nm, "opacity", [(0, 0), (t, 0, "linear"), (t + 10, 1), (t + 36, 0.9), (t + 60, 0), (150, 0)])
    elif route == "deer":  # 留芳：抬头，花瓣从花角两侧飘落，花香收淡
        crown = ctx["W"](ctx["spec"]["crown"])
        for i, (dx, t, rot) in enumerate(((-0.42, 36, 0.6), (0.4, 44, -0.4), (-0.55, 52, 0.9), (0.52, 62, -0.7), (-0.32, 70, 0.5))):
            nm = f"Petal{i}"
            x0, y0 = crown[0] + dx * H, crown[1] + H * 0.02
            shapes.append(f'<Node x="{fmt(x0)}" y="{fmt(y0)}" opacity="0" name="{nm}" id="{ids[nm]}"><Shape name="S">'
                          f'<Ellipse width="{fmt(H * 0.045)}" height="{fmt(H * 0.026)}" originX="0.5" originY="0.5" name="P"/>'
                          f'<Fill name="F"><SolidColor colorValue="FFFFB7C8" name="C"/></Fill></Shape></Node>')
            a.key(nm, "y", [(0, y0), (t, y0, "sio"), (t + 72, y0 + H * 0.55)])
            a.key(nm, "x", [(0, x0), (t, x0, "sio"), (t + 24, x0 + H * 0.05), (t + 48, x0 - H * 0.03), (t + 72, x0 + H * 0.04)])
            a.key(nm, "rotation", [(0, 0), (t, 0, "linear"), (t + 72, rot * 3)])
            a.key(nm, "opacity", [(0, 0), (t, 0, "linear"), (t + 8, 1), (t + 54, 1), (t + 72, 0), (150, 0)])
        shapes.append(f'<Node x="{fmt(crown[0])}" y="{fmt(min(crown[1], hy0) - H * 0.06)}" opacity="0" name="Bloom" id="{ids["Bloom"]}">'
                      f'<Shape name="S"><Ellipse width="{fmt(H * 0.42)}" height="{fmt(H * 0.16)}" originX="0.5" originY="0.5" name="P"/>'
                      f'<Fill fillRule="clockwise" name="F"><SolidColor colorValue="55FFC8D8" name="C"/><Feather strength="{fmt(H * 0.06)}" name="Fe"/></Fill></Shape></Node>')
        a.key("Bloom", "opacity", [(0, 0), (28, 0), (44, 1), (92, 0.6), (134, 0), (150, 0)])
        off(a, "Head", "rotation", [(0, 0), (24, tilt * 0.04), (44, -tilt * 0.07), (92, -tilt * 0.03), (150, 0)])
    elif route == "water":  # 回澜：抬起蓄势 → 轻点 → 两圈水纹扩散 → 收淡
        off(a, "Root", "y", [(0, 0), (22, -hop * 0.2, "ins"), (36, 0), (150, 0)])
        tails_wave(a, 0.11, 44, 24, 128, env_ramp(24, 128, 16))
        for i, t in enumerate((36, 56)):
            nm = f"Ripple{i}"
            shapes.append(f'<Node x="{fmt(gx)}" y="{fmt(gy + 2)}" scaleX="0" scaleY="0" opacity="0" name="{nm}" id="{ids[nm]}"><Shape name="S">'
                          f'<Ellipse width="{fmt(H * 1.0)}" height="{fmt(H * 0.22)}" originX="0.5" originY="0.5" name="P"/>'
                          f'<Stroke thickness="{fmt(H * 0.012)}" name="St"><SolidColor colorValue="FF7FD8D0" name="C"/></Stroke></Shape></Node>')
            a.key(nm, "scaleX", [(0, 0.2), (t, 0.2, "out"), (t + 68, 1.25)])
            a.key(nm, "scaleY", [(0, 0.2), (t, 0.2, "out"), (t + 68, 1.25)])
            a.key(nm, "opacity", [(0, 0), (t, 0, "linear"), (t + 5, 1), (t + 34, 0.8), (t + 68, 0), (150, 0)])
        shapes.append(f'<Node x="{fmt(gx)}" y="{fmt(gy)}" opacity="0" name="Splash" id="{ids["Splash"]}"><Shape name="S">'
                      f'<Ellipse width="{fmt(H * 0.5)}" height="{fmt(H * 0.12)}" originX="0.5" originY="0.5" name="P"/>'
                      f'<Fill fillRule="clockwise" name="F"><SolidColor colorValue="887FE3DA" name="C"/><Feather strength="{fmt(H * 0.05)}" name="Fe"/></Fill></Shape></Node>')
        a.key("Splash", "opacity", [(0, 0), (34, 0), (40, 1), (90, 0), (150, 0)])
    elif route == "star":  # 连星：尾尖轻点 → 五颗星依次亮起连成小径 → 收淡
        tails_wave(a, 0.12, 36, 10, 74, env_ramp(10, 74, 12))
        pts = [(hcx + dx * H, hy0 + dy * H) for dx, dy in ((-0.62, 0.32), (-0.42, -0.02), (-0.1, -0.16), (0.24, -0.1), (0.55, 0.18))]
        path = "".join(f'<StraightVertex x="{fmt(x)}" y="{fmt(y)}"/>' for x, y in pts)
        shapes.append(f'<Shape opacity="0" name="Link" id="{ids["Link"]}"><PointsPath isClosed="false" name="P">{path}</PointsPath>'
                      f'<Stroke thickness="{fmt(H * 0.008)}" cap="round" join="round" name="St"><SolidColor colorValue="CCC9B8FF" name="C"/>'
                      f'<TrimPath start="0" end="0" name="Trim" id="{ids["LinkTrim"]}"/></Stroke></Shape>')
        for i, (x, y) in enumerate(pts):
            t = 32 + i * 12
            shapes.append(star(f"Lux{i}", H * (0.06 if i % 2 else 0.075), "FFFFE7A0" if i % 2 else "FFD9CCFF", ids, x, y))
            a.key(f"Lux{i}", "opacity", [(0, 0), (t, 0, "linear"), (t + 6, 1), (112, 1), (140, 0), (150, 0)])
            a.key(f"Lux{i}", "scaleX", [(0, 0.2), (t, 0.2, "out"), (t + 14, 1)])
            a.key(f"Lux{i}", "scaleY", [(0, 0.2), (t, 0.2, "out"), (t + 14, 1)])
        a.key("Link", "opacity", [(0, 1), (112, 1), (140, 0), (150, 0)])
        a.key("LinkTrim", "end", [(0, 0), (32, 0, "linear"), (86, 1), (150, 1)])
    return a, f'<Node opacity="0" name="Skill" id="{ids["Skill"]}">{"".join(shapes)}</Node>'


# ── 状态机 ────────────────────────────────────────────────────────────
def cond_bool(ids, prop, v):
    return (f'<TransitionViewModelCondition><TransitionPropertyViewModelComparator><BindablePropertyBoolean>'
            f'<DataBindContext sourcePathIds="{ids["VM"]}-{ids["vm:" + prop]}" propertyKey="634"/></BindablePropertyBoolean>'
            f'</TransitionPropertyViewModelComparator><TransitionValueBooleanComparator value="{"true" if v else "false"}"/>'
            f'</TransitionViewModelCondition>')


def cond_trig(ids, prop):
    return (f'<TransitionViewModelCondition><TransitionPropertyViewModelComparator><BindablePropertyTrigger>'
            f'<DataBindContext sourcePathIds="{ids["VM"]}-{ids["vm:" + prop]}" propertyKey="686"/></BindablePropertyTrigger>'
            f'</TransitionPropertyViewModelComparator><TransitionValueTriggerComparator/></TransitionViewModelCondition>')


def tr(ids, to, ms, conds="", exit_full=False):
    ex = ' enableExitTime="true" exitTimeIsPercetange="true" exitTime="100"' if exit_full else ""
    return (f'<StateTransition stateToId="{ids["st:" + to]}" duration="{ms}" interpolationType="cubic"{ex}>'
            f'{SM_EASE}{conds}</StateTransition>')


def state_machine(ids, has_skill):
    def layer(name, states, entry):
        body = "".join(f'<AnimationState x="{x}" y="{y}" animationId="{ids["anim:" + anim]}"{" reset=" + chr(34) + "true" + chr(34) if reset else ""} '
                       f'id="{ids["st:" + key]}">{"".join(trs)}</AnimationState>'
                       for key, anim, x, y, reset, trs in states)
        return (f'<StateMachineLayer name="{name}" id="{ids["layer:" + name]}"><AnyState x="200" y="-160"/><ExitState x="420" y="-160"/>'
                f'<EntryState x="0" y="0"><StateTransition stateToId="{ids["st:" + entry]}"/></EntryState>{body}</StateMachineLayer>')

    oneshots = ["Petting", "Celebrate"] + (["Skill"] if has_skill else [])
    triggers = {"Petting": "pet", "Celebrate": "celebrate", "Skill": "skill"}

    def from_awake(extra=()):
        out = [tr(ids, s, 220, cond_trig(ids, triggers[s])) for s in oneshots]
        out.append(tr(ids, "Doze", 400, cond_bool(ids, "sleeping", True)))
        return out + list(extra)

    after = lambda: [tr(ids, "Attention", 360, cond_bool(ids, "hovered", True), True), tr(ids, "Idle", 420, "", True)]
    states = [
        ("Idle", "Idle", 160, 0, True, from_awake([tr(ids, "Greet", 220, cond_bool(ids, "hovered", True))])),
        ("Greet", "Greet", 160, 200, True, from_awake([tr(ids, "Idle", 420, cond_bool(ids, "hovered", False)),
                                                        tr(ids, "Attention", 300, "", True)])),
        ("Attention", "Attention", 380, 200, False, from_awake([tr(ids, "Idle", 480, cond_bool(ids, "hovered", False))])),
        ("Doze", "Doze", 600, 0, True, [tr(ids, "Sleep", 300, "", True), tr(ids, "Idle", 500, cond_bool(ids, "sleeping", False))]),
        ("Sleep", "Sleep", 820, 0, False, [tr(ids, "Wake", 260, cond_bool(ids, "sleeping", False))]),
        ("Wake", "Wake", 1040, 0, True, [tr(ids, "Idle", 420, "", True)]),
    ] + [(st, st, 380 + 220 * i, 400, True, after()) for i, st in enumerate(oneshots)]
    action = layer("Action", states, "Idle")
    breath = layer("Breath", [("BreathAwake", "BreathAwake", 160, 0, False, [tr(ids, "BreathSleep", 1200, cond_bool(ids, "sleeping", True))]),
                              ("BreathSleep", "BreathSleep", 380, 0, False, [tr(ids, "BreathAwake", 800, cond_bool(ids, "sleeping", False))])],
                   "BreathAwake")
    blink = layer("Blink", [("Blink", "Blink", 160, 0, False, [])], "Blink")
    return f'<StateMachine name="Pet" id="{ids["SM"]}">{breath}{blink}{action}</StateMachine>'


def view_model(ids):
    props = [("hovered", "Boolean"), ("sleeping", "Boolean"), ("pet", "Trigger"), ("celebrate", "Trigger"), ("skill", "Trigger")]
    decl = "".join(f'<ViewModelProperty{t} name="{n}" id="{ids["vm:" + n]}"/>' for n, t in props)
    inst = "".join(f'<ViewModelInstance{t} {"propertyValue=" + chr(34) + "false" + chr(34) + " " if t == "Boolean" else ""}'
                   f'viewModelPropertyId="{ids["vm:" + n]}"/>' for n, t in props)
    return (f'<ViewModel defaultInstanceId="{ids["VMI"]}" name="Pet" id="{ids["VM"]}">{decl}'
            f'<ViewModelInstance exports="true" name="Default" id="{ids["VMI"]}">{inst}</ViewModelInstance></ViewModel>')

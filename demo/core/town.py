"""我的小镇：每个人一块会慢慢长大的地，现实里做成的每件小事都在这里盖起来。

  - 等级（growth.level）决定土地多大、能建什么；金币（growth 的账本）决定买不买得起。
  - 买 = 扣金币 + 放到地上，在一个事务里做完；同一个请求号只扣一次（连点、网络重发都安全）。
  - 建筑不会坏、不会消失、不会因为中断被收走。可以挪位置、收进仓库、再放出来，都不花钱。
  - 每栋建筑记下它是哪天建的、那之前你做成了什么，小镇慢慢就是你的成长故事。
  - 到达里程碑会送一块刻着名字的纪念碑，放在仓库里，想放哪儿放哪儿。
  - 老账号第一次进来（ensure）：过去累计的经验按一半换成金币；按旧算法到过的等级记成保底，不会掉级；
    小光关于宠物 / 徽章的记忆收起来。
格子坐标 (x, y) 从 0 开始，土地变大时只往外长，已经放好的东西不用挪。

建筑素材库：public/js/buildings/<id>.js，一个文件一样东西。第一行是 @building {...} 元数据（名字、类别、
占地、默认价格、默认解锁等级、高度、介绍），下面是画法。服务器启动时读元数据，前端用 /js/buildings/all.js
（服务器把这个目录拼成一个文件）拿画法。新放进来的文件默认不上架（元数据里写 "enabled": true 的除外），
在后台「小镇」里定好价格、等级再上架；后台改的只存在 data/town_config.json，盖在默认值上面。
占地 size = [w, d]：w 沿 x、d 沿 y；放的时候可以转方向（rot=1 时 w、d 对调；正方形的占地不变，画的时候左右翻过来）。(x, y) 是占地里 x、y 都最小的那一格。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import threading
import time

from . import growth
from .util import DATA, clip, dumps, iso, loads, new_id, now

TOWN_V = 3                  # 1：开镇；2：等级换成递增曲线，老账号记下保底等级；3：新手小镇换成有屋有路有灯的样子
OLD_LEVEL_XP = 40           # 3.0 之前：每 40 经验一级
MIGRATE_RATE = 0.5          # 老账号：过去的经验换成金币的比例

CATS = {"build": "建筑", "nature": "自然", "road": "道路", "decor": "装饰"}
LIB_DIR = pathlib.Path(__file__).resolve().parent.parent / "public" / "js" / "buildings"
CONFIG = DATA / "town_config.json"
HEADER = re.compile(r"/\*\s*@building\s+(\{.*?\})\s*\*/", re.S)
_cache: dict = {}
_cache_lock = threading.Lock()


_STAMP_TTL = 1.0      # 秒
_stamps: dict = {}


def _stamp(*paths) -> tuple:
    """这些文件现在的样子（名字 + 修改时间），用来判断素材库 / 后台配置变没变。
    一秒内问过就用上一次的结果：拼一次页面数据会问几十遍，每遍都要把素材库的三十多个文件挨个看一眼
    （老用户的小镇东西多，光这一项就占了每次操作一大半的时间）。文件改了最多晚一秒生效；后台保存时会立刻清掉。"""
    t = time.monotonic()
    hit = _stamps.get(paths)
    if hit and t - hit[0] < _STAMP_TTL:
        return hit[1]
    out = []
    for path in paths:
        try:
            if path.is_dir():
                out += sorted((f.name, f.stat().st_mtime_ns) for f in path.glob("*.js"))
            else:
                out.append((path.name, path.stat().st_mtime_ns))
        except OSError:
            out.append((str(path), 0))
    _stamps[paths] = (t, tuple(out))
    return tuple(out)


def library() -> dict[str, dict]:
    """素材库里的每样东西（按文件名排序）：id → 默认元数据。文件改了会自动重读。"""
    key = _stamp(LIB_DIR)
    with _cache_lock:
        if _cache.get("lib_key") == key:
            return _cache["lib"]
    lib = {}
    for f in sorted(LIB_DIR.glob("*.js")):
        if f.name == "all.js":
            continue
        m = HEADER.search(f.read_text(encoding="utf-8")[:2000])
        if not m:
            continue
        try:
            meta = json.loads(m.group(1))
        except ValueError:
            continue
        w, d = (meta.get("size") or [1, 1])[:2]
        lib[f.stem] = {"id": f.stem, "name": str(meta.get("name") or f.stem), "cat": meta.get("cat") if meta.get("cat") in CATS else "decor",
                       "size": [max(1, int(w)), max(1, int(d))], "price": max(0, int(meta.get("price") or 0)),
                       "lv": max(1, int(meta.get("lv") or 1)), "height": int(meta.get("height") or 0),
                       "desc": str(meta.get("desc") or ""), "layer": meta.get("layer") or "", "gift": bool(meta.get("gift")),
                       "enabled": bool(meta.get("enabled", True))}
    with _cache_lock:
        _cache.update(lib_key=key, lib=lib)
    return lib


def overrides() -> dict:
    key = _stamp(CONFIG)
    with _cache_lock:
        if _cache.get("cfg_key") == key:
            return _cache["cfg"]
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    with _cache_lock:
        _cache.update(cfg_key=key, cfg=cfg)
    return cfg


def kinds() -> dict[str, dict]:
    """素材库 + 后台改过的值 = 现在生效的样子（包括礼物和没上架的，已经摆在地上的东西要靠它画）。"""
    ov = overrides().get("items") or {}
    out = {}
    for k, m in library().items():
        o = ov.get(k) or {}
        out[k] = {**m, **{f: o[f] for f in ("price", "lv", "enabled", "name", "desc") if f in o}}
        out[k]["sell"] = out[k]["enabled"] and not m["gift"]
    return out


def catalog() -> list[dict]:
    """商店里卖的（上架了的、不是礼物的），按类别、等级、价格排。"""
    order = list(CATS)
    return sorted((m for m in kinds().values() if m["sell"]), key=lambda m: (order.index(m["cat"]), m["lv"], m["price"]))


def meta(kind: str) -> dict:
    return kinds().get(kind) or {"id": kind, "name": kind, "cat": "decor", "size": [1, 1], "price": 0, "lv": 1,
                                  "height": 30, "desc": "", "layer": "", "gift": False, "enabled": False, "sell": False}


def dims(kind: str, rot: int = 0) -> tuple[int, int]:
    w, d = meta(kind)["size"]
    return (d, w) if rot else (w, d)


def bundle_js() -> bytes:
    """把素材库拼成一个 ES 模块：每个文件的 export default 变成 B[id]，一次请求拿到全部画法。"""
    key = _stamp(LIB_DIR)
    with _cache_lock:
        if _cache.get("js_key") == key:
            return _cache["js"]
    parts = ["// 由服务器把 public/js/buildings/*.js 拼成一个文件（core/town.py 的 bundle_js）", "const B = {};"]
    for f in sorted(LIB_DIR.glob("*.js")):
        if f.name == "all.js":
            continue
        code = re.sub(r"^export default ", "return ", f.read_text(encoding="utf-8"), count=1, flags=re.M)
        parts.append(f"B[{json.dumps(f.stem)}] = (function () {{\n{code}\n}})();")
    parts.append("export default B;")
    data = "\n".join(parts).encode("utf-8")
    with _cache_lock:
        _cache.update(js_key=key, js=data)
    return data


# (从第几级起, 土地边长)
LAND = ((1, 5), (3, 6), (6, 7), (10, 8), (15, 9), (20, 10), (26, 11), (32, 12))

# 新开的小镇（5×5 的地）：一间小木屋，门口一条小路通到地边，路口立着路牌，路两边各一盏路灯。都算小镇送的。
# 小木屋的门朝 +y（屏幕左下），所以路从 (2,2) 往 +y 铺到地边。
STARTER = (("cottage", 2, 1), ("road", 2, 2), ("road", 2, 3), ("road", 2, 4),
           ("sign", 1, 4), ("lamp", 1, 2), ("lamp", 3, 3))
# 以前开镇只放的那三样（路牌和一小段路），一直没动过的账号升级成上面的样子
OLD_STARTER = {("sign", 0, 0), ("road", 2, 4), ("road", 2, 3)}

# 小光关于下架功能的记忆：开镇时收起来（不是删除，「小光记得的」里也就看不到了）
RETIRED = re.compile(r"小芽|宠物|徽章|勋章|焰尾狐|花角鹿|澜灵|星灵|涟芽|进化图|分化成")


def size_for(lv: int) -> int:
    return max(n for at, n in LAND if lv >= at)


def name_of(kind: str) -> str:
    return meta(kind)["name"]


def level_gain(a: int, b: int) -> dict:
    """从 a 级升到 b 级多了什么：新的建筑 / 装饰、更大的地。"""
    items = [{"id": c["id"], "name": c["name"], "cat": c["cat"]} for c in catalog() if a < c["lv"] <= b]
    land = (size_for(a), size_for(b)) if size_for(b) > size_for(a) else None
    return {"from": a, "to": b, "unlocks": items, "land": list(land) if land else None}


def next_unlock(lv: int) -> dict | None:
    for L in range(lv + 1, max([c["lv"] for c in catalog()] + [at for at, _ in LAND]) + 1):
        g = level_gain(L - 1, L)
        if g["unlocks"] or g["land"]:
            return {"lv": L, "xp": growth.xp_for_level(L), "items": [i["name"] for i in g["unlocks"]],
                    "land": g["land"][1] if g["land"] else None}
    return None


def unlock_table() -> list[dict]:
    rows = []
    cat = catalog()
    for L in sorted({c["lv"] for c in cat} | {at for at, _ in LAND}):
        rows.append({"lv": L, "xp": growth.xp_for_level(L), "items": [c["name"] for c in cat if c["lv"] == L],
                     "land": next((n for at, n in LAND if at == L), None)})
    return rows


def unlock_text() -> str:
    lines = []
    cat = catalog()
    for L in sorted({c["lv"] for c in cat} | {at for at, _ in LAND}):
        g = level_gain(L - 1, L) if L > 1 else {"unlocks": [c for c in cat if c["lv"] == 1], "land": [0, size_for(1)]}
        bits = [i["name"] for i in g["unlocks"]]
        if g["land"]:
            bits.append(f"土地 {g['land'][1]}×{g['land'][1]}")
        lines.append(f"Lv{L} " + "、".join(bits))
    return "解锁节奏：" + "；".join(lines) + "。"


# ---------------------------------------------------------------- 开镇 / 老账号迁移 ----

def ensure(st) -> None:
    """每个账号第一次用到小镇时做一次：老账号把过去的经验换成金币、按旧算法到过的等级记成保底，
    收起小光关于宠物和徽章的记忆，放下新手小镇（STARTER）。之后每次调用只读一个画像字段。"""
    if int(st.profile().get("town_v") or 0) >= TOWN_V:
        return
    with st.tx():
        p = st.profile()
        v = int(p.get("town_v") or 0)
        if v >= TOWN_V:
            return
        total = growth.total_xp(st)
        floor = max(total // OLD_LEVEL_XP + 1 if total else 1, int(p.get("level_floor") or 1))
        lv = growth.level_of(total, floor)["lv"]
        patch = {"town_v": TOWN_V, "level_floor": floor, "town_seen_level": max(lv, int(p.get("town_seen_level") or 0))}
        if v < 1:
            gift = round(total * MIGRATE_RATE)
            if gift:
                growth._coin(st, "migrate", gift, "migrate:v1", f"过去的 {total} 经验换成了建材")
            if not st.c.execute("SELECT 1 FROM town_item LIMIT 1").fetchone():
                _starter(st)
            _retire_memories(st, p)
            patch["town_welcome"] = {"kind": "migrated" if total else "new", "xp": total, "coins": gift, "lv": lv}
        elif v < 3:
            _upgrade_starter(st)
        st.set_profile(patch)


def _starter(st) -> None:
    for kind, x, y in STARTER:
        _insert(st, kind, x, y, source="gift")


def _upgrade_starter(st) -> None:
    """老的新手小镇（只有路牌和两格路）原样没动过：换成新手小镇。摆过、挪过、买过东西的不碰。"""
    rows = st.c.execute("SELECT kind, x, y, placed, source FROM town_item").fetchall()
    if {(r["kind"], r["x"], r["y"]) for r in rows} == OLD_STARTER and len(rows) == len(OLD_STARTER)             and all(r["placed"] and r["source"] == "gift" for r in rows):
        st.c.execute("DELETE FROM town_item")
        _starter(st)


def _retire_memories(st, p: dict) -> None:
    for r in st.c.execute("SELECT id, text FROM memory WHERE status IN ('active','guess')").fetchall():
        if RETIRED.search(r["text"] or ""):
            st.c.execute("UPDATE memory SET status='archived', updated_at=? WHERE id=?", (iso(), r["id"]))
    nb = p.get("notebook") or {}
    if nb.get("text") and RETIRED.search(nb["text"]):
        kept = "\n".join(line for line in nb["text"].split("\n") if not RETIRED.search(line))
        st.set_profile({"notebook": {**nb, "text": kept}})
    you = ((p.get("cheer") or {}).get("text")) or ""
    if RETIRED.search(you):
        st.set_profile({"cheer": {}})


def seed_demo(st) -> None:
    """示例账号：按真实账号的规则把经验换成金币，再摆几样东西，让第一次来的人看到一个有人住的小镇。"""
    with st.tx():
        total = growth.total_xp(st)
        if total and not st.c.execute("SELECT 1 FROM coin WHERE ref='migrate:v1'").fetchone():
            growth._coin(st, "migrate", round(total * MIGRATE_RATE), "migrate:v1", f"过去的 {total} 经验换成了建材")
        for kind, x, y in (("tree", 3, 1), ("flowers", 1, 3), ("bush", 0, 2), ("tree", 4, 4)):   # 新手小镇上再添几样
            if not _taken(st) & _cells(x, y, 1, 1):
                _insert(st, kind, x, y, source="demo", story=_story(st))
        st.set_profile({"town_seen_level": growth.level(st)["lv"], "town_welcome": ""})


# ---------------------------------------------------------------- 读 ----

def _row(r) -> dict:
    d = dict(r)
    d["name"] = name_of(d["kind"])
    d["story"] = loads(d.get("story") or "", {}) if d.get("story") else {}
    return d


def items(st, placed: bool = True) -> list[dict]:
    return [_row(r) for r in st.c.execute(
        "SELECT * FROM town_item WHERE placed=? ORDER BY created_at, rowid", (1 if placed else 0,))]


def state(st) -> dict:
    ensure(st)
    p = st.profile()
    lv = growth.level(st)["lv"]
    placed = items(st)
    ks = kinds()
    have = {i["kind"] for i in placed} | {i["kind"] for i in items(st, placed=False)}
    return {
        "name": p.get("town_name") or "我的小镇",
        "size": size_for(lv),
        "level": lv,
        "coins": growth.coins(st),
        "items": placed,
        "warehouse": items(st, placed=False),
        "catalog": [{**c, "unlocked": lv >= c["lv"]} for c in catalog()],
        # 画地上的东西要用的：商店里卖的 + 这个人手里有的（礼物、后来下架了的）
        "kinds": {k: {f: m[f] for f in ("name", "cat", "size", "height", "layer")} for k, m in ks.items() if m["sell"] or k in have or m["gift"]},
        "cats": CATS,
        "next": next_unlock(lv),
        "built": sum(1 for i in placed if ks.get(i["kind"], {}).get("cat") == "build"),
        "welcome": p.get("town_welcome") or None,   # 第一次进小镇时的欢迎，看过就清掉
    }


def summary(st) -> str:
    """给小光的一句话：小镇现在什么样。"""
    s = state(st)
    builds = [i for i in s["items"] if i["source"] != "gift" and i["kind"] != "road"]
    last = builds[-1] if builds else None
    line = (f"TA 的小镇「{s['name']}」：Lv{s['level']}，{s['size']}×{s['size']} 的地，摆了 {len(builds)} 样东西"
            + (f"（最近建的是{last['name']}，{last['created_at'][5:10]}）" if last else "，还没建东西")
            + f"，现在有 {s['coins']} 金币")
    if s["warehouse"]:
        line += f"，仓库里放着 {len(s['warehouse'])} 样"
    if s["next"]:
        line += f"；Lv{s['next']['lv']} 会解锁" + "、".join(s["next"]["items"] + ([f"{s['next']['land']}×{s['next']['land']} 的地"] if s["next"]["land"] else []))
    return line + "。"


# ---------------------------------------------------------------- 写 ----

def _cells(x: int, y: int, w: int, d: int) -> set:
    return {(x + i, y + j) for i in range(w) for j in range(d)}


def _taken(st, skip: str = "") -> set:
    """地上已经被占的格子（大建筑占好几格）。"""
    out = set()
    for r in st.c.execute("SELECT id, kind, x, y, rot FROM town_item WHERE placed=1 AND id!=?", (skip,)):
        out |= _cells(r["x"], r["y"], *dims(r["kind"], r["rot"] or 0))
    return out


def _cell(st, kind: str, x, y, rot: int = 0, skip: str = "") -> tuple[int, int]:
    try:
        x, y = int(x), int(y)
    except (TypeError, ValueError):
        raise ValueError("位置不对")
    w, d = dims(kind, rot)
    n = size_for(growth.level(st)["lv"])
    if not (0 <= x and 0 <= y and x + w <= n and y + d <= n):
        raise ValueError("这块地放不下" if 0 <= x < n and 0 <= y < n else "这块地还没开出来")
    if _cells(x, y, w, d) & _taken(st, skip):
        raise ValueError("这里已经有东西了")
    return x, y


def _insert(st, kind: str, x: int | None, y: int | None, source: str = "shop", price: int = 0, note: str = "",
            story: dict | None = None, ref: str = "", rot: int = 0) -> dict:
    iid = new_id("t")
    placed = x is not None
    st.c.execute("INSERT INTO town_item(id, kind, x, y, placed, note, story, source, price, ref, created_at, placed_at, rot) "
                 "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (iid, kind, x if placed else -1, y if placed else -1, 1 if placed else 0, note,
                  dumps(story) if story else "", source, price, ref, iso(), iso() if placed else "", 1 if rot else 0))
    return _row(st.c.execute("SELECT * FROM town_item WHERE id=?", (iid,)).fetchone())


def _story(st) -> dict:
    """建它的时候，最近一次做成的事。"""
    r = st.c.execute("SELECT note, created_at FROM xp WHERE note!='' AND source NOT IN ('checkin','daily') "
                     "ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
    if not r:
        return {}
    n = re.sub(r"（今日这类剩 \d+）", "", r["note"])
    for pre, fmt in (("完成练习：", "做完了练习「{}」"), ("完成：", "完成了「{}」"), ("打卡：", "给「{}」打了卡"), ("到达：", "到达了里程碑「{}」")):
        if n.startswith(pre):
            n = fmt.format(n[len(pre):])
            break
    else:
        n = {"小确幸": "记下了一件小确幸", "好消息": "记下了一件小确幸", "内心戏": "记下了一段内心戏",
             "留下一个瞬间": "在愿望的轨迹上留下了一个瞬间"}.get(n, n)
    return {"text": n, "day": r["created_at"][:10]}


NONCE = re.compile(r"^[A-Za-z0-9_-]{6,40}$")


def _rot(kind: str, rot) -> int:
    """转个方向：长条的宽和深对调；正方形的占地不变，画的时候左右翻过来（门换一边朝）。路没有方向。"""
    return 1 if rot and meta(kind).get("layer") != "road" else 0


def buy(st, kind: str, x, y, nonce: str = "", rot=0) -> dict:
    item = kinds().get(str(kind or ""))
    if not item or not item["sell"]:
        raise ValueError("商店里没有这个")
    rot = _rot(item["id"], rot)
    nonce = nonce if NONCE.match(str(nonce or "")) else new_id("n")
    ref = "buy:" + nonce
    with st.tx():
        again = st.c.execute("SELECT * FROM town_item WHERE ref=?", (ref,)).fetchone()
        if again:   # 同一次点击的重发：不再扣钱，把上次建好的那栋还回去
            return {**_row(again), "again": True}
        lv = growth.level(st)["lv"]
        if lv < item["lv"]:
            raise ValueError(f"{item['name']}要 Lv{item['lv']} 才能建")
        x, y = _cell(st, item["id"], x, y, rot)
        growth.spend(st, item["price"], ref, f"建造：{item['name']}")
        out = _insert(st, item["id"], x, y, price=item["price"], story=_story(st), ref=ref, rot=rot)
    if item["cat"] == "build":
        st.log("town", f"在小镇建了一座{item['name']}")
    return out


def _get(st, iid: str) -> dict:
    r = st.c.execute("SELECT * FROM town_item WHERE id=?", (str(iid or ""),)).fetchone()
    if not r:
        raise ValueError("没有这样东西")
    return dict(r)


def move(st, iid: str, x, y, rot=None) -> dict:
    with st.tx():
        it = _get(st, iid)
        rot = _rot(it["kind"], it["rot"] if rot is None else rot)
        x, y = _cell(st, it["kind"], x, y, rot, skip=it["id"])
        st.c.execute("UPDATE town_item SET x=?, y=?, rot=?, placed=1, placed_at=? WHERE id=?", (x, y, rot, iso(), it["id"]))
    return _row(st.c.execute("SELECT * FROM town_item WHERE id=?", (it["id"],)).fetchone())


def store_item(st, iid: str) -> dict:
    with st.tx():
        it = _get(st, iid)
        st.c.execute("UPDATE town_item SET placed=0, x=-1, y=-1 WHERE id=?", (it["id"],))
    return _row(st.c.execute("SELECT * FROM town_item WHERE id=?", (it["id"],)).fetchone())


def rename(st, name: str) -> str:
    name = clip(re.sub(r"\s+", "", str(name or "")), 10)
    st.set_profile({"town_name": name})
    st.log("town", f"小镇改名叫「{name or '我的小镇'}」")
    return name


def welcome_seen(st) -> None:
    st.set_profile({"town_welcome": ""})


def gift_monument(st, ref: str, title: str) -> dict | None:
    """到达里程碑：送一块刻着它名字的纪念碑（在 award 的事务里调用；同一个里程碑只送一次）。"""
    gref = "gift:" + ref
    if st.c.execute("SELECT 1 FROM town_item WHERE ref=?", (gref,)).fetchone():
        return None
    it = _insert(st, "monument", None, None, source="gift", note=clip(title, 30),
                 story={"text": f"到达了里程碑「{clip(title, 30)}」", "day": now().date().isoformat()}, ref=gref)
    st.log("town", f"到达「{clip(title, 30)}」，小镇送来一块纪念碑")
    return {"id": it["id"], "name": it["name"], "note": it["note"]}


# ---------------------------------------------------------------- 后台：全局调价格和解锁等级 ----

ADMIN_FIELDS = {"price": (0, 100000), "lv": (1, 200)}


def admin_catalog() -> dict:
    """后台的「小镇」页：素材库里每一样的默认值、后台改过的值、现在生效的值。"""
    ov = overrides()
    items = ov.get("items") or {}
    rows = []
    for k, m in library().items():
        eff = kinds()[k]
        rows.append({"id": k, "default": {f: m[f] for f in ("name", "price", "lv", "enabled", "desc")}, "override": items.get(k) or {},
                     "name": eff["name"], "desc": eff["desc"], "price": eff["price"], "lv": eff["lv"], "enabled": eff["enabled"],
                     "cat": m["cat"], "size": m["size"], "height": m["height"], "layer": m["layer"], "gift": m["gift"],
                     "fresh": not m["enabled"] and k not in items})      # 新放进素材库、还没在后台定过的
    order = list(CATS)
    rows.sort(key=lambda r: (r["gift"], order.index(r["cat"]), r["lv"], r["price"]))
    return {"items": rows, "land": [{"lv": a, "size": n} for a, n in LAND], "cats": CATS,
            "updated_at": ov.get("updated_at", ""), "levels": [{"lv": lv, "xp": growth.xp_for_level(lv)} for lv in (5, 10, 15, 20, 25, 30, 35, 40)]}


def admin_save(patch: dict) -> dict:
    """patch = {id: {price, lv, enabled, name, desc} | None}；None 表示恢复默认。只改出现的那几样。"""
    lib = library()
    cfg = dict(overrides())
    items = dict(cfg.get("items") or {})
    for k, v in (patch or {}).items():
        if k not in lib:
            raise ValueError(f"素材库里没有 {k}")
        if v is None:
            items.pop(k, None)
            continue
        o = dict(items.get(k) or {})
        for f, (lo, hi) in ADMIN_FIELDS.items():
            if f in v:
                try:
                    n = int(v[f])
                except (TypeError, ValueError):
                    raise ValueError(f"{lib[k]['name']}的{'价格' if f == 'price' else '解锁等级'}要是整数")
                if not lo <= n <= hi:
                    raise ValueError(f"{lib[k]['name']}的{'价格' if f == 'price' else '解锁等级'}要在 {lo}～{hi} 之间")
                o[f] = n
        if "enabled" in v:
            o["enabled"] = bool(v["enabled"])
        for f, n in (("name", 10), ("desc", 40)):
            if f in v:
                t = clip(str(v[f] or "").strip(), n)
                if t:
                    o[f] = t
                else:
                    o.pop(f, None)
        # 和默认值一样的就不存
        o = {f: x for f, x in o.items() if x != lib[k].get(f)}
        if o:
            items[k] = o
        else:
            items.pop(k, None)
    cfg.update(items=items, updated_at=iso())
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, CONFIG)
    _stamps.clear()      # 改完立刻生效，不等那一秒
    return admin_catalog()

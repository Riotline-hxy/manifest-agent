"""我的小镇：每个人一块会慢慢长大的地，现实里做成的每件小事都在这里盖起来。

  - 等级（growth.level）决定土地多大、能建什么；金币（growth 的账本）决定买不买得起。
  - 买 = 扣金币 + 放到地上，在一个事务里做完；同一个请求号只扣一次（连点、网络重发都安全）。
  - 建筑不会坏、不会消失、不会因为中断被收走。可以挪位置、收进仓库、再放出来，都不花钱。
  - 每栋建筑记下它是哪天建的、那之前你做成了什么，小镇慢慢就是你的成长故事。
  - 到达里程碑会送一块刻着名字的纪念碑，放在仓库里，想放哪儿放哪儿。
  - 老账号第一次进来（ensure）：过去累计的经验按一半换成金币；按旧算法到过的等级记成保底，不会掉级；
    小光关于宠物 / 徽章的记忆收起来。
格子坐标 (x, y) 从 0 开始，土地变大时只往外长，已经放好的东西不用挪。
"""
from __future__ import annotations

import re

from . import growth
from .util import clip, dumps, iso, loads, new_id, now

TOWN_V = 2                  # 1：开镇；2：等级换成递增曲线，老账号记下保底等级
OLD_LEVEL_XP = 40           # 3.0 之前：每 40 经验一级
MIGRATE_RATE = 0.5          # 老账号：过去的经验换成金币的比例

CATS = {"build": "建筑", "nature": "自然", "road": "道路", "decor": "装饰"}

# 解锁节奏：前两周差不多每两三天有新东西，之后一周左右一样（数值说明见 docs/成长数值设计.md）
CATALOG = [
    {"id": "cottage", "name": "小木屋", "cat": "build", "price": 40, "lv": 1, "desc": "小镇的第一盏灯，从这里亮起来"},
    {"id": "house", "name": "蓝顶小屋", "cat": "build", "price": 80, "lv": 3, "desc": "窗台上摆着一盆花"},
    {"id": "bakery", "name": "面包房", "cat": "build", "price": 120, "lv": 4, "desc": "每天早上都有刚出炉的香味"},
    {"id": "cafe", "name": "街角咖啡", "cat": "build", "price": 140, "lv": 6, "desc": "适合坐一个下午"},
    {"id": "library", "name": "小图书馆", "cat": "build", "price": 200, "lv": 9, "desc": "装着你读过的每一页"},
    {"id": "greenhouse", "name": "玻璃花房", "cat": "build", "price": 240, "lv": 10, "desc": "冬天也有花开"},
    {"id": "windmill", "name": "风车", "cat": "build", "price": 300, "lv": 12, "desc": "风一吹，就慢慢转起来"},
    {"id": "tower", "name": "观星塔", "cat": "build", "price": 380, "lv": 15, "desc": "离星星近一点"},
    {"id": "clocktower", "name": "钟楼", "cat": "build", "price": 450, "lv": 18, "desc": "替你记着走过的每一天"},
    {"id": "bush", "name": "圆灌木", "cat": "nature", "price": 6, "lv": 1, "desc": "圆滚滚的一团绿"},
    {"id": "flowers", "name": "小花丛", "cat": "nature", "price": 8, "lv": 1, "desc": "几朵不挑地方的小花"},
    {"id": "tree", "name": "圆冠树", "cat": "nature", "price": 12, "lv": 1, "desc": "夏天能在下面乘凉"},
    {"id": "pine", "name": "松树", "cat": "nature", "price": 14, "lv": 2, "desc": "一年四季都绿着"},
    {"id": "pond", "name": "小池塘", "cat": "nature", "price": 50, "lv": 5, "desc": "水面上漂着一片荷叶"},
    {"id": "sakura", "name": "樱花树", "cat": "nature", "price": 30, "lv": 7, "desc": "花瓣会慢慢落下来"},
    {"id": "road", "name": "石板路", "cat": "road", "price": 3, "lv": 1, "desc": "挨着放会自己连起来"},
    {"id": "lamp", "name": "路灯", "cat": "decor", "price": 15, "lv": 2, "desc": "天黑了会亮"},
    {"id": "bench", "name": "长椅", "cat": "decor", "price": 18, "lv": 3, "desc": "走累了坐一会儿"},
    {"id": "mailbox", "name": "邮筒", "cat": "decor", "price": 20, "lv": 4, "desc": "寄给未来的自己"},
    {"id": "arch", "name": "花拱门", "cat": "decor", "price": 45, "lv": 7, "desc": "从下面走过去，像进了另一段路"},
    {"id": "fountain", "name": "喷泉", "cat": "decor", "price": 150, "lv": 8, "desc": "小镇广场的中心"},
    {"id": "balloon", "name": "热气球", "cat": "decor", "price": 320, "lv": 14, "desc": "在小镇上空慢慢飘"},
]
GIFTS = {
    "sign": {"name": "小镇路牌", "cat": "decor", "desc": "写着小镇的名字"},
    "monument": {"name": "纪念碑", "cat": "decor", "desc": "到达里程碑那天，小镇送给你的"},
}
BY_ID = {c["id"]: c for c in CATALOG}

# (从第几级起, 土地边长)
LAND = ((1, 5), (3, 6), (6, 7), (10, 8), (15, 9), (20, 10))

# 小光关于下架功能的记忆：开镇时收起来（不是删除，「小光记得的」里也就看不到了）
RETIRED = re.compile(r"小芽|宠物|徽章|勋章|焰尾狐|花角鹿|澜灵|星灵|涟芽|进化图|分化成")


def size_for(lv: int) -> int:
    return max(n for at, n in LAND if lv >= at)


def name_of(kind: str) -> str:
    return (BY_ID.get(kind) or GIFTS.get(kind) or {}).get("name", kind)


def level_gain(a: int, b: int) -> dict:
    """从 a 级升到 b 级多了什么：新的建筑 / 装饰、更大的地。"""
    items = [{"id": c["id"], "name": c["name"], "cat": c["cat"]} for c in CATALOG if a < c["lv"] <= b]
    land = (size_for(a), size_for(b)) if size_for(b) > size_for(a) else None
    return {"from": a, "to": b, "unlocks": items, "land": list(land) if land else None}


def next_unlock(lv: int) -> dict | None:
    for L in range(lv + 1, 40):
        g = level_gain(L - 1, L)
        if g["unlocks"] or g["land"]:
            return {"lv": L, "xp": growth.xp_for_level(L), "items": [i["name"] for i in g["unlocks"]],
                    "land": g["land"][1] if g["land"] else None}
    return None


def unlock_table() -> list[dict]:
    rows = []
    for L in sorted({c["lv"] for c in CATALOG} | {at for at, _ in LAND}):
        rows.append({"lv": L, "xp": growth.xp_for_level(L), "items": [c["name"] for c in CATALOG if c["lv"] == L],
                     "land": next((n for at, n in LAND if at == L), None)})
    return rows


def unlock_text() -> str:
    lines = []
    for L in sorted({c["lv"] for c in CATALOG} | {at for at, _ in LAND}):
        g = level_gain(L - 1, L) if L > 1 else {"unlocks": [c for c in CATALOG if c["lv"] == 1], "land": [0, size_for(1)]}
        bits = [i["name"] for i in g["unlocks"]]
        if g["land"]:
            bits.append(f"土地 {g['land'][1]}×{g['land'][1]}")
        lines.append(f"Lv{L} " + "、".join(bits))
    return "解锁节奏：" + "；".join(lines) + "。"


# ---------------------------------------------------------------- 开镇 / 老账号迁移 ----

def ensure(st) -> None:
    """每个账号第一次用到小镇时做一次：老账号把过去的经验换成金币、按旧算法到过的等级记成保底，
    收起小光关于宠物和徽章的记忆，放下路牌和一小段路。之后每次调用只读一个画像字段。"""
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
                for kind, x, y in (("sign", 0, 0), ("road", 2, 4), ("road", 2, 3)):
                    _insert(st, kind, x, y, source="gift")
            _retire_memories(st, p)
            patch["town_welcome"] = {"kind": "migrated" if total else "new", "xp": total, "coins": gift, "lv": lv}
        st.set_profile(patch)


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
        for kind, x, y in (("cottage", 1, 1), ("tree", 3, 1), ("flowers", 1, 3), ("bush", 0, 3), ("road", 2, 2), ("road", 2, 1)):
            if not _occupied(st, x, y):
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
    return {
        "name": p.get("town_name") or "我的小镇",
        "size": size_for(lv),
        "level": lv,
        "coins": growth.coins(st),
        "items": placed,
        "warehouse": items(st, placed=False),
        "catalog": [{**c, "unlocked": lv >= c["lv"]} for c in CATALOG],
        "cats": CATS,
        "next": next_unlock(lv),
        "built": sum(1 for i in placed if (BY_ID.get(i["kind"]) or {}).get("cat") == "build"),
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

def _occupied(st, x: int, y: int, skip: str = "") -> bool:
    return bool(st.c.execute("SELECT 1 FROM town_item WHERE placed=1 AND x=? AND y=? AND id!=?", (x, y, skip)).fetchone())


def _cell(st, x, y, skip: str = "") -> tuple[int, int]:
    try:
        x, y = int(x), int(y)
    except (TypeError, ValueError):
        raise ValueError("位置不对")
    n = size_for(growth.level(st)["lv"])
    if not (0 <= x < n and 0 <= y < n):
        raise ValueError("这块地还没开出来")
    if _occupied(st, x, y, skip):
        raise ValueError("这里已经有东西了")
    return x, y


def _insert(st, kind: str, x: int | None, y: int | None, source: str = "shop", price: int = 0, note: str = "",
            story: dict | None = None, ref: str = "") -> dict:
    iid = new_id("t")
    placed = x is not None
    st.c.execute("INSERT INTO town_item(id, kind, x, y, placed, note, story, source, price, ref, created_at, placed_at) "
                 "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                 (iid, kind, x if placed else -1, y if placed else -1, 1 if placed else 0, note,
                  dumps(story) if story else "", source, price, ref, iso(), iso() if placed else ""))
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


def buy(st, kind: str, x, y, nonce: str = "") -> dict:
    item = BY_ID.get(str(kind or ""))
    if not item:
        raise ValueError("商店里没有这个")
    nonce = nonce if NONCE.match(str(nonce or "")) else new_id("n")
    ref = "buy:" + nonce
    with st.tx():
        again = st.c.execute("SELECT * FROM town_item WHERE ref=?", (ref,)).fetchone()
        if again:   # 同一次点击的重发：不再扣钱，把上次建好的那栋还回去
            return {**_row(again), "again": True}
        lv = growth.level(st)["lv"]
        if lv < item["lv"]:
            raise ValueError(f"{item['name']}要 Lv{item['lv']} 才能建")
        x, y = _cell(st, x, y)
        growth.spend(st, item["price"], ref, f"建造：{item['name']}")
        out = _insert(st, item["id"], x, y, price=item["price"], story=_story(st), ref=ref)
    if item["cat"] == "build":
        st.log("town", f"在小镇建了一座{item['name']}")
    return out


def _get(st, iid: str) -> dict:
    r = st.c.execute("SELECT * FROM town_item WHERE id=?", (str(iid or ""),)).fetchone()
    if not r:
        raise ValueError("没有这样东西")
    return dict(r)


def move(st, iid: str, x, y) -> dict:
    with st.tx():
        it = _get(st, iid)
        x, y = _cell(st, x, y, skip=it["id"])
        st.c.execute("UPDATE town_item SET x=?, y=?, placed=1, placed_at=? WHERE id=?", (x, y, iso(), it["id"]))
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

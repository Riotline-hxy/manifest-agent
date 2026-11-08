"""「显化你的愿望」「调整现有计划」演示用：用真模型（.env 里的模型，不思考）把演示里每条路的小光回复先跑出来，写进 data.js。
用法（在 manifest-agent 目录）：python docs/显化与调整/gen.py
提示词就在这个文件里；接进 App 时照搬到 core/ 里。演示人物：阿青，温柔的小光。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
os.environ["MANIFEST_DATA"] = tempfile.mkdtemp(prefix="demo_gen_")
sys.path.insert(0, str(ROOT / "demo"))
sys.stdout.reconfigure(encoding="utf-8")
from core.util import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from core import llm  # noqa: E402

TONE = "你说话温柔、慢一点。"
RULES = ("用平常话，不说「宇宙」「振动频率」「吸引力法则」「能量」这类玄的词；不说教，不喊口号，不用「不是……而是……」、破折号，"
         "不说「加油」「你一定可以」「值得被」「勇敢」「旅程」「蜕变」；不复述 TA 刚说的原话。")
WHO = "你是「小光」，TA 的朋友，陪 TA 用显化的方法一点点靠近想要的生活。" + TONE

# ---------------------------------------------------------------- 显化你的愿望：每一步一段提示词 ----
P = {
    "spec": WHO + """
显化第一步是「清晰你的愿景」：越具体越有力量。TA 刚说了一个还比较笼统的愿望。
1. say：接住 TA，一句，不超过 24 字。
2. opts：两个更具体的版本，每个不超过 22 字，补上 TA 可能在意的细节（数量、时间、地点、样子），两个侧重不同，都用 TA 的口吻。
""" + RULES + """
只输出 JSON：{"say":"","opts":["",""]}""",
    "vision": WHO + """
还是第一步「清晰你的愿景」。TA 闭上眼，想象这个愿望已经实现了，选了那一刻的感觉。
1. vision：那一刻的画面，一句现在时，用「我」开头，不超过 36 字，写出具体的场景和这种感觉，像日记里的一句。
2. say：你看到这个画面时的一句话，不超过 22 字，别复述画面。
""" + RULES + """
只输出 JSON：{"vision":"","say":""}""",
    "doubt": WHO + """
显化第二步是「消除恐惧与怀疑」：人会被「我不配」「我做不到」这种声音拖住。TA 刚说了心里冒出来的那个声音。
1. say：接住它，一句，不超过 30 字。说出这个声音很常见、它从哪来，不急着反驳。
2. opts：两句对着这个声音的肯定语，每句用「我」开头、不超过 16 字，可信、不夸张，像能每天对自己说的话，两句不一样。
TA 说没有这种声音时，say 夸一句 TA 的笃定，opts 给两句帮 TA 守住这份笃定的话。
""" + RULES + """
只输出 JSON：{"say":"","opts":["",""]}""",
    "act": WHO + """
显化第三步是「调整你的行为」：显化不是许愿，是行动；假装你已经是实现了它的人，做那个人今天会做的事。
opts：两件今天就能做的小事，每件不超过 16 字，具体到动作，比 TA 平时稍微走出舒适区一点点，但不吓人，两件不一样。
""" + RULES + """
只输出 JSON：{"opts":["",""]}""",
    "act_say": WHO + """
还是第三步「调整你的行为」。TA 挑了今天要做的一件小事。
say：一句，不超过 24 字，让 TA 觉得做这件事时，自己已经有点像实现了愿望的那个人。
""" + RULES + """
只输出 JSON：{"say":""}""",
    "test": WHO + """
显化第四步是「克服考验」：往前走的时候，总会出现让人想将就、想退回去的时刻。TA 刚说了最近遇到的。
1. say：接住 TA，一句，不超过 28 字。不评判、不表现失望，想将就是人之常情。
2. opts：两句「下次它出现时，我会……」，每句不超过 24 字（含「下次它出现时，我会」），给一个具体、做得到的应对，两句不一样。
TA 说没有时，say 说一句不用硬找，opts 给两句为以后准备的应对。
""" + RULES + """
只输出 JSON：{"say":"","opts":["",""]}""",
    "thanks": WHO + """
显化第五步是「无条件的感恩」：对未来有期待，对现在有感激；一个小技巧是把「我必须」换成「我有幸能」。TA 刚写了一句。
1. line：把它写成一句感恩，用「我有幸能」开头，不超过 22 字。TA 写的本来就是感激的事，就顺着写。
2. say：一句，不超过 22 字，说说这样换一下之后的感觉。
""" + RULES + """
只输出 JSON：{"line":"","say":""}""",
    "envy": WHO + """
显化第六步是「把嫉妒变成动力」：看到别人过上了自己想要的样子，心里发酸是正常的；这份酸其实在告诉你，你真正想要什么。TA 刚说了看到那个人时的感觉。
1. say：一句，不超过 40 字。先接住这份感觉，再点出它说明 TA 真正想要的是什么，最后落到「TA 能做到，你也可以」的意思（用你自己的话）。
2. learn：可以向那个人学的一件具体的事，不超过 16 字。
TA 说没有这样的人时，say 说一句也很好，learn 给一个可以去找找的榜样方向。
""" + RULES + """
只输出 JSON：{"say":"","learn":""}""",
    "trust": WHO + """
显化第七步是「信任」：显化不是控制；越急越不安，该做的做了，剩下的交给时间，它会在合适的时候来。TA 刚说了想到「它什么时候会来」时的心情。
1. say：接住这份心情，不超过 40 字。把「你今天能做的」（就是 TA 选的那件小事）和「可以交给时间的」分开说，让 TA 松一口气；不催，不保证结果。
2. opts：两句心急时可以对自己说的话，用「我」开头，不超过 16 字，平实、可信，两句不一样。
TA 说能慢慢等时，say 顺着这份从容说，opts 给两句帮 TA 一直这样从容的话。
""" + RULES + """
只输出 JSON：{"say":"","opts":["",""]}""",
    # 七步走完：小光写的一小段话，把 TA 这一路说的串起来；最后一句落在自爱
    "close": WHO + """
显化七步都走完了。下面是 TA 这一路说的、选的。
1. letter：你写给 TA 的一小段话，2～3 句，不超过 90 字。用上 TA 这一路的具体内容：心里那个声音、TA 挑的那句话、今天要做的那件小事，
   串成 TA 自己的一段路（心里怕什么，打算怎么对自己说，今天往哪走一步）。像朋友写的小纸条，有温度、有细节；不总结、不列清单、不喊口号。
2. love：最后一句，提醒 TA 好好爱自己，不超过 20 字，对 TA 说（用「你」），和 letter 不重复。
""" + RULES + """
只输出 JSON：{"letter":"","love":""}""",
}

# ---------------------------------------------------------------- 调整现有计划 ----
PLAN = """你是「小光」，TA 的朋友，帮 TA 把现有的计划调到贴着 TA 现在的状态走。""" + TONE + """
下面是 TA 刚说的现在的状态，和 TA 现在的整份计划。按 TA 的状态，给一份调整方案：
1. see：一句话说出你看到的现在的 TA，对 TA 说，不超过 34 字，把状态和计划连起来。
2. changes：0～5 条具体改动，每条 {"kind":"","target":"","to":"","why":""}：
   kind 只能是：habit_small 习惯改小（to 写新的做法，别写频率）/ habit_freq 习惯降频（to 写「每周 N 次」）/ habit_cue 习惯挂到每天某个时候（to 写那个时候）/
   habit_pause 习惯这周先停 / step_small 小步改成更小的第一下（to 写那一下）/ step_move 小步换个日子（to 写哪天）/
   ms_delay 里程碑推后（to 写推后几天，比如「推后 7 天」）/ step_add 加一个新小步（to 写这一步，只在 TA 状态好、计划做得顺时用）。
   target 写计划里那一项的原名（step_add 写愿望名）。why 不超过 18 字，说为什么这么改。
   每一项最多一条改动（想又改小又降频，就挑更要紧的那个）；习惯只能用 habit_ 开头的，小步只能用 step_ 开头的，里程碑只能用 ms_delay。
   只改需要改的：TA 累、忙、顾不上，就改小、降频、停一停，别加；顺的时候可以不改，或者加一小步。劲头只有一点点时，留下的每件事都要两分钟内做得完。
   计划没什么要改的，changes 给空，see 说一句「照现在的来就好」的意思。
不说教，不喊口号，不用「不是……而是……」、破折号，不说「加油」。
只输出 JSON：{"see":"","changes":[{"kind":"","target":"","to":"","why":""}]}"""

REVISE = PLAN + """
这是第二轮：TA 看了上一版方案，提了意见。只改 TA 提到的地方，别的保持不变；TA 不想改的项就从 changes 里拿掉。see 可以换一句接住 TA 的意见。"""

PERSONA_PLAN = """愿望「敢开口说英语」：
- 习惯「每天背 20 个单词」：每天，本周做到 2/7
- 习惯「跟读一段对话」：每周 3 次，本周做到 1/3
- 小步「约 Mia 周末练口语」：放了 6 天还没做
- 里程碑「能用英语做 3 分钟自我介绍」：还有 10 天
愿望「睡好一点」：
- 习惯「12 点前放下手机」：每天，本周做到 4/7"""

STATE = {"busy": "忙忙碌碌（事情一件接一件）", "steady": "按自己的节奏（和平时差不多）", "change": "正在变化（有些事不一样了）",
         "slow": "想慢下来（有点累了）"}
ENERGY = {"seed": "一点点就好（两分钟就够）", "sprout": "每天一小会（十分钟左右）", "more": "可以多一点（半小时左右）"}
FEEL = {"smooth": "挺顺的（照着做就行）", "stuck": "有点卡（有一件动不起来）", "full": "太满了（顾了这头顾不上那头）",
        "none": "顾不上（这周几乎没碰）"}
REVISIONS = ["背单词我不想减，别的可以", "别让我停跟读", "其实我还能再多做一点"]

# ---------------------------------------------------------------- 演示的愿望 ----
NEW_WISHES = ["换一份喜欢的工作", "每天睡个好觉", "敢在人前表达自己"]
OLD = {"title": "敢开口说英语", "vision": "我在小组讨论里自然地用英语说出自己的想法，大家都在认真听。"}
FEELS = {"light": "轻松", "proud": "骄傲", "calm": "平静", "steadyfeel": "踏实", "happy": "开心"}
DOUBTS = {"worth": "我不配", "able": "我能力不够", "late": "已经太晚了", "others": "怕别人怎么看", "none": "没有这种声音"}
TESTS = {"settle": "想将就一下", "old": "旧习惯又回来了", "cold": "有人泼冷水", "none": "最近没有"}
THANKS = ["我必须每天上课", "我必须早起", "家人一直在支持我"]
ENVY = {"sour": "有点酸", "admire": "很羡慕", "learn": "想向 TA 学", "none": "没有这样的人"}
TRUST = {"rush": "很急，想快点看到", "fear": "怕它一直不来", "calm": "能慢慢等"}

out = {"spec": {}, "vision": {}, "doubt": {}, "act": {}, "act_say": {}, "test": {}, "thanks": {}, "envy": {}, "trust": {}, "close": {},
       "plan": {}, "revise": {}}
lock = threading.Lock()


def ask(system, user, need):
    r = {}
    for _ in range(3):
        r = llm.complete_json([{"role": "system", "content": system}, {"role": "user", "content": user}], timeout=45, reasoning="none") or {}
        if all(r.get(k) for k in need):
            return r
    return r


def put(kind, key, val):
    with lock:
        out[kind][key] = val


def wish_ctx(w):
    """后面几步用的愿望：新愿望用第一步挑的第一个具体版本（演示里简化），旧愿望用标题和当初写的样子。"""
    if w == "old":
        return f"愿望：「{OLD['title']}」\n当初写下的样子：{OLD['vision']}"
    spec = (out["spec"].get(w) or {}).get("opts") or [NEW_WISHES[int(w)]]
    return f"愿望：「{spec[0]}」"


def run(job):
    kind, key = job[0], job[1]
    if kind == "spec":
        put(kind, key, ask(P["spec"], f"TA 的称呼：阿青\nTA 说想要：{NEW_WISHES[int(key)]}", ["say", "opts"]))
    elif kind == "vision":
        w, i, f = key.split("|")
        spec = out["spec"][w]["opts"][int(i)]
        put(kind, key, ask(P["vision"], f"TA 的称呼：阿青\n愿望：{spec}\n想象它实现时，那一刻的感觉：{FEELS[f]}", ["vision", "say"]))
    elif kind == "doubt":
        w, d = key.split("|")
        put(kind, key, ask(P["doubt"], f"{wish_ctx(w)}\n想到它，TA 心里冒出来的声音：{DOUBTS[d]}", ["say", "opts"]))
    elif kind == "act":
        put(kind, key, ask(P["act"], wish_ctx(key), ["opts"]))
    elif kind == "act_say":
        w, i = key.split("|")
        put(kind, key, ask(P["act_say"], f"{wish_ctx(w)}\nTA 今天要做的事：{out['act'][w]['opts'][int(i)]}", ["say"]))
    elif kind == "test":
        w, t = key.split("|")
        put(kind, key, ask(P["test"], f"{wish_ctx(w)}\n最近让 TA 想将就、想退回去的：{TESTS[t]}", ["say", "opts"]))
    elif kind == "thanks":
        w, i = key.split("|")
        put(kind, key, ask(P["thanks"], f"{wish_ctx(w)}\nTA 写的：{THANKS[int(i)]}", ["line", "say"]))
    elif kind == "envy":
        w, e = key.split("|")
        put(kind, key, ask(P["envy"], f"{wish_ctx(w)}\n看到已经过上 TA 想要的样子的那个人，TA 心里：{ENVY[e]}", ["say", "learn"]))
    elif kind == "trust":
        w, t = key.split("|")
        put(kind, key, ask(P["trust"], f"{wish_ctx(w)}\nTA 今天要做的小事：{out['act'][w]['opts'][0]}\n想到它什么时候会来，TA 心里：{TRUST[t]}", ["say", "opts"]))
    elif kind == "close":
        w, d, ai, ci, t = key.split("|")
        aff = out["doubt"][f"{w}|{d}"]["opts"][int(ai)]
        act = out["act"][w]["opts"][int(ci)]
        put(kind, key, ask(P["close"], f"TA 的称呼：阿青\n{wish_ctx(w)}\n心里那个声音：{DOUBTS[d]}\nTA 挑的那句话：{aff}\n"
                                       f"今天要做的小事：{act}\n想到它什么时候会来：{TRUST[t]}", ["letter", "love"]))
    elif kind == "plan":
        s, e, f = key.split("|")
        put(kind, key, ask(PLAN, f"TA 的称呼：阿青\n最近的状态：{STATE[s]}\n现在的劲头：{ENERGY[e]}\n这阵子的计划做起来：{FEEL[f]}\n\nTA 现在的计划：\n{PERSONA_PLAN}", ["see"]))
    elif kind == "revise":
        base, i = key.split("#")
        s, e, f = base.split("|")
        prev = json.dumps(out["plan"][base], ensure_ascii=False)
        put(kind, key, ask(REVISE, f"TA 的称呼：阿青\n最近的状态：{STATE[s]}\n现在的劲头：{ENERGY[e]}\n这阵子的计划做起来：{FEEL[f]}\n\n"
                                   f"TA 现在的计划：\n{PERSONA_PLAN}\n\n上一版方案：{prev}\nTA 的意见：{REVISIONS[int(i)]}", ["see"]))


def batch(jobs):
    with ThreadPoolExecutor(12) as ex:
        list(ex.map(run, jobs))


W = ["0", "1", "2", "old"]
batch([("spec", str(i)) for i in range(3)] + [("act", w) for w in ["old"]]
      + [("plan", f"{s}|{e}|{f}") for s in STATE for e in ENERGY for f in FEEL])
batch([("vision", f"{w}|{i}|{f}") for w in ["0", "1", "2"] for i in range(2) for f in FEELS]
      + [("act", w) for w in ["0", "1", "2"]]
      + [("doubt", f"{w}|{d}") for w in W for d in DOUBTS] + [("test", f"{w}|{t}") for w in W for t in TESTS]
      + [("thanks", f"{w}|{i}") for w in W for i in range(3)] + [("envy", f"{w}|{e}") for w in W for e in ENVY]

      + [("revise", f"busy|seed|full#{i}") for i in range(3)] + [("revise", f"steady|sprout|stuck#{i}") for i in range(3)])
batch([("act_say", f"{w}|{i}") for w in W for i in range(2)] + [("trust", f"{w}|{t}") for w in W for t in TRUST]
      + [("close", f"{w}|{d}|{a}|{c}|{t}") for w in W for d in DOUBTS for a in range(2) for c in range(2) for t in TRUST])

prompts = {k: v for k, v in P.items()}
prompts["plan"], prompts["revise"] = PLAN, REVISE
(HERE / "data.js").write_text(
    "// 用真模型（DeepSeek flash，不思考，温柔的小光）预先跑出来的演示数据，由 gen.py 生成。\n"
    f"window.PROMPTS = {json.dumps(prompts, ensure_ascii=False)};\n"
    f"window.D = {json.dumps(out, ensure_ascii=False)};\n"
    f"window.OPT = {json.dumps(dict(NEW_WISHES=NEW_WISHES, OLD=OLD, FEELS=FEELS, DOUBTS=DOUBTS, TESTS=TESTS, THANKS=THANKS, ENVY=ENVY, TRUST=TRUST, STATE=STATE, ENERGY=ENERGY, FEEL=FEEL, REVISIONS=REVISIONS, PERSONA_PLAN=PERSONA_PLAN), ensure_ascii=False)};\n",
    encoding="utf-8")
miss = {k: [kk for kk, vv in v.items() if not vv] for k, v in out.items()}
print({k: len(v) for k, v in out.items()}, "missing:", {k: v for k, v in miss.items() if v})

"""把 rigs.json 排成紧凑格式（坐标点写在一行），方便手工改。python -I gen/fmt_rigs.py"""
import json
import os
import re

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rigs.json")
data = json.load(open(p, encoding="utf8"))
text = json.dumps(data, ensure_ascii=False, indent=2)
# 数字列表 / 点列表收成一行
text = re.sub(r"\[\s+(-?[\d.]+),\s+(-?[\d.]+)\s+\]", r"[\1, \2]", text)
text = re.sub(r"\[\s+((?:\[-?[\d.]+, -?[\d.]+\],?\s*)+)\]", lambda m: "[" + re.sub(r"\s+", " ", m.group(1)).strip() + "]", text)
open(p, "w", encoding="utf8").write(text + "\n")

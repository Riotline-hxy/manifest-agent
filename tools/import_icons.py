"""Bring the final icon set (48 grid, codex-workspace/icon-lab/handoff/manifest-icons-final/svg) into ui.js ICONS (24 grid).
Every coordinate is halved, so the site's own stroke CSS (.ic-svg 1.8, .tile 2.1) keeps working. The 10 KEEP_ORIGINAL icons are untouched."""
import csv, re, sys
from pathlib import Path

PKG = Path(r"C:/Users/11768/Documents/GTIIT learning/日常事项/Manifest/codex-workspace/icon-lab/handoff/manifest-icons-final")
UI = Path(r"C:/Users/11768/Documents/GTIIT learning/日常事项/Manifest/manifest-agent/demo/public/js/ui.js")


def half(num: str) -> str:
    v = round(float(num) / 2, 2)
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def conv_d(d: str) -> str:
    assert not re.search(r"[AaSsTtmlhvqczr]", d), d      # only absolute M L H V Q C Z expected
    return re.sub(r"-?\d*\.?\d+", lambda m: half(m.group(0)), d)


def conv(inner: str) -> str:
    out = []
    for tag, attrs in re.findall(r"<(\w+)\s([^>]*?)\s*/?>", inner):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        if tag == "path":
            s = f'<path d="{conv_d(a["d"])}"'
        elif tag == "circle":
            s = f'<circle cx="{half(a["cx"])}" cy="{half(a["cy"])}" r="{half(a["r"])}"'
        else:
            raise SystemExit("unexpected tag " + tag)
        for k in ("fill", "stroke"):
            if k in a:
                s += f' {k}="{a[k]}"'
        if "stroke-width" in a:     # compass needle / ticks are drawn a touch lighter than the outline
            s += f' stroke-width="{half(a["stroke-width"])}"'
        out.append(s + "/>")
    return "".join(out)


rows = list(csv.DictReader(open(PKG / "替换清单.csv", encoding="utf-8-sig")))
new = {}
for r in rows:
    if r["处理"] in ("REPLACE", "ADD_STARTUP"):
        svg = (PKG / r["SVG文件"]).read_text(encoding="utf-8")
        assert 'viewBox="0 0 48 48"' in svg, r["key"]
        new[r["key"]] = conv(re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1))
print(len(new), "icons")

src = UI.read_text(encoding="utf-8")
start = src.index("export const ICONS = {")
end = src.index("};", start)
block = src[start:end]
done = set()
lines = block.split("\n")
for i, line in enumerate(lines):
    m = re.match(r"  (\w+): '.*',$", line)
    if m and m.group(1) in new:
        lines[i] = f"  {m.group(1)}: '{new[m.group(1)]}',"
        done.add(m.group(1))
missing = [k for k in new if k not in done]
for k in missing:                      # footsteps (new)
    lines.insert(len(lines) - 1, f"  {k}: '{new[k]}',")
block = "\n".join(lines)
src = src[:start] + block + src[end:]
UI.write_text(src, encoding="utf-8")
print("replaced", len(done), "added", missing)

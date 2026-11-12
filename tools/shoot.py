"""Desktop screenshots of the local app with the installed Chrome (dev tool).

    python tools/shoot.py <base_url> <outdir> <route> [<route> ...]

Logs in as a fresh seeded guest, visits each #route at 1440x900 and saves
<outdir>/<route>.png. Pass route 'gate' to shoot the logged-out page.
Playwright lives outside the repo (PW_PATH env), never shipped.
"""
import os
import sys

sys.path.insert(0, os.environ.get("PW_PATH", ""))
from playwright.sync_api import sync_playwright  # noqa: E402


def main():
    base, out, routes = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.makedirs(out, exist_ok=True)
    w, hgt = int(os.environ.get("SHOT_W", 1440)), int(os.environ.get("SHOT_H", 900))
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = b.new_context(viewport={"width": w, "height": hgt}, device_scale_factor=1)
        page = ctx.new_page()
        logs = []
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
        if "gate" in routes:
            page.goto(base + "/")
            page.wait_for_timeout(2600)
            page.screenshot(path=os.path.join(out, "gate.png"))
            routes = [r for r in routes if r != "gate"]
        if routes:
            page.request.post(base + "/api/auth/guest", data={"seed": True})
            for r in routes:
                action = None
                if ":" in r:
                    r, action = r.split(":", 1)
                page.goto(f"{base}/#{r}")
                page.reload()
                page.wait_for_timeout(1800)
                if action:
                    for step in action.split(","):
                        if step.startswith("click="):
                            page.click(step[6:])
                        elif step.startswith("wait="):
                            page.wait_for_timeout(int(step[5:]))
                        elif step.startswith("fill="):
                            sel, val = step[5:].split("|", 1)
                            page.fill(sel, val)
                        elif step.startswith("scroll="):
                            page.evaluate(f"document.querySelector('{step[7:]}').scrollTop = 1e6")
                page.screenshot(path=os.path.join(out, f"{r}{'-' + str(abs(hash(action)) % 1000) if action else ''}.png"))
        for line in logs[:30]:
            print(line)
        b.close()


if __name__ == "__main__":
    main()

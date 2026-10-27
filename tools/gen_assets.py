"""Generate the transparent art used by the web app (pets, garden, stickers).

    OPENLUX_API_KEY=... python tools/gen_assets.py [--force] [name ...]

Uses gpt-image-1.5 with background=transparent (gpt-image-2 on this relay
returns RGB with a painted checkerboard, so it can't be layered). Raw PNGs
go to tools/.raw/, then each image is trimmed to its alpha bounds, scaled
and written as WebP-with-alpha into demo/public/assets/art/.
Skips names that already exist unless --force.
"""
import base64
import json
import os
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = "https://api.openlux.ai/v1"
KEY = os.environ.get("OPENLUX_API_KEY", "")
HERE = pathlib.Path(__file__).resolve().parent
RAW = HERE / ".raw"
OUT = HERE.parent / "demo" / "public" / "assets" / "art"

STYLE = ("cute glossy 3D collectible toy style, soft studio lighting with gentle rim light, "
         "pastel mint green and warm cream palette with small amber-gold accents, rounded chubby "
         "proportions, big shiny dark eyes with highlights when it has eyes, clean readable silhouette, "
         "single isolated subject, centered, full body visible, no background, no ground shadow, no text")

ITEMS = {
    # ---- pet line (小芽) ----
    "pet-egg": ("a smooth rounded egg, cream white with soft mint speckles, a tiny two-leaf green sprout "
                "growing from a small crack at the top, faint warm golden glow from inside, sitting upright", 360),
    "pet-fox-1": ("a small chubby fox cub, fluffy mint-green and cream fur, a tiny green leaf sprout between its ears, "
                  "a big fluffy tail whose tip glows warm amber like a little flame, playful sitting pose", 420),
    "pet-fox-2": ("a graceful adult fox spirit, flowing mint and cream fur, a crest of two leaf sprouts, one long "
                  "flowing tail with a glowing amber flame tip, small embers floating, confident standing pose", 480),
    "pet-deer-1": ("a tiny chubby fawn, cream fur with soft mint spots, little antlers made of green twigs with pink "
                   "blossom buds, big shiny eyes, standing shyly", 420),
    "pet-deer-2": ("a gentle adult deer spirit, cream and mint fur, large elegant antlers covered in blooming pink and "
                   "white flowers and small leaves, a few glowing fireflies around, standing calmly", 480),
    "pet-whale-1": ("a tiny chubby baby whale made of soft fluffy cloud, pale mint and sky blue, floating, a small "
                    "green leaf sprout on its head like a water spout, big shiny eyes, gentle smile", 420),
    "pet-whale-2": ("a majestic friendly sky whale made of soft clouds, pale mint and lavender, floating serenely, "
                    "a small leafy tree growing on its back, a few glowing stars around it", 480),
    "pet-star-1": ("a small chubby cat-like spirit creature, deep indigo fur with tiny glowing golden star spots like "
                   "constellations, a leaf sprout on its head, crescent-moon shaped tail, big shiny eyes", 420),
    "pet-star-2": ("a mystical elegant cat-like guardian spirit, indigo and violet fur sparkling with golden "
                   "constellations, a glowing crescent halo above its head, long flowing tail with stars, serene pose", 480),
    # ---- garden ----
    "garden-island": ("a small round floating grass island seen from an isometric three-quarter view, lush soft green "
                      "grass on top that is flat and empty, rich brown soil and rounded stones underneath tapering "
                      "downward, tiny flowers around the rim", 720),
    "plant-sprout": ("a single small green two-leaf sprout growing from a tiny soil mound, isometric three-quarter view", 200),
    "plant-tulip": ("a single small cluster of three pink tulip buds with leaves in a tiny soil mound, isometric view", 220),
    "plant-bush": ("a single small round green bush with a few red berries, isometric three-quarter view", 220),
    "plant-tree": ("a single small round cartoon tree with a fluffy mint-green canopy and short brown trunk, isometric view", 260),
    "plant-glow": ("a single small magical tree with a round canopy and softly glowing golden fruit like lanterns, isometric view", 260),
    # ---- stickers ----
    "st-jar": ("a small glass jar filled with glowing golden stars, cork lid tied with a ribbon", 320),
    "st-compass": ("a cute chubby brass compass with a mint-green face and a golden needle", 320),
    "st-lotus": ("a glowing pink lotus flower floating with a soft light in its center", 320),
    "st-letter": ("a cream envelope sealed with a red heart wax seal, small sparkles around", 320),
    "st-steps": ("seven small rounded stepping stones rising upward in a gentle curve with a glowing star at the top", 320),
    "st-mirror": ("a round hand mirror with a mint-green frame reflecting little sparkles", 320),
    "st-book": ("an open storybook with a green leaf bookmark and soft glowing pages", 320),
    "st-flag": ("a small mint flag planted on a tiny grassy hilltop with a sprout beside it", 320),
    "st-moon": ("a sleepy crescent moon resting on a soft fluffy cloud pillow, closed eyes, tiny zzz", 320),
    "st-chest": ("a small treasure chest, mint green with gold trim, lid slightly open with golden sparkles coming out", 320),
    "st-chest-open": ("a small open treasure chest, mint green with gold trim, overflowing with glowing stars and coins", 320),
    "st-seed": ("a single shiny seed with a tiny sprout and a soft golden glow, floating", 260),
}


def generate(name: str, subject: str) -> pathlib.Path | None:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"{name}.png"
    if dest.exists() and "--force" not in sys.argv:
        return dest
    body = {"model": "gpt-image-1.5", "prompt": f"{subject}. {STYLE}", "n": 1, "size": "1024x1024",
            "background": "transparent", "output_format": "png"}
    req = urllib.request.Request(BASE + "/images/generations", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
                                 method="POST")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                d = json.loads(r.read())
            it = d["data"][0]
            raw = base64.b64decode(it["b64_json"]) if it.get("b64_json") else urllib.request.urlopen(it["url"]).read()
            dest.write_bytes(raw)
            print("ok", name, flush=True)
            return dest
        except Exception as e:  # noqa: BLE001
            print("retry", name, attempt + 1, type(e).__name__, str(e)[:120], flush=True)
            time.sleep(5 * (attempt + 1))
    print("FAILED", name, flush=True)
    return None


def finish(name: str, src: pathlib.Path, size: int) -> None:
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    box = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if box:
        pad = 12
        box = (max(0, box[0] - pad), max(0, box[1] - pad), min(im.width, box[2] + pad), min(im.height, box[3] + pad))
        im = im.crop(box)
    im.thumbnail((size, size), Image.LANCZOS)
    OUT.mkdir(parents=True, exist_ok=True)
    im.save(OUT / f"{name}.webp", "WEBP", quality=88, method=6)


def main() -> int:
    if not KEY:
        print("OPENLUX_API_KEY missing")
        return 2
    wanted = [a for a in sys.argv[1:] if not a.startswith("--")] or list(ITEMS)
    sem = threading.Semaphore(4)
    failed = []

    def work(n):
        with sem:
            subject, size = ITEMS[n]
            p = generate(n, subject)
            if p:
                finish(n, p, size)
            else:
                failed.append(n)

    ts = [threading.Thread(target=work, args=(n,)) for n in wanted]
    [t.start() for t in ts]
    [t.join() for t in ts]
    print("done; failed:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

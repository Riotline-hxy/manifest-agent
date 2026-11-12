"""把官方展示账号要用的几张真照片压成 App 里的大小（大图长边 1600、小图长边 480，JPEG），
放进 demo/showcase_photos/，core/showcase.py 建账号时会挂到对应的瞬间上。

  python tools/prep_showcase_photos.py hk=香港.jpg coast=海岸.jpg noodle=沙茶面.jpg words=扇贝打卡.jpg

名字对应的瞬间：hk 香港商场的天花板 · coast 西贡徒步看到的海 · noodle 自己做的沙茶面 · words 扇贝打卡截图。
"""
import sys
from pathlib import Path

from PIL import Image, ImageOps

OUT = Path(__file__).resolve().parent.parent / "demo" / "showcase_photos"
NAMES = {"hk", "coast", "noodle", "words"}


def shrink(src: Path, name: str) -> None:
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    for suffix, side, q in (("", 1600, 82), ("_s", 480, 78)):
        x = im.copy()
        x.thumbnail((side, side))
        x.save(OUT / f"{name}{suffix}.jpg", "JPEG", quality=q, optimize=True)
    print("ok", name, src.name)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for arg in sys.argv[1:]:
        name, path = arg.split("=", 1)
        if name not in NAMES:
            raise SystemExit(f"不认识的名字 {name}，只能是 {sorted(NAMES)}")
        shrink(Path(path), name)

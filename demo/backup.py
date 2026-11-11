"""把数据目录做一份前后一致的备份（部署前由 deploy/deploy.sh 调用，也可以手动跑）：

    python3 backup.py <数据目录> <备份到哪> [--photos]

服务运行着也能做。SQLite 的库（*.db）开着 WAL，直接拷文件可能拷到「写了一半」的状态
（.db、-wal、-shm 三个文件不是同一瞬间的）；这里用 SQLite 自带的在线备份接口复制，
拷出来的每个库再做一次完整性检查。其余的小文件（vapid.json、town_config.json、admin_log.jsonl……）原样拷。
瞬间的照片（u/<uid>/photos）默认跳过：它们只增删、不会被改，每次都整份复制只会白占硬盘；要连照片一起备份加 --photos。

退出码 0：全部成功。非 0：有库没备份好（哪一个会打印出来），这时不要继续部署。
只读数据目录，不改它；只用标准库。
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path


def backup_db(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    a = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True, timeout=30)
    b = sqlite3.connect(dst)
    try:
        a.backup(b)
        ok = b.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise sqlite3.DatabaseError(f"integrity_check: {ok}")
    finally:
        b.close()
        a.close()


def run(src: Path, dst: Path, photos: bool = False) -> tuple[int, int, list[str]]:
    dbs, files, failed = 0, 0, []
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if not f.is_file() or f.name.endswith(("-wal", "-shm", ".tmp")):
            continue
        if not photos and "photos" in rel.parts[:-1]:
            continue
        out = dst / rel
        try:
            if f.suffix == ".db":
                backup_db(f, out)
                dbs += 1
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, out)
                files += 1
        except (sqlite3.Error, OSError) as e:
            failed.append(f"{rel}: {e}")
    return dbs, files, failed


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        return 2
    src, dst = Path(args[0]).resolve(), Path(args[1]).resolve()
    if not src.is_dir():
        print(f"没有这个数据目录：{src}")
        return 2
    if dst == src or src in dst.parents:
        print("备份不能放在数据目录里面")
        return 2
    dbs, files, failed = run(src, dst, photos="--photos" in argv)
    print(f"备份到 {dst}：{dbs} 个库，{files} 个其他文件" + ("" if "--photos" in argv else "（照片没有备份）"))
    for line in failed:
        print("  没备份好：", line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

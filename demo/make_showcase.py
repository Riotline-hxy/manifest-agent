"""建官方展示账号（core/showcase.py）：python make_showcase.py 用户名 密码
已有这个用户名：清空它的数据重建，密码改成给的这个。"""
import shutil
import sys

from core import auth
from core.showcase import seed_showcase
from core.store import Store
from core.util import DATA


def main(username: str, password: str) -> None:
    with auth._lock:
        row = auth.db().execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if row:
        uid = row["id"]
        with auth._lock:
            auth.db().execute("UPDATE users SET pw_hash=?, kind='member' WHERE id=?", (auth.hash_password(password), uid))
        shutil.rmtree(DATA / "u" / uid, ignore_errors=True)
    else:
        uid = auth.register(username, password)["id"]
    with Store(uid) as st:
        out = seed_showcase(st)
    print(f"ok {username} uid={uid} {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

"""坏点升格回放：双写两轨 + 切流账册钉升格指纹。

工程形态（择定）：双写两轨
- 原坏点行进只读归档：坏点匣行不删，坏点状态 由 在匣 改 已升格（影子），钉升格指纹。
- 现行入栏改读升格后集合：入栏缓冲新增一行（原报文编号随行），命运 在栏，钉同一指纹。
- 两轨读引用不同：影子可查但不计入"在匣坏点"，贯验只认在匣；升格指纹须两轨齐。
- 切流账册（升格账）钉指纹：无键/无指纹回放拒绝；指纹幂等，二次回放拒绝。
- 升格写现行与销匣同成败：一票一事务（BEGIN IMMEDIATE），整票回滚。
- 并发：进程内 RLock + 跨进程文件锁 + 库级立即写锁，升格与新装同号并发只许一个命运。
"""
from __future__ import annotations

import os
import threading
import uuid
from contextlib import contextmanager

from app import db
from app.db import 连接
from app.seed import 此刻

NAME = "坏点升格回放"
在匣 = "在匣"
已升格 = "已升格"
坏点入栏 = "在栏"

_进程锁 = threading.RLock()


@contextmanager
def _升格锁():
    """进程内 RLock 串行；另用文件锁覆盖跨进程双请求脚本。"""
    db.数据目录.mkdir(parents=True, exist_ok=True)
    锁路径 = db.数据目录 / "升格回放.lock"
    with _进程锁:
        fh = open(锁路径, "w")
        try:
            try:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except ImportError:  # 非 POSIX 退化到仅进程锁
                pass
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except ImportError:
                pass
            fh.close()


def _取键(体: dict) -> list[int]:
    体 = 体 or {}
    原始 = 体.get("坏点编号")
    if 原始 is None:
        原始 = 体.get("匣号")
    if isinstance(原始, int):
        原始 = [原始]
    if not isinstance(原始, list) or not 原始:
        raise ValueError("无键回放拒绝：须带坏点编号（原旁路键）")
    键: list[int] = []
    for x in 原始:
        try:
            键.append(int(x))
        except (TypeError, ValueError):
            raise ValueError(f"坏点编号非法:{x!r}")
    if len(set(键)) != len(键):
        raise ValueError("一票内坏点编号重复")
    return 键


def 升格回放(体: dict) -> dict:
    """把在匣坏点升格回放到当前栏入栏缓冲。整票原子，失败全滚。"""
    键 = _取键(体)
    指定指纹 = str(体.get("升格指纹") or "").strip()
    if 指定指纹 and not 指定指纹.startswith("升格-"):
        raise ValueError("升格指纹形态非法")

    with _升格锁():
        conn = 连接()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # 切流账册：指纹幂等。指定指纹已存在即拒绝，杜绝同指纹二次回放
            if 指定指纹:
                撞 = conn.execute(
                    "SELECT 1 FROM 升格账 WHERE 升格指纹=?", (指定指纹,)
                ).fetchone()
                if 撞:
                    raise ValueError(f"升格指纹已存在，幂等拒绝:{指定指纹}")

            规行 = conn.execute(
                "SELECT 值 FROM 栏规 WHERE 键='当前栏号'"
            ).fetchone()
            栏号 = 规行["值"] if 规行 else "B-demo"

            影子 = conn.execute(
                f"SELECT * FROM 坏点匣 WHERE 编号 IN ({','.join('?' * len(键))})",
                键,
            ).fetchall()
            if len(影子) != len(键):
                raise ValueError(f"坏点编号不存在或已销匣:{键}")
            for r in 影子:
                if r["坏点状态"] != 在匣:
                    raise ValueError(
                        f"坏点 {r['编号']} 状态为 {r['坏点状态']}，不可重复升格"
                    )
            # 原报文编号若已在缓冲（并发新装抢先），拒绝，保证同号只有一条入栏
            for r in 影子:
                撞行 = conn.execute(
                    "SELECT 1 FROM 入栏缓冲 WHERE 报文编号=?", (r["报文编号"],)
                ).fetchone()
                if 撞行:
                    raise ValueError(f"报文 {r['报文编号']} 已在入栏缓冲，拒绝双命运")

            指纹 = 指定指纹 or f"升格-{uuid.uuid4().hex[:12]}"
            时刻 = 此刻()
            销匣 = 0
            for r in 影子:
                # 轨一：原坏点行进只读归档（不删行，改影子状态，钉指纹）
                conn.execute(
                    "UPDATE 坏点匣 SET 坏点状态=?, 升格指纹=?, 升格时=? WHERE 编号=?",
                    (已升格, 指纹, 时刻, r["编号"]),
                )
                # 轨二：现行入栏写升格后集合（原旁路键随行，钉同一指纹）
                conn.execute(
                    """INSERT INTO 入栏缓冲
                       (报文编号,站点键,指标键,读数,观测时,栏号,命运,入栏时,
                        升格指纹,来源坏点编号)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        r["报文编号"], r["站点键"],
                        conn.execute(
                            "SELECT 指标键 FROM 观测报文 WHERE 报文编号=?",
                            (r["报文编号"],),
                        ).fetchone()["指标键"],
                        r["读数"], r["观测时"], 栏号, 坏点入栏, 时刻,
                        指纹, r["编号"],
                    ),
                )
                conn.execute(
                    "UPDATE 观测报文 SET 命运=? WHERE 报文编号=?",
                    ("已升格", r["报文编号"]),
                )
                conn.execute(
                    """INSERT INTO 升格账
                       (升格指纹,坏点编号,报文编号,栏号,时刻)
                       VALUES (?,?,?,?,?)""",
                    (指纹, r["编号"], r["报文编号"], 栏号, 时刻),
                )
                销匣 += 1
            conn.commit()
            return {
                "升格指纹": 指纹,
                "指纹": 指纹,
                "升格": 销匣,
                "销匣": 销匣,
                "栏号": 栏号,
                "坏点编号": 键,
                "时刻": 时刻,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def 只读() -> list[dict]:
    """只读接口：切流账册（升格指纹 → 两轨引用）。"""
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 升格账 ORDER BY 时刻 DESC, 编号 DESC"
            ).fetchall()
        ]
    finally:
        conn.close()


def 在匣坏点() -> list[dict]:
    """现行坏点集合：只含在匣，归档影子排除。"""
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM 坏点匣 WHERE 坏点状态=? ORDER BY 编号 DESC",
                (在匣,),
            ).fetchall()
        ]
    finally:
        conn.close()


def 归档影子() -> list[dict]:
    """只读归档集合：已升格原行，与现行入栏读引用不同。"""
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM 坏点匣 WHERE 坏点状态=? ORDER BY 编号 DESC",
                (已升格,),
            ).fetchall()
        ]
    finally:
        conn.close()


def 额外贯验() -> list[str]:
    """升格两轨齐套贯验：每个升格指纹须账册、影子、现行缓冲三边齐，缺边即撕裂。"""
    conn = 连接()
    try:
        问题: list[str] = []
        账 = conn.execute("SELECT DISTINCT 升格指纹 FROM 升格账").fetchall()
        for row in 账:
            指纹 = row["升格指纹"]
            影 = conn.execute(
                "SELECT COUNT(*) AS c FROM 坏点匣 WHERE 升格指纹=? AND 坏点状态=?",
                (指纹, 已升格),
            ).fetchone()["c"]
            现 = conn.execute(
                "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 升格指纹=?",
                (指纹,),
            ).fetchone()["c"]
            账笔 = conn.execute(
                "SELECT COUNT(*) AS c FROM 升格账 WHERE 升格指纹=?", (指纹,)
            ).fetchone()["c"]
            if not (影 and 现 and 账笔 and 影 == 现 == 账笔):
                问题.append(
                    f"升格指纹 {指纹} 两轨缺边撕裂：账={账笔} 影子={影} 现行={现}"
                )
        # 反向：有指纹的缓冲行在账册里查无对应（孤儿现行）
        孤儿 = conn.execute(
            """SELECT b.升格指纹 FROM 入栏缓冲 b
               WHERE b.升格指纹 IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM 升格账 z WHERE z.升格指纹=b.升格指纹)"""
        ).fetchall()
        for r in 孤儿:
            问题.append(f"现行入栏挂无账指纹（孤儿）:{r['升格指纹']}")
        return 问题
    finally:
        conn.close()

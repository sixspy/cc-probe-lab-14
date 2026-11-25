"""栏贯验：已汇总缓冲报文数 == 汇总账报文数之和。

坏点口径只认"在匣"；已升格原行是只读归档影子，单列，绝不被当齐套。
"""
from __future__ import annotations
from app.db import 连接
from app.seed import 此刻
from app.services import 升格回放


def _取数(conn) -> dict:
    在栏 = conn.execute(
        "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'"
    ).fetchone()["c"]
    已汇总缓冲 = conn.execute(
        "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='已汇总'"
    ).fetchone()["c"]
    汇总报文 = conn.execute(
        "SELECT COALESCE(SUM(报文数),0) AS c FROM 站点汇总账"
    ).fetchone()["c"]
    坏点在匣 = conn.execute(
        "SELECT COUNT(*) AS c FROM 坏点匣 WHERE 坏点状态='在匣'"
    ).fetchone()["c"]
    升格影子 = conn.execute(
        "SELECT COUNT(*) AS c FROM 坏点匣 WHERE 坏点状态='已升格'"
    ).fetchone()["c"]
    return {
        "在栏": 在栏,
        "已汇总缓冲": int(已汇总缓冲),
        "汇总报文": int(汇总报文),
        "坏点在匣": int(坏点在匣),
        "升格影子": int(升格影子),
    }


def 跑一次() -> dict:
    conn = 连接()
    try:
        d = _取数(conn)
        对齐 = 1 if d["已汇总缓冲"] == d["汇总报文"] else 0
        升格问题 = 升格回放.额外贯验()
        说明 = (
            "入栏已汇总与站点汇总报文数一致"
            if 对齐
            else f"撕裂：已汇总缓冲={d['已汇总缓冲']} 汇总报文={d['汇总报文']}"
        )
        if 升格问题:
            说明 += "；升格两轨:" + ";".join(升格问题)
        时刻 = 此刻()
        conn.execute(
            """INSERT INTO 栏贯验(时刻,在栏笔数,汇总报文数,坏点笔数,是否对齐,说明)
               VALUES (?,?,?,?,?,?)""",
            (时刻, d["在栏"], d["汇总报文"], d["坏点在匣"], 对齐 and not 升格问题, 说明),
        )
        conn.commit()
        d.update({
            "时刻": 时刻,
            "坏点": d["坏点在匣"],
            "是否对齐": bool(对齐 and not 升格问题),
            "说明": 说明,
            "升格贯验": 升格问题,
        })
        return d
    finally:
        conn.close()


def 只读快照() -> dict:
    """不落库的贯验快照，供页面预览。"""
    conn = 连接()
    try:
        d = _取数(conn)
        d["坏点"] = d["坏点在匣"]
        d["是否对齐"] = (
            d["已汇总缓冲"] == d["汇总报文"] and not 升格回放.额外贯验()
        )
        d["升格贯验"] = 升格回放.额外贯验()
        return d
    finally:
        conn.close()

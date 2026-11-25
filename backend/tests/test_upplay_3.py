"""争用失败测：升格与新装同号并发双请求双命运则红。

并发双请求脚本同文件可独立运行：python3 tests/test_upplay_3.py
硬推理约束：
- 升格写现行（入栏缓冲）与销匣（坏点匣改影子）同成败，一票一事务。
- 升格与新装并发会争同一报文编号的命运，必须加锁串行，胜者唯一。
- 不加锁则两边都 SELECT 到"在匣/未入栏"，双双成功 → 双命运，红。
"""
import threading

from app.db import 连接
from app.services import 装载, 目录, 升格回放, 夹具


def _匣号(报文编号: str) -> int:
    return next(r["编号"] for r in 目录.坏点列表() if r["报文编号"] == 报文编号)


def _同号缓冲(编号: str) -> list[dict]:
    return [r for r in 目录.缓冲列表() if r["报文编号"] == 编号]


def test_并发双升格请求只许一个命运():
    装载.装一批(夹具.读取("坏点可升格成片"))
    匣号 = _匣号("P-bad-a")
    果: list[object] = []

    def 抢升格() -> None:
        try:
            果.append(升格回放.升格回放({"坏点编号": [匣号]}))
        except ValueError as e:
            果.append(e)

    t1 = threading.Thread(target=抢升格)
    t2 = threading.Thread(target=抢升格)
    t1.start(); t2.start(); t1.join(); t2.join()

    成功 = [x for x in 果 if isinstance(x, dict)]
    驳回 = [x for x in 果 if isinstance(x, ValueError)]
    assert len(成功) == 1 and len(驳回) == 1, f"双成功即双命运:{果}"
    assert len(_同号缓冲("P-bad-a")) == 1
    账 = 升格回放.只读()
    assert len(账) == 1
    影子 = [r for r in 目录.坏点列表() if r["报文编号"] == "P-bad-a"]
    assert len(影子) == 1 and 影子[0]["坏点状态"] == "已升格"


def test_升格与新装同号并发不许双成功():
    装载.装一批(夹具.读取("坏点样例"))
    匣号 = _匣号("P-bad-1")
    新装 = {
        "批次编号": "并发新装",
        "报文": [{
            "报文编号": "P-bad-1",
            "站点键": "站-河东",
            "指标键": "PM25",
            "读数": 33.0,
            "观测时": "2026-11-24T10:30:00Z",
        }]
    }
    果: dict[str, object] = {}

    def 升格侧() -> None:
        try:
            果["升格"] = 升格回放.升格回放({"坏点编号": [匣号]})
        except Exception as e:  # noqa: BLE001
            果["升格"] = e

    def 新装侧() -> None:
        果["新装"] = 装载.装一批(新装)

    t1 = threading.Thread(target=升格侧)
    t2 = threading.Thread(target=新装侧)
    t1.start(); t2.start(); t1.join(); t2.join()

    # 无论谁先谁后：同号报文只许一行、同号入栏只许一条
    conn = 连接()
    try:
        报文数 = conn.execute(
            "SELECT COUNT(*) AS c FROM 观测报文 WHERE 报文编号=?", ("P-bad-1",)
        ).fetchone()["c"]
    finally:
        conn.close()
    assert 报文数 == 1
    assert len(_同号缓冲("P-bad-1")) == 1, "升格与新装各插一条即双命运，红"
    新装报 = 果["新装"]
    assert isinstance(新装报, dict) and 新装报["入栏"] == 0
    assert 新装报["驳回"] == 1


def test_成片升格并发竞争不半票不重复():
    装载.装一批(夹具.读取("坏点可升格成片"))
    号 = {名: _匣号(名) for 名 in ("P-bad-a", "P-bad-b", "P-bad-c")}
    果: list[object] = []

    def 抢(票: list[int]) -> None:
        try:
            果.append(升格回放.升格回放({"坏点编号": 票}))
        except ValueError as e:
            果.append(e)

    t1 = threading.Thread(target=抢, args=([号["P-bad-a"], 号["P-bad-b"]],))
    t2 = threading.Thread(target=抢, args=([号["P-bad-b"], 号["P-bad-c"]],))
    t1.start(); t2.start(); t1.join(); t2.join()

    成功 = [x for x in 果 if isinstance(x, dict)]
    assert len(成功) == 1, f"竞争票必须一成一整败:{果}"
    # 任一报文编号在缓冲里最多一条；账册(指纹,匣号)组合不重复
    for 名 in 号:
        assert len(_同号缓冲(名)) <= 1
    账 = 升格回放.只读()
    组合 = [(r["升格指纹"], r["坏点编号"]) for r in 账]
    assert len(组合) == len(set(组合))
    账上号 = [r["报文编号"] for r in 账]
    assert len(账上号) == len(set(账上号))


def test_只读接口不落库且无键回放拒():
    import pytest

    pytest.importorskip("quart")
    from app.main import app
    import asyncio

    装载.装一批(夹具.读取("坏点样例"))

    async def 跑() -> None:
        client = app.test_client()
        r = await client.get("/api/坏点升格回放")
        assert r.status_code == 200
        assert (await r.get_json()) == []
        r2 = await client.post("/api/坏点升格回放/跑", json={})
        assert r2.status_code == 400
        body = await r2.get_json()
        assert "错误" in body

    asyncio.run(跑())
    assert 目录.缓冲列表() == []
    assert 升格回放.只读() == []


if __name__ == "__main__":
    # 并发双请求脚本：独立进程内对同号坏点并发打"升格/新装"双请求
    import os
    import tempfile

    os.environ.setdefault("数据目录", tempfile.mkdtemp(prefix="upplay-race-"))
    from app import seed
    seed.初始化库()
    装载.装一批(夹具.读取("坏点样例"))
    匣号 = _匣号("P-bad-1")
    箱: dict[str, object] = {}

    def _升格() -> None:
        try:
            箱["升格"] = 升格回放.升格回放({"坏点编号": [匣号]})
        except Exception as e:  # noqa: BLE001
            箱["升格"] = repr(e)

    def _新装() -> None:
        箱["新装"] = 装载.装一批({
            "批次编号": "脚本新装",
            "报文": [{
                "报文编号": "P-bad-1", "站点键": "站-河东", "指标键": "PM25",
                "读数": 33.0, "观测时": "2026-11-24T10:30:00Z",
            }],
        })

    ts = [threading.Thread(target=_升格), threading.Thread(target=_新装)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(_同号缓冲("P-bad-1")) == 1, "并发双命运"
    print("并发双请求脚本通过：", 箱)

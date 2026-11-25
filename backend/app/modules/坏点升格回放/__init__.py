"""坏点升格回放（已落桩）。

工程形态：双写两轨 + 切流账册钉升格指纹。
- 原坏点进只读归档（坏点状态=已升格，影子，钉指纹）；
- 现行入栏改读升格后集合（入栏缓冲带同一升格指纹，原报文编号随行）；
- 无键/无指纹回放拒绝；指纹幂等；升格写现行与销匣同成败（一票一事务）；
- 进程锁 + 文件锁 + BEGIN IMMEDIATE，升格与新装同号并发只许一个命运。
实现在 app.services.升格回放，本模块保留骨签钩子位与页面契约。
"""
from app.services import 升格回放 as _服务

NAME = "坏点升格回放"
CONTRACT = "坏点匣可升格回放进下一栏缓冲，原旁路键随行，双写两轨可区分"
HOOKS = ("before_load", "after_load", "decide_gate", "before_close", "after_close", "extra_verify_checks")


def describe() -> dict:
    return {
        "模块": NAME,
        "契约": CONTRACT,
        "钩子": list(HOOKS),
        "默认启用": True,
        "形态": "双写两轨+切流账册钉指纹",
        "只读接口": "/api/坏点升格回放",
        "回放接口": "/api/坏点升格回放/跑",
    }


def 升格回放(体: dict) -> dict:
    return _服务.升格回放(体)


def 只读() -> list[dict]:
    return _服务.只读()


def before_load(batch: dict) -> dict:
    return batch


def after_load(report: dict) -> dict:
    return report


def decide_gate(event: dict, rules: dict) -> str:
    return "入栏"


def before_close(pen_id: str) -> None:
    return None


def after_close(report: dict) -> dict:
    return report


def extra_verify_checks(snapshot: dict) -> list[str]:
    return _服务.额外贯验()

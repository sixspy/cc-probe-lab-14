"""空桩：坏点旁路保留

契约：
- 坏点匣保留原读数与观测时，供升格回放
- 已落轨：在匣行为现行坏点；升格后原行转只读归档影子（坏点状态=已升格，钉升格指纹），
  与入栏缓冲的升格现行行读引用不同，影子不计入在匣坏点、不被贯验当齐套。
- 不得改坏基线默认门槛 happy path（装载→入栏/坏点→结栏汇总→贯验）。
- 页面须能读到：当前策略名、命运变化、可点的下一步。
"""
NAME = "坏点旁路保留"
CONTRACT = "坏点匣保留原读数与观测时，供升格回放"
HOOKS = ("before_load", "after_load", "decide_gate", "before_close", "after_close", "extra_verify_checks")


def describe() -> dict:
    return {"空桩": NAME, "契约": CONTRACT, "钩子": list(HOOKS), "默认启用": False}


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
    return []

# -*- coding: utf-8 -*-
"""角色名映射 — 统一定义职场名↔传统名的双向映射、颜色、阵营

此模块替代此前散落在 evaluation_cn.py / jsonl_parser.py / web_ui.py /
eval_agent/context_builder.py / skills_agent/generator.py 等处的重复定义。
"""

from __future__ import annotations

# ── 职场名 → 传统名（评测与分析用）──────────────────────────────────────
ROLE_ALIASES: dict[str, str] = {
    "间谍": "狼人",
    "HR总监": "预言家",
    "CEO": "女巫",
    "法务总监": "猎人",
    "安保主管": "守护者",
    "普通员工": "村民",
}

# ── 传统名 → 职场名（反向映射，web_ui 展示用）────────────────────────────
ROLE_ALIASES_REVERSE: dict[str, str] = {
    "狼人": "商业间谍",
    "预言家": "预言家",
    "女巫": "女巫",
    "猎人": "猎人",
    "守护者": "守护者",
    "村民": "普通员工",
}

# ── 任意名 → 职场名（评测上下文归一化用）──────────────────────────────────
# 同时接受传统名和职场名，统一输出为职场名（如 狼人→间谍, 间谍→间谍）
ROLE_ALIASES_TO_WORKPLACE: dict[str, str] = {
    # Traditional → workplace
    "狼人": "间谍",
    "预言家": "HR总监",
    "女巫": "CEO",
    "猎人": "法务总监",
    "守护者": "安保主管",
    "村民": "普通员工",
    # Workplace → workplace (identity)
    "间谍": "间谍",
    "HR总监": "HR总监",
    "CEO": "CEO",
    "法务总监": "法务总监",
    "安保主管": "安保主管",
    "普通员工": "普通员工",
}

# ── 阵营分类 ──────────────────────────────────────────────────────────────
VILLAGER_TEAM: set[str] = {"预言家", "女巫", "猎人", "守护者", "村民"}

# ── 角色颜色（前端展示用）─────────────────────────────────────────────────
ROLE_COLORS: dict[str, str] = {
    "狼人": "#a11d33",
    "商业间谍": "#a11d33",
    "预言家": "#2563eb",
    "HR总监": "#2563eb",
    "女巫": "#7c3aed",
    "CEO": "#7c3aed",
    "猎人": "#a16207",
    "法务总监": "#a16207",
    "守护者": "#0f766e",
    "安保主管": "#0f766e",
    "村民": "#475569",
    "普通员工": "#475569",
}


def normalize_role(role: str | None, strip_punct: bool = True) -> str:
    """将职场角色名归一化为传统名（如 间谍→狼人, CEO→女巫）

    Args:
        role: 原始角色名，可为 None
        strip_punct: 是否去除中文标点（评测场景需要，JSONL 解析不需要）
    """
    if not role:
        return "未知"
    cleaned = role.strip()
    if strip_punct:
        cleaned = cleaned.strip(" ，。:：")
    return ROLE_ALIASES.get(cleaned, cleaned)


def normalize_role_to_workplace(role: str | None, strip_punct: bool = True) -> str:
    """将任意角色名归一化为职场名（如 狼人→间谍, CEO→CEO）

    用于 eval_agent/context_builder 等需要统一使用职场名的场景。

    Args:
        role: 原始角色名，可为 None
        strip_punct: 是否去除中文标点
    """
    if not role:
        return "未知"
    cleaned = role.strip()
    if strip_punct:
        cleaned = cleaned.strip(" ，。:：")
    return ROLE_ALIASES_TO_WORKPLACE.get(cleaned, cleaned)


def normalize_role_webui(role: str | None) -> str:
    """将任意角色名映射到 web_ui 展示用的职场名

    同时接受职场名和传统名，统一输出为展示名。
    例如：间谍→商业间谍, 狼人→商业间谍, CEO→女巫
    """
    if not role:
        return "普通员工"
    cleaned = role.strip()
    # 先尝试 职场名→传统名 归一化
    trad = ROLE_ALIASES.get(cleaned, cleaned)
    # 再映射到 web_ui 展示名
    return ROLE_ALIASES_REVERSE.get(trad, cleaned)

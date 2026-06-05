# -*- coding: utf-8 -*-
"""游戏规则与策略知识库 — 评测Agent的领域知识

此模块作为评测Agent的"内化知识"，嵌入到评测Prompt的系统提示中，
使LLM以职场狼人杀专家视角评分。使用职场狼人杀术语而非传统狼人杀术语。
"""


# ── 4.1 角色与技能定义 ──────────────────────────────────────

ROLE_DEFINITIONS = {
    "间谍": {
        "workplace_names": ["卷王", "造谣者", "偷窥者"],
        "team": "潜伏阵营",
        "skill": "夜间与队友协商窃取（击杀）一名员工",
        "win_conditions": [
            "间谍人数≥好人人数（人数优势）",
            "神职角色全部阵亡（屠神）",
            "普通员工全部阵亡（屠民）",
        ],
    },
    "HR总监": {
        "workplace_names": ["HR总监"],
        "team": "公司阵营",
        "skill": "夜间背调（查验）一人真实身份",
        "win_conditions": ["所有间谍被开除"],
    },
    "CEO": {
        "workplace_names": ["CEO"],
        "team": "公司阵营",
        "skill": "持有留人offer（解药）和辞退信（毒药）各一张",
        "win_conditions": ["所有间谍被开除"],
    },
    "法务总监": {
        "workplace_names": ["法务总监"],
        "team": "公司阵营",
        "skill": "被开除时（非毒杀）可发起诉讼（带走一人）",
        "win_conditions": ["所有间谍被开除"],
    },
    "安保主管": {
        "workplace_names": ["安保主管"],
        "team": "公司阵营",
        "skill": "夜间保护一人免于窃取（不可连续保护同一人）",
        "win_conditions": ["所有间谍被开除"],
    },
    "普通员工": {
        "workplace_names": ["普通员工"],
        "team": "公司阵营",
        "skill": "无特殊技能",
        "win_conditions": ["所有间谍被开除"],
    },
}

KEY_RULES = [
    "安保主管不可连续两夜保护同一人",
    "法务总监被辞退信（毒药）击杀时不可发起诉讼",
    "同夜被安保主管保护且CEO使用留人offer → 该员工仍然出局（保护+解药不叠加）",
    "CEO看到被窃取的员工后决定是否使用留人offer，不可救自己",
    "CEO的辞退信可在任意夜晚使用（包括同夜使用解药的夜晚）",
]


# ── 4.2 高级策略知识 ──────────────────────────────────────

SPY_STRATEGIES = {
    "冒充HR总监": {
        "aka": "悍跳/穿衣服",
        "description": "间谍冒充HR总监，发布虚假背调结果：给好人发假查杀（声称某好人是间谍）或给队友发假金水（声称队友是好人），混淆视听",
    },
    "冒充法务总监": {
        "aka": "穿猎人衣",
        "description": '间谍冒充法务总监，利用"一换一"威慑阻止好人投票，即使被拆穿也能消耗法务总监的公信力',
    },
    "自刀骗银水": {
        "aka": "自刀",
        "description": '间谍夜间窃取自己的队友，使CEO误用留人offer救下"受害者"，该队友获得"银水"身份背书',
    },
    "冲锋": {
        "aka": "冲锋狼",
        "description": "明确站边、攻击好人阵营，用攻击性发言吸引注意力，即使被投出也消耗了好人资源",
    },
    "倒钩": {
        "aka": "倒钩狼",
        "description": '与队友刻意对立，投票/发言攻击队友，建立"好人"形象，在后期关键时刻反水',
    },
    "深潜": {
        "aka": "深水狼",
        "description": "全程低调，不参与核心争论，混在好人中间，避免成为焦点",
    },
    "煽动": {
        "aka": "煽动狼",
        "description": "不直接攻击，而是引导其他好人对立，制造内部矛盾，让好人互相投票",
    },
}

GOOD_STRATEGIES = {
    "银水逻辑": {
        "applicable_roles": "CEO/全体好人",
        "description": '被CEO留人offer救下的人不一定是好人——间谍可能自刀骗取银水身份。银水只能证明"此人被窃取过"，不能证明身份',
    },
    "背调优先级": {
        "applicable_roles": "HR总监",
        "description": "查验优先级：争议焦点玩家 > 行为不确定的沉默玩家 > 已亮明身份的玩家（避免重复）",
    },
    "跳身份时机": {
        "applicable_roles": "HR总监",
        "description": "首轮跳明可尽早提供信息但风险大；延迟跳明可积累更多背调但可能被悍跳抢占话语权",
    },
    "一换一威慑": {
        "applicable_roles": "法务总监",
        "description": '公开身份后，威胁"投我出去就拉你"，阻止间谍投票。但间谍可能冒充法务总监反制',
    },
    "交替保护": {
        "applicable_roles": "安保主管",
        "description": "不可连续保护同一人，需在HR总监/CEO/有价值员工之间交替，且保护成功是隐藏信息",
    },
    "隐藏身份": {
        "applicable_roles": "安保主管",
        "description": "安保主管身份不公开，可暗中保护关键角色。保护成功只有被保护者知道，安保主管可通过此推断对方身份",
    },
}


# ── 4.3 核心推理原则 ──────────────────────────────────────

REASONING_PRINCIPLES = [
    "某人被背调为好人 → 可能是冒充HR总监的间谍在发假金水",
    "某人被窃取过 → 可能是间谍自刀骗银水",
    "某人攻击队友 → 可能是倒钩策略而非真的好人",
    "某人保持沉默 → 可能是深潜策略而非无害",
    "某人帮助好人 → 可能是倒钩/深潜策略在建立信用",
    "某人声称被保护 → 可能是间谍利用保护成功信息伪装",
]


# ── 4.4 核心函数 ──────────────────────────────────────


def get_role_knowledge(role: str) -> str:
    """返回指定角色的技能、策略和评估标准"""
    parts = []

    role_def = ROLE_DEFINITIONS.get(role, {})
    if role_def:
        parts.append(f"## {role}的角色定义")
        parts.append(f"- 阵营: {role_def.get('team', '未知')}")
        parts.append(f"- 技能: {role_def.get('skill', '无')}")
        parts.append(f"- 胜利条件: {'; '.join(role_def.get('win_conditions', []))}")

    # 间谍专属策略
    if role == "间谍":
        parts.append("\n## 间谍阵营高级策略")
        for name, info in SPY_STRATEGIES.items():
            parts.append(f"- **{name}**（又称{info['aka']}）: {info['description']}")

    # 公司阵营专属策略
    if role in ("HR总监", "CEO", "法务总监", "安保主管", "普通员工"):
        parts.append(f"\n## {role}的专属策略")
        for name, info in GOOD_STRATEGIES.items():
            if role in info.get("applicable_roles", "") or role == "普通员工" and name in ("银水逻辑",):
                parts.append(f"- **{name}**: {info['description']}")

    return "\n".join(parts)


def get_strategy_knowledge(team: str) -> str:
    """返回阵营的高级策略知识（team="spy" 或 "company"）"""
    if team == "spy":
        lines = ["## 潜伏阵营（间谍）策略"]
        for name, info in SPY_STRATEGIES.items():
            lines.append(f"- **{name}**（又称{info['aka']}）: {info['description']}")
        return "\n".join(lines)
    else:
        lines = ["## 公司阵营（好人）策略"]
        for name, info in GOOD_STRATEGIES.items():
            lines.append(f"- **{name}**（适用: {info['applicable_roles']}）: {info['description']}")
        return "\n".join(lines)


def get_reasoning_principles() -> str:
    """返回核心推理原则"""
    lines = ["## 核心推理原则", "\"任何逻辑都可以是反逻辑\"——这是职场狼人杀的核心思辨原则："]
    for p in REASONING_PRINCIPLES:
        lines.append(f"- {p}")
    lines.append("评测时需判断：决策者是否意识到这些反逻辑可能性？是否在推理中体现了多层博弈思维？")
    return "\n".join(lines)


def get_full_system_prompt() -> str:
    """组装完整的评测系统提示"""
    parts = [
        "你是职场狼人杀的专业评委，拥有上帝视角（知道所有角色身份和游戏结果）。",
        "你需要基于对游戏规则、角色技能和高级策略的深刻理解来评判每个决策的质量。",
        "",
        "## 评测视角要求",
        "你需要同时从两个视角评判每个决策：",
        "1. **上帝视角**：基于真实角色身份，判断决策客观上是否合理",
        "2. **玩家视角**：基于该玩家当时能获得的信息，判断决策在有限信息下是否最优",
        "",
        "## 角色与技能定义",
    ]

    for role, defn in ROLE_DEFINITIONS.items():
        names = "/".join(defn["workplace_names"])
        parts.append(f"- **{role}**（{names}）: 阵营={defn['team']}, 技能={defn['skill']}")
        if defn.get("win_conditions"):
            for wc in defn["win_conditions"]:
                parts.append(f"  - 胜利条件: {wc}")

    parts.append("")
    parts.append("## 关键规则约束")
    for rule in KEY_RULES:
        parts.append(f"- {rule}")

    parts.append("")
    parts.append(get_strategy_knowledge("spy"))
    parts.append("")
    parts.append(get_strategy_knowledge("company"))
    parts.append("")
    parts.append(get_reasoning_principles())

    return "\n".join(parts)
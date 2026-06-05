# -*- coding: utf-8 -*-
"""评测维度定义 — 通用维度 + 角色专属维度 + 结果维度

替代原3个笼统维度(逻辑性/博弈合理性/话术质量)，
改为差异化的5通用 + 11角色专属 + 1结果维度体系。
维度名称使用职场狼人杀术语。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class GameStage(Enum):
    EARLY = "early"
    MID = "mid"
    LATE = "late"


@dataclass
class EvalDimension:
    """单个评测维度"""
    name: str                   # 维度名（中文，如"推理质量"）
    key: str                    # 维度key（英文，如"reasoning_quality"）
    description: str            # 评测要点
    score_range: tuple = (0, 100)
    applies_to: List[str] = field(default_factory=list)  # 适用event_type: ["speech","vote","skill"]


# ── 通用维度（所有决策都评）─────────────────────────────────────

COMMON_DIMENSIONS = [
    EvalDimension(
        name="推理质量",
        key="reasoning_quality",
        description="推理链是否连贯，证据引用是否具体可验证，是否体现多层博弈思维（考虑反逻辑可能）",
        applies_to=["speech", "vote", "skill"],
    ),
    EvalDimension(
        name="信息利用",
        key="information_utilization",
        description="是否利用了已知信息（背调结果/投票分布/死亡顺序），是否遗漏关键线索",
        applies_to=["speech", "vote", "skill"],
    ),
    EvalDimension(
        name="言行一致性",
        key="consistency",
        description="发言主张与实际投票/技能是否一致，是否存在自相矛盾",
        applies_to=["speech", "vote", "skill"],
    ),
    EvalDimension(
        name="博弈深度",
        key="game_depth",
        description="决策体现了第几层博弈思维（L0反应→L1推理→L2反逻辑→L3反反逻辑→L4+高阶操纵）",
        applies_to=["speech", "vote", "skill"],
    ),
    EvalDimension(
        name="信息隐藏",
        key="info_concealment",
        description="是否过早暴露身份/队友关系/关键信息，是否控制信息释放节奏",
        applies_to=["speech", "vote", "skill"],
    ),
]


# ── 角色专属维度 ──────────────────────────────────────────────

ROLE_DIMENSIONS = {
    "HR总监": [
        EvalDimension(
            name="背调效率",
            key="seer_efficiency",
            description="背调目标是否最大化信息增量，避免重复背调，优先查验争议玩家",
            applies_to=["skill"],
        ),
        EvalDimension(
            name="跳身份时机",
            key="seer_timing",
            description="何时亮明HR总监身份，是否在关键时刻提供背调信息，是否应对冒充",
            applies_to=["speech", "skill"],
        ),
    ],
    "安保主管": [
        EvalDimension(
            name="保护策略",
            key="guard_protection",
            description="保护目标是否合理（HR总监>CEO>自己>有价值员工），是否遵守不可连续保护规则，是否有效隐藏身份",
            applies_to=["skill"],
        ),
    ],
    "CEO": [
        EvalDimension(
            name="留人策略",
            key="witch_antidote",
            description="留人offer使用时机，是否考虑自刀骗银水风险，是否在关键轮次保留",
            applies_to=["skill"],
        ),
        EvalDimension(
            name="辞退策略",
            key="witch_poison",
            description="辞退信目标是否有充分证据，是否避免误伤好人，是否与已有信息交叉验证",
            applies_to=["skill"],
        ),
    ],
    "法务总监": [
        EvalDimension(
            name="诉讼策略",
            key="hunter_shoot",
            description="诉讼目标是否基于证据，是否优先带走高嫌疑间谍，是否有效利用一换一威慑",
            applies_to=["skill"],
        ),
    ],
    "间谍": [
        EvalDimension(
            name="团队协作",
            key="werewolf_coordination",
            description="窃取目标是否与队友协调，分工是否合理（冲锋/倒钩/深潜/煽动）",
            applies_to=["skill", "speech"],
        ),
        EvalDimension(
            name="伪装质量",
            key="werewolf_deception",
            description="白天发言是否有效执行冒充/倒钩/深潜策略，是否暴露队友关系",
            applies_to=["speech"],
        ),
        EvalDimension(
            name="投票策略",
            key="werewolf_vote_strategy",
            description="投票是否推动潜伏阵营目标，是否避免明显抱团，是否配合战术分工",
            applies_to=["vote"],
        ),
    ],
    "普通员工": [
        EvalDimension(
            name="公司贡献",
            key="village_contribution",
            description="投票/发言是否帮助识别间谍，是否理解各神职角色特点",
            applies_to=["speech", "vote"],
        ),
    ],
}


# ── 结果维度（游戏结束后评）───────────────────────────────────

OUTCOME_DIMENSION = EvalDimension(
    name="结果对齐度",
    key="outcome_alignment",
    description="决策是否实际帮助了阵营目标（公司阵营获胜→好人决策对齐度高；潜伏阵营获胜→间谍决策对齐度高）",
    applies_to=["speech", "vote", "skill"],
)


# ── 核心函数 ──────────────────────────────────────────────


def get_dimensions_for(
    event_type: str,
    role: str,
    include_outcome: bool = True,
) -> List[EvalDimension]:
    """根据决策类型和角色返回适用的维度列表"""
    dims = []

    # 通用维度
    for d in COMMON_DIMENSIONS:
        if event_type in d.applies_to:
            dims.append(d)

    # 角色专属维度
    role_dims = ROLE_DIMENSIONS.get(role, [])
    for d in role_dims:
        if event_type in d.applies_to:
            dims.append(d)

    # 结果维度
    if include_outcome and event_type in OUTCOME_DIMENSION.applies_to:
        dims.append(OUTCOME_DIMENSION)

    return dims


def get_dimension_weights(
    round: int,
    total_rounds: int,
    event_type: str,
    role: str,
) -> Dict[str, float]:
    """动态维度权重

    前期(game_progress < 0.3)：信息利用权重高
    后期(game_progress > 0.7)：伪装质量/言行一致性权重高
    中期：均衡
    """
    progress = round / max(total_rounds, 1)
    dims = get_dimensions_for(event_type, role, include_outcome=False)
    weights = {}

    for d in dims:
        base_weight = 1.0

        if d.key == "information_utilization":
            # 前期权重高
            if progress < 0.3:
                base_weight = 1.5
            elif progress > 0.7:
                base_weight = 0.7
        elif d.key in ("consistency", "werewolf_deception", "info_concealment"):
            # 后期权重高
            if progress < 0.3:
                base_weight = 0.7
            elif progress > 0.7:
                base_weight = 1.5
        elif d.key == "game_depth":
            # 中期权重高
            if 0.3 <= progress <= 0.7:
                base_weight = 1.3

        weights[d.key] = base_weight

    # 归一化
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    return weights


# ── 博弈深度层级定义 ──────────────────────────────────────

GAME_DEPTH_LEVELS = {
    "L0": {"name": "反应层", "description": "仅根据当前信息做出反应，无推理", "score_range": (0, 20)},
    "L1": {"name": "推理层", "description": "基于线索推理出结论，如'我认为X是间谍，因为...'", "score_range": (21, 40)},
    "L2": {"name": "反逻辑层", "description": "考虑反逻辑可能，如'X可能在假装攻击Y来洗白自己（倒钩）'", "score_range": (41, 60)},
    "L3": {"name": "反反逻辑层", "description": "多层嵌套推理，如'X看起来像倒钩，但可能是在故意表演倒钩'", "score_range": (61, 80)},
    "L4+": {"name": "高阶博弈层", "description": "多层嵌套推理，主动制造信息不对称", "score_range": (81, 100)},
}
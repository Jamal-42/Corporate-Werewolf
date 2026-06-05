# -*- coding: utf-8 -*-
"""间谍深度协作策略 - 自动分配战术角色与协作场景"""
from typing import Dict, List, Optional, Any
import random
from structured_output_cn import SpyStrategyModelCN


# 战术角色定义
TACTICAL_ROLES = {
    "冲锋型": {
        "description": "积极发言带节奏，伪装HR总监制造混乱",
        "priority": 1,  # 最先分配
    },
    "深潜型": {
        "description": "假装好人跟风投票，必要时投出队友换取信任",
        "priority": 2,
    },
    "低调型": {
        "description": "极度低调不发言，靠低存在感苟到最后",
        "priority": 3,
    },
    "煽动型": {
        "description": "不伪装身份但善于质疑引导，制造怀疑链",
        "priority": 4,
    },
}


def assign_tactical_roles(werewolves: List[str]) -> Dict[str, str]:
    """为间谍团队分配战术角色

    根据间谍数量分配角色，保证每种角色至少1人（如果人数足够）
    """
    n = len(werewolves)
    if n == 0:
        return {}

    if n == 1:
        return {werewolves[0]: "深潜型"}

    # 按优先级分配角色
    roles_pool = ["冲锋型", "深潜型"]
    if n >= 3:
        roles_pool.append("低调型")
    if n >= 4:
        roles_pool.append("煽动型")

    # 先确保每种角色有1人
    assignment = {}
    remaining = list(werewolves)
    for role in roles_pool:
        if not remaining:
            break
        wolf = remaining.pop(0)
        assignment[wolf] = role

    # 剩余间谍随机分配
    for wolf in remaining:
        assignment[wolf] = random.choice(roles_pool)

    return assignment


def generate_coordination_plan(
    tactical_roles: Dict[str, str],
    alive_players: List[str],
    round_num: int,
) -> str:
    """生成间谍协作计划"""
    plans = []

    # 统一投票方向：优先淘汰已亮明身份的好人
    identified_good = [p for p in alive_players if p not in tactical_roles]
    if identified_good:
        target = random.choice(identified_good)
        plans.append(f"统一投票方向：{target}")

    # 冲锋型间谍伪装策略
    chargers = [name for name, role in tactical_roles.items() if role == "冲锋型"]
    if chargers and round_num <= 2:
        plans.append(f"{chargers[0]}可考虑伪装HR总监给出虚假背调")

    # 深潜型间谍跟风策略
    divers = [name for name, role in tactical_roles.items() if role == "深潜型"]
    if divers:
        plans.append(f"{divers[0]}跟随公司阵营投票方向建立好人形象")

    return "；".join(plans) if plans else "各自为战，低调行事"

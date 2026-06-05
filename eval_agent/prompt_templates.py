# -*- coding: utf-8 -*-
"""结构化评测Prompt模板

3种Prompt模板（speech/vote/skill），含Few-Shot示例和双视角评测要求。
系统提示由game_knowledge.py提供。
"""
import json
from typing import Dict, List

from eval_agent.context_builder import DecisionContext, GameContext
from eval_agent.dimensions import EvalDimension
from eval_agent.game_knowledge import get_full_system_prompt, get_role_knowledge


# ── Few-Shot示例 ──────────────────────────────────────

FEW_SHOT_EXAMPLE = """## 评测示例

### 示例：间谍倒钩策略的评测
**上下文**：3号（间谍/造谣者）在第2天发言攻击4号（间谍/卷王），声称"4号第1天投票很可疑"
**发言内容**："我觉得4号很可疑，他昨天的投票时机很奇怪，我建议HR总监今晚查一下4号"

**评测结果**：
{
  "dimensions": {
    "推理质量": {"score": 78, "reason": "发言构建了合理的怀疑逻辑（投票时机），但证据链稍显薄弱，未引用具体票数分布"},
    "博弈深度": {"score": 72, "reason": "体现了L2反逻辑层思维——攻击队友建立对立面，但未进一步预判好人可能识破倒钩"},
    "信息利用": {"score": 65, "reason": "利用了投票信息，但未结合死亡顺序做交叉分析"},
    "信息隐藏": {"score": 80, "reason": "未暴露队友关系，攻击力度控制得当，但建议HR总监背调4号可能引出真实背调结果"},
    "言行一致性": {"score": 85, "reason": "发言攻击4号与后续投票方向一致"},
    "伪装质量": {"score": 85, "reason": "有效执行倒钩策略——攻击队友建立对立面，语气自然不显刻意"},
    "结果对齐度": {"score": 75, "reason": "倒钩策略成功可帮助潜伏阵营获胜，但若4号真被投出则潜伏阵营减员"}
  },
  "overall_comment": "3号展示了成熟的倒钩技巧，攻击队友但不显刻意。攻击力度控制得当——太强可能真导致队友出局，太弱则无法建立对立面。",
  "key_insight": "倒钩策略的风险收益平衡把握较好，但需要关注后续是否会被HR总监背调揭穿",
  "decision_tags": {"strategy_used": "倒钩", "risk_level": "中风险", "mistake_type": null, "target_alignment": "队友", "game_impact": "正向推进"}
}"""


# ── 辅助格式化函数 ──────────────────────────────────────


def format_role_map(game_ctx: GameContext, include_actual: bool = True) -> str:
    """格式化角色映射表"""
    lines = []
    for seat, role in sorted(game_ctx.role_map.items()):
        name = game_ctx.seat_to_name.get(seat, "")
        char_info = game_ctx.character_map.get(seat, {})
        title = char_info.get("workplace_title", "")
        personality = char_info.get("personality", "")
        if include_actual:
            lines.append(f"- {seat}({name}/{title}): {role} | 性格: {personality}")
        else:
            lines.append(f"- {seat}({name}/{title}): 性格: {personality}")
    return "\n".join(lines)


def format_prior_history(dc: DecisionContext) -> str:
    """格式化决策前历史"""
    parts = []
    if dc.prior_deaths_summary:
        parts.append(f"死亡时间线: {dc.prior_deaths_summary}")
    if dc.prior_vote_summaries:
        parts.append("投票结果: " + "; ".join(dc.prior_vote_summaries))
    if dc.prior_speech_summaries:
        parts.append("最近发言:")
        for s in dc.prior_speech_summaries:
            parts.append(f"  - {s}")
    return "\n".join(parts) if parts else "暂无历史信息"


def format_outcome(dc: DecisionContext) -> str:
    """格式化决策后结果"""
    parts = []
    if dc.target_actual_role:
        parts.append(f"目标{dc.target}的真实角色: {dc.target_actual_role}")
    if dc.target_died_this_round:
        parts.append(f"目标{dc.target}本轮出局")
    parts.append(f"该玩家阵营是否获胜: {'是' if dc.team_won else '否'}")
    return "\n".join(parts)


def format_dimensions(dimensions: List[EvalDimension]) -> str:
    """格式化评分维度说明"""
    lines = []
    for i, d in enumerate(dimensions, 1):
        lines.append(f"{i}. {d.name}(0-100): {d.description}")
    return "\n".join(lines)


def format_dimension_keys(dimensions: List[EvalDimension]) -> str:
    """格式化维度JSON key列表"""
    keys = [d.name for d in dimensions]
    return json.dumps(keys, ensure_ascii=False)


# ── 三种Prompt模板 ──────────────────────────────────────


def build_speech_eval_prompt(
    dc: DecisionContext,
    game_ctx: GameContext,
    dimensions: List[EvalDimension],
) -> str:
    """构建发言评测Prompt"""
    return _build_base_prompt(dc, game_ctx, dimensions, event_label="白天公开发言")


def build_vote_eval_prompt(
    dc: DecisionContext,
    game_ctx: GameContext,
    dimensions: List[EvalDimension],
) -> str:
    """构建投票评测Prompt"""
    return _build_base_prompt(dc, game_ctx, dimensions, event_label="投票决策")


def build_skill_eval_prompt(
    dc: DecisionContext,
    game_ctx: GameContext,
    dimensions: List[EvalDimension],
) -> str:
    """构建技能评测Prompt"""
    return _build_base_prompt(dc, game_ctx, dimensions, event_label="技能决策")


def _build_base_prompt(
    dc: DecisionContext,
    game_ctx: GameContext,
    dimensions: List[EvalDimension],
    event_label: str,
) -> str:
    """构建完整Prompt（系统提示+用户提示）"""
    # 系统提示
    system_prompt = get_full_system_prompt()
    role_knowledge = get_role_knowledge(dc.role)

    # 用户提示
    user_parts = [
        "## 游戏概况",
        f"- 玩家数: {game_ctx.player_count}，当前第{dc.round}轮",
        f"- 最终结果: {game_ctx.winner or '未知'}",
        f"- 游戏阶段: {dc.game_stage}",
        "",
        "## 角色身份（上帝视角）",
        format_role_map(game_ctx, include_actual=True),
        "",
        "## 当前决策者",
        f"- 玩家: {dc.player}（{game_ctx.seat_to_name.get(dc.player, '')} / {dc.role}）",
        f"- 决策类型: {event_label}",
        f"- 当前存活: {', '.join(dc.alive_at_decision) if dc.alive_at_decision else '未知'}",
    ]

    # 女巫/守卫状态
    if dc.witch_has_antidote is not None:
        user_parts.append(f"- CEO: 留人offer{'有' if dc.witch_has_antidote else '无'}，辞退信{'有' if dc.witch_has_poison else '无'}")
    if dc.last_guarded:
        user_parts.append(f"- 安保主管上夜保护: {dc.last_guarded}")

    user_parts.extend([
        "",
        "## 信息不对称分析",
        f"- 决策者已知: {'; '.join(dc.known_to_player) if dc.known_to_player else '仅公开信息'}",
        f"- 决策者未知（上帝视角）: {'; '.join(dc.unknown_to_player) if dc.unknown_to_player else '无额外信息'}",
        f"- 是否有信息优势: {'是' if dc.info_advantage else '否'}",
    ])

    # 决策前历史
    user_parts.extend([
        "",
        "## 决策前历史",
        format_prior_history(dc),
    ])

    # 被评价的发言/决策内容
    if dc.llm_output_text:
        user_parts.extend([
            "",
            "## 被评价的内容（完整LLM输出）",
            dc.llm_output_text[:3000],  # 截断防溢出
        ])

    if dc.full_output:
        user_parts.extend([
            "",
            "## 结构化输出",
            json.dumps(dc.full_output, ensure_ascii=False, indent=2)[:1500],
        ])

    if dc.suspicion_level is not None:
        user_parts.append(f"\n嫌疑度: {dc.suspicion_level}")

    # 投票专属：投票分布
    if dc.event_type == "vote" and dc.target:
        user_parts.extend([
            "",
            "## 投票信息",
            f"- 投票目标: {dc.target}",
        ])
        if dc.target_actual_role:
            user_parts.append(f"- 目标真实角色: {dc.target_actual_role}")

    # 技能专属
    if dc.event_type == "skill":
        user_parts.extend([
            "",
            "## 技能信息",
            f"- 技能: {dc.action}",
            f"- 目标: {dc.target or '无'}",
        ])
        if dc.key_evidence:
            user_parts.append(f"- 证据: {dc.key_evidence}")

    # 决策后结果
    user_parts.extend([
        "",
        "## 决策后结果（上帝视角）",
        format_outcome(dc),
    ])

    # 评分维度
    user_parts.extend([
        "",
        "## 评分维度",
        format_dimensions(dimensions),
        "",
        "请严格按以下JSON格式回复（不要添加markdown代码块标记）：",
        "{",
        f'  "dimensions": {{',
    ])
    for d in dimensions:
        user_parts.append(f'    "{d.name}": {{"score": 0-100, "reason": "..."}},')
    user_parts.extend([
        "  },",
        '  "overall_comment": "一句话总体评价",',
        '  "key_insight": "最关键的发现或洞察",',
        '  "decision_tags": {',
        '    "strategy_used": "使用的策略名（如倒钩/深潜/冲锋/悍跳等，无则填null）",',
        '    "risk_level": "低风险/中风险/高风险",',
        '    "mistake_type": "错误类型（如信息遗漏/逻辑矛盾/暴露身份/时机错误等，无则填null）",',
        '    "target_alignment": "正确目标/错误目标/无目标",',
        '    "game_impact": "关键转折/正向推进/负向影响/中性"',
        "  }",
        "}",
    ])

    # 组装
    prompt = f"# 系统提示\n\n{system_prompt}\n\n## {dc.role}的专属策略知识\n{role_knowledge}\n\n{FEW_SHOT_EXAMPLE}\n\n---\n\n# 评测任务\n\n" + "\n".join(user_parts)

    return prompt


def build_eval_prompt(
    dc: DecisionContext,
    game_ctx: GameContext,
    dimensions: List[EvalDimension],
) -> str:
    """组装完整Prompt（系统提示+用户提示），根据event_type分发"""
    if dc.event_type == "vote":
        return build_vote_eval_prompt(dc, game_ctx, dimensions)
    elif dc.event_type == "skill":
        return build_skill_eval_prompt(dc, game_ctx, dimensions)
    else:
        return build_speech_eval_prompt(dc, game_ctx, dimensions)
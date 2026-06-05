# -*- coding: utf-8 -*-
"""评分融合与聚合

将LLM评分与规则引擎评分融合，按「角色 × 决策类型 × 游戏阶段」聚合输出评测报告。
"""
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from eval_agent.judge import EvalResult, GameEvalResult

_log = logging.getLogger("werewolf.diag.eval")


@dataclass
class AggregatedScore:
    """单个维度的聚合分数"""
    mean: float = 0.0
    std: float = 0.0
    median: float = 0.0
    ci95: Tuple[float, float] = (0.0, 0.0)
    sample_count: int = 0


@dataclass
class ScoreDiscrepancy:
    """评分分歧标记"""
    dimension: str = ""
    rule_score: float = 0.0
    llm_score: float = 0.0
    gap: float = 0.0
    possible_reasons: List[str] = field(default_factory=list)


@dataclass
class EvalComparisonUnit:
    """评测聚合单元：角色×事件×阶段"""
    role: str = ""
    event_type: str = ""
    game_stage: Optional[str] = None
    sample_count: int = 0
    dimension_scores: Dict[str, AggregatedScore] = field(default_factory=dict)
    strategy_distribution: Dict[str, int] = field(default_factory=dict)
    common_mistakes: List[str] = field(default_factory=list)
    dimension_reasons_sample: Dict[str, List[str]] = field(default_factory=dict)
    games_sampled: List[str] = field(default_factory=list)
    actual_stage: str = ""


def _compute_aggregated(values: List[float]) -> AggregatedScore:
    """计算聚合统计"""
    if not values:
        return AggregatedScore()
    n = len(values)
    mean = sum(values) / n
    if n > 1:
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        std = math.sqrt(variance)
        se = std / math.sqrt(n)
        ci95 = (mean - 1.96 * se, mean + 1.96 * se)
    else:
        std = 0.0
        ci95 = (mean, mean)
    sorted_vals = sorted(values)
    median = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    return AggregatedScore(mean=mean, std=std, median=median, ci95=ci95, sample_count=n)


def detect_discrepancies(
    rule_scores: Dict[str, float],
    llm_scores: Dict[str, float],
    threshold: float = 20,
) -> List[ScoreDiscrepancy]:
    """检测LLM与规则引擎评分分歧"""
    discrepancies = []
    for dim, rule_val in rule_scores.items():
        llm_val = llm_scores.get(dim, 0.0)
        gap = abs(rule_val - llm_val)
        if gap > threshold:
            reasons = []
            if llm_val > rule_val:
                reasons.append("LLM评分偏高，可能考虑了规则引擎未覆盖的博弈深度")
            else:
                reasons.append("LLM评分偏低，可能发现了规则引擎未检测的逻辑矛盾")
            discrepancies.append(ScoreDiscrepancy(
                dimension=dim,
                rule_score=rule_val,
                llm_score=llm_val,
                gap=gap,
                possible_reasons=reasons,
            ))
    return discrepancies


def integrate_scores(
    rule_report: Dict[str, Any],
    llm_result: GameEvalResult,
    config: Any = None,
) -> Dict[str, Any]:
    """将LLM评分与规则引擎评分融合

    融合策略:
    - 规则引擎分数作为基线(0-100)，始终可用
    - LLM评分(0-100)作为校准信号，在可用时加权调整
    - 置信度自适应加权: LLM权重 = 基础权重0.4 × 置信度，规则引擎权重 = 1.0 - LLM权重
    - 融合报告中保留两套原始分数 + 融合分数
    """
    result = dict(rule_report)  # 保留规则引擎的所有字段

    llm_evals = llm_result.results
    if not llm_evals:
        result["llm_judge_scores"] = {"error": "No LLM eval results"}
        return result

    # 构建LLM评分索引: (player, round, event_type) → EvalResult
    llm_index = {}
    for er in llm_evals:
        key = (er.player, er.round, er.event_type)
        llm_index[key] = er

    # 融合评分
    base_llm_weight = 0.4
    fused_scores = []
    for er in llm_evals:
        confidence = er.confidence
        llm_weight = base_llm_weight * confidence
        rule_weight = 1.0 - llm_weight

        # 计算LLM综合分
        llm_avg = 0.0
        if er.dimension_scores:
            llm_avg = sum(er.dimension_scores.values()) / len(er.dimension_scores)

        # 查找对应的规则引擎分数（如果有）
        # 规则引擎分数在rule_report的events中
        rule_score = 0.0
        events = rule_report.get("events", [])
        if isinstance(events, list):
            for ev in events:
                if isinstance(ev, dict):
                    ev_player = ev.get("player", "")
                    ev_round = ev.get("round")
                    if ev_player == er.player and ev_round == er.round:
                        rule_score = float(ev.get("score", 0))
                        break

        fused = llm_weight * llm_avg + rule_weight * rule_score

        fused_entry = {
            "player": er.player,
            "role": er.role,
            "round": er.round,
            "event_type": er.event_type,
            "game_stage": er.game_stage,
            "rule_score": rule_score,
            "llm_scores": er.dimension_scores,
            "dimension_reasons": er.dimension_reasons,
            "llm_avg": llm_avg,
            "llm_confidence": confidence,
            "fused_score": fused,
            "overall_comment": er.overall_comment,
            "key_insight": er.key_insight,
            "decision_tags": {
                "strategy_used": er.decision_tags.strategy_used,
                "risk_level": er.decision_tags.risk_level,
                "mistake_type": er.decision_tags.mistake_type,
                "target_alignment": er.decision_tags.target_alignment,
                "game_impact": er.decision_tags.game_impact,
            },
        }

        # 检测评分分歧
        if rule_score > 0 and er.dimension_scores:
            discrepancies = detect_discrepancies(
                {"综合": rule_score},
                {"综合": llm_avg},
            )
            if discrepancies:
                fused_entry["score_discrepancies"] = [
                    {"dimension": d.dimension, "rule": d.rule_score, "llm": d.llm_score, "gap": d.gap}
                    for d in discrepancies
                ]

        fused_scores.append(fused_entry)

    result["llm_judge_scores"] = fused_scores
    result["llm_aggregate"] = llm_result.aggregate

    return result


def aggregate_results(
    eval_results: List[EvalResult],
    game_ctxs: List[Any] = None,
) -> Dict[str, Any]:
    """按角色×事件×阶段聚合评测结果"""
    # 按(role, event_type, game_stage)分组
    groups: Dict[str, List[EvalResult]] = {}
    for er in eval_results:
        if er.error:
            continue
        # 样本稀疏回退逻辑
        key = _get_comparison_unit_key(er.role, er.event_type, er.game_stage, groups)
        groups.setdefault(key, []).append(er)

    # 计算每组的聚合统计
    units: Dict[str, EvalComparisonUnit] = {}
    for key, ers in groups.items():
        role, et, stage = key.split("|")
        unit = EvalComparisonUnit(
            role=role,
            event_type=et,
            game_stage=stage if stage else None,
            sample_count=len(ers),
        )

        # 按维度聚合分数
        dim_values: Dict[str, List[float]] = {}
        for er in ers:
            for dim, score in er.dimension_scores.items():
                dim_values.setdefault(dim, []).append(score)

        for dim, values in dim_values.items():
            unit.dimension_scores[dim] = _compute_aggregated(values)

        # 策略分布
        strategy_counts: Dict[str, int] = {}
        for er in ers:
            s = er.decision_tags.strategy_used
            if s:
                strategy_counts[s] = strategy_counts.get(s, 0) + 1
        unit.strategy_distribution = strategy_counts

        # 常见错误
        mistakes: Dict[str, int] = {}
        for er in ers:
            m = er.decision_tags.mistake_type
            if m:
                mistakes[m] = mistakes.get(m, 0) + 1
        unit.common_mistakes = sorted(mistakes.keys(), key=lambda x: mistakes[x], reverse=True)[:3]

        # 维度理由样本（取每个维度最具体的3条理由）
        dim_reasons: Dict[str, List[str]] = {}
        for er in ers:
            for dim, reason in er.dimension_reasons.items():
                if reason:
                    dim_reasons.setdefault(dim, []).append(reason)
        # 每个维度取最长的3条（最具体）
        unit.dimension_reasons_sample = {
            dim: sorted(reasons, key=len, reverse=True)[:3]
            for dim, reasons in dim_reasons.items()
        }

        units[key] = unit

    return {
        "comparison_units": {k: {
            "role": u.role,
            "event_type": u.event_type,
            "game_stage": u.game_stage,
            "sample_count": u.sample_count,
            "dimension_scores": {dim: {
                "mean": agg.mean,
                "std": agg.std,
                "median": agg.median,
                "ci95": list(agg.ci95),
                "sample_count": agg.sample_count,
            } for dim, agg in u.dimension_scores.items()},
            "strategy_distribution": u.strategy_distribution,
            "common_mistakes": u.common_mistakes,
            "dimension_reasons_sample": u.dimension_reasons_sample,
        } for k, u in units.items()},
    }


def _get_comparison_unit_key(
    role: str,
    event_type: str,
    game_stage: str,
    existing_groups: Dict[str, List],
    min_samples: int = 3,
) -> str:
    """带回退的评测单元选择

    样本数≥3 → 角色×事件×阶段
    角色×事件≥3 → 角色×事件（全期）
    角色×事件<3 → 角色（全类型全期）
    """
    # 尝试最细粒度
    fine_key = f"{role}|{event_type}|{game_stage}"
    if len(existing_groups.get(fine_key, [])) >= min_samples:
        return fine_key

    # 回退到角色×事件（全期）
    mid_key = f"{role}|{event_type}|"
    return mid_key


def compare_versions(
    agg_v1: Dict[str, Any],
    agg_v2: Dict[str, Any],
) -> Dict[str, Any]:
    """A/B版本对比

    输出两个版本在各评测单元的对比，标记统计显著差异。
    """
    units_v1 = agg_v1.get("comparison_units", {})
    units_v2 = agg_v2.get("comparison_units", {})

    comparison = {}
    for key in units_v1:
        if key not in units_v2:
            continue
        u1 = units_v1[key]
        u2 = units_v2[key]

        dim_diffs = {}
        for dim in u1.get("dimension_scores", {}):
            s1 = u1["dimension_scores"].get(dim, {})
            s2 = u2["dimension_scores"].get(dim, {})
            mean1 = s1.get("mean", 0)
            mean2 = s2.get("mean", 0)
            delta = mean2 - mean1

            # 简化显著性判断：差异 > 2个标准差
            std1 = s1.get("std", 0)
            std2 = s2.get("std", 0)
            pooled_std = math.sqrt((std1 ** 2 + std2 ** 2) / 2) if (std1 + std2) > 0 else 0
            significant = abs(delta) > 2 * pooled_std if pooled_std > 0 else False

            dim_diffs[dim] = {
                "v1_mean": mean1,
                "v2_mean": mean2,
                "delta": delta,
                "significant": significant,
            }

        comparison[key] = {
            "role": u1.get("role", ""),
            "event_type": u1.get("event_type", ""),
            "game_stage": u1.get("game_stage"),
            "dimension_diffs": dim_diffs,
        }

    return comparison
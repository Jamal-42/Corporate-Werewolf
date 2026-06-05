# -*- coding: utf-8 -*-
"""评测结果质量自检

检查LLM评测输出的格式、分数范围、评分-评论一致性、理由具体性。
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("werewolf.diag.eval")


@dataclass
class DecisionTags:
    """决策标签（结构化可查询）"""
    strategy_used: Optional[str] = None
    risk_level: str = "中风险"
    mistake_type: Optional[str] = None
    target_alignment: str = "无目标"
    game_impact: str = "中性"


@dataclass
class EvalResult:
    """单个决策的评测结果"""
    decision_id: int = 0
    player: str = ""
    role: str = ""
    event_type: str = ""
    round: int = 0
    game_stage: str = ""
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    dimension_reasons: Dict[str, str] = field(default_factory=dict)
    overall_comment: str = ""
    key_insight: str = ""
    decision_tags: DecisionTags = field(default_factory=DecisionTags)
    confidence: float = 1.0
    raw_response: str = ""
    error: Optional[str] = None


class EvalQualityChecker:
    """评测质量自检"""

    @staticmethod
    def check_format_compliance(raw_response: str) -> Tuple[bool, str]:
        """检查JSON格式是否合规"""
        text = raw_response.strip()
        # 移除markdown代码块标记
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return False, "JSON格式错误：未找到有效的JSON对象"

        try:
            parsed = json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            return False, f"JSON解析失败: {e}"

        # 检查必要字段
        if "dimensions" not in parsed:
            return False, "缺少dimensions字段"

        dims = parsed["dimensions"]
        if not isinstance(dims, dict) or len(dims) == 0:
            return False, "dimensions为空或格式错误"

        # 检查每个维度是否有score和reason
        for dim_name, dim_data in dims.items():
            if isinstance(dim_data, dict):
                if "score" not in dim_data:
                    return False, f"维度'{dim_name}'缺少score字段"
            elif not isinstance(dim_data, (int, float)):
                return False, f"维度'{dim_name}'格式错误"

        return True, ""

    @staticmethod
    def check_score_range(scores: Dict[str, float]) -> Tuple[bool, List[str]]:
        """检查分数是否在0-100范围内"""
        warnings = []
        for dim, score in scores.items():
            if score < 0 or score > 100:
                warnings.append(f"维度'{dim}'分数{score}超出0-100范围")
        return len(warnings) == 0, warnings

    @staticmethod
    def check_consistency(
        dimension_scores: Dict[str, float],
        overall_comment: str,
    ) -> Tuple[bool, List[str]]:
        """检查评分与评论是否一致"""
        warnings = []
        if not dimension_scores or not overall_comment:
            return True, []

        # 计算平均分
        avg = sum(dimension_scores.values()) / len(dimension_scores)

        # 检查低分（<40）但评论没有批评性词汇
        critical_words = ["问题", "不足", "错误", "矛盾", "遗漏", "暴露", "失败", "风险", "不当"]
        has_critical = any(w in overall_comment for w in critical_words)

        if avg < 40 and not has_critical:
            warnings.append("平均分较低(<40)但评论缺少批评性表述")

        # 检查高分（>80）但评论没有肯定性词汇
        positive_words = ["优秀", "合理", "正确", "有效", "精准", "出色", "恰当", "高质"]
        has_positive = any(w in overall_comment for w in positive_words)

        if avg > 80 and not has_positive:
            warnings.append("平均分较高(>80)但评论缺少肯定性表述")

        return len(warnings) == 0, warnings

    @staticmethod
    def check_reason_specificity(reasons: Dict[str, str]) -> Tuple[bool, List[str]]:
        """检查理由是否具体（避免"表现良好"这种空洞理由）"""
        warnings = []
        # 空洞理由模式
        vague_patterns = [
            r"^表现[好坏]$", r"^决策合理$", r"^策略恰当$",
            r"^推理清晰$", r"^发言有效$",
        ]
        # 具体性指标：引用了玩家号/轮次/事件
        specific_indicators = re.compile(r'\d+号|第\d+轮|第\d+夜|第\d+天|窃取|背调|保护|投票')

        for dim, reason in reasons.items():
            if not reason or len(reason) < 5:
                warnings.append(f"维度'{dim}'理由过于简短")
                continue
            # 检查是否匹配空洞模式
            is_vague = any(re.match(p, reason) for p in vague_patterns)
            if is_vague:
                warnings.append(f"维度'{dim}'理由过于空洞: '{reason}'")
                continue
            # 检查是否引用了具体信息
            if not specific_indicators.search(reason) and len(reason) < 30:
                warnings.append(f"维度'{dim}'理由缺少具体引用（玩家号/轮次/事件）")

        return len(warnings) == 0, warnings

    @classmethod
    def validate(cls, eval_result: EvalResult) -> Tuple[bool, List[str]]:
        """综合校验，返回(是否通过, 警告列表)"""
        all_warnings = []

        # 格式检查
        if eval_result.raw_response:
            fmt_ok, fmt_msg = cls.check_format_compliance(eval_result.raw_response)
            if not fmt_ok:
                all_warnings.append(f"格式问题: {fmt_msg}")

        # 分数范围检查
        range_ok, range_warnings = cls.check_score_range(eval_result.dimension_scores)
        all_warnings.extend(range_warnings)

        # 评分-评论一致性
        cons_ok, cons_warnings = cls.check_consistency(
            eval_result.dimension_scores,
            eval_result.overall_comment,
        )
        all_warnings.extend(cons_warnings)

        # 理由具体性
        spec_ok, spec_warnings = cls.check_reason_specificity(eval_result.dimension_reasons)
        all_warnings.extend(spec_warnings)

        # 如果有error，降低置信度
        if eval_result.error:
            all_warnings.append(f"评测错误: {eval_result.error}")

        passed = len(all_warnings) == 0
        return passed, all_warnings
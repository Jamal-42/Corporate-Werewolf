# -*- coding: utf-8 -*-
"""评测核心逻辑 — EvalJudge

异步并发+信号量控制，3种采样策略，集成quality_checker。
"""
import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentscope.model import ChatModelBase

from eval_agent.config import EvalModelConfig, create_eval_model, resolve_eval_config
from eval_agent.context_builder import DecisionContext, GameContext, build_evaluation_contexts
from eval_agent.dimensions import get_dimensions_for
from eval_agent.prompt_templates import build_eval_prompt
from eval_agent.quality_checker import EvalQualityChecker, EvalResult, DecisionTags

_log = logging.getLogger("werewolf.diag.eval")


@dataclass
class GameEvalResult:
    """一局游戏的评测结果"""
    game_context: GameContext = field(default_factory=GameContext)
    results: List[EvalResult] = field(default_factory=list)
    aggregate: Dict[str, Any] = field(default_factory=dict)


class EvalJudge:
    """评测智能体"""

    def __init__(self, config: EvalModelConfig = None):
        self.config = config or resolve_eval_config()
        self.model: ChatModelBase = create_eval_model(self.config)
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        self._checker = EvalQualityChecker()

    async def judge_decision(
        self,
        decision_ctx: DecisionContext,
        game_ctx: GameContext,
    ) -> EvalResult:
        """对单个决策进行评测"""
        dimensions = get_dimensions_for(
            decision_ctx.event_type,
            decision_ctx.role,
            include_outcome=True,
        )
        prompt = build_eval_prompt(decision_ctx, game_ctx, dimensions)

        async with self._semaphore:
            try:
                response = await self._call_model(prompt)
                result = self._parse_response(response, dimensions, decision_ctx)

                # 质量自检
                passed, warnings = self._checker.validate(result)
                if not passed and warnings:
                    _log.warning(f"Quality check warnings for decision {decision_ctx.event_id}: {warnings}")
                    # 如果分数越界，直接截断
                    for k, v in result.dimension_scores.items():
                        result.dimension_scores[k] = max(0.0, min(100.0, v))
                    result.confidence *= 0.8

                    # 重试1次（仅格式问题）
                    if any("格式" in w or "JSON" in w for w in warnings):
                        _log.info(f"Retrying decision {decision_ctx.event_id} due to format issue")
                        response2 = await self._call_model(prompt)
                        result2 = self._parse_response(response2, dimensions, decision_ctx)
                        passed2, warnings2 = self._checker.validate(result2)
                        if passed2 or len(warnings2) < len(warnings):
                            result = result2

                return result

            except Exception as e:
                _log.error(f"Judge decision failed for {decision_ctx.player} round {decision_ctx.round}: {e}")
                return EvalResult(
                    decision_id=decision_ctx.event_id,
                    player=decision_ctx.player,
                    role=decision_ctx.role,
                    event_type=decision_ctx.event_type,
                    round=decision_ctx.round,
                    game_stage=decision_ctx.game_stage,
                    error=str(e),
                    raw_response="",
                )

    async def judge_game(
        self,
        jsonl_path: str,
        sample_rate: float = None,
        strategy: str = "uniform",
    ) -> GameEvalResult:
        """对一局游戏进行评测"""
        game_ctx, decision_ctxs = build_evaluation_contexts(jsonl_path)

        rate = sample_rate or self.config.sample_rate
        sampled = self._sample(decision_ctxs, rate, strategy)

        _log.info(f"Judging game: {len(decision_ctxs)} decisions, {len(sampled)} sampled (rate={rate}, strategy={strategy})")

        results = await asyncio.gather(*[
            self.judge_decision(dc, game_ctx) for dc in sampled
        ])

        return GameEvalResult(
            game_context=game_ctx,
            results=list(results),
            aggregate=self._aggregate(list(results)),
        )

    async def _call_model(self, prompt: str) -> str:
        """调用评测模型

        agentscope的ChatModelBase.__call__是async def，需要await。
        model()接受list[dict]格式（role/content键），stream=True时返回async generator。
        评测模型统一使用stream=False以简化响应处理。
        """
        # 确保评测模型使用stream=False
        if hasattr(self.model, 'stream') and self.model.stream:
            self.model.stream = False

        messages = [{'role': 'user', 'content': prompt}]
        response = await self.model(messages)

        # ChatResponse.content 是 list[dict]，如 [{'type': 'text', 'text': '...'}]
        content = response.content
        if isinstance(content, list):
            texts = [item.get('text', '') for item in content if isinstance(item, dict)]
            return ''.join(texts)
        return str(content)

    def _parse_response(
        self,
        response: str,
        dimensions: list,
        dc: DecisionContext,
    ) -> EvalResult:
        """解析LLM评测响应"""
        result = EvalResult(
            decision_id=dc.event_id,
            player=dc.player,
            role=dc.role,
            event_type=dc.event_type,
            round=dc.round,
            game_stage=dc.game_stage,
            raw_response=response,
        )

        try:
            # 提取JSON
            text = response.strip()
            # 移除markdown代码块标记
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)

            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(text[start:end + 1])
            else:
                parsed = json.loads(text)

            # 解析维度评分
            dims_data = parsed.get("dimensions", {})
            for d in dimensions:
                dim_data = dims_data.get(d.name, {})
                if isinstance(dim_data, dict):
                    result.dimension_scores[d.name] = float(dim_data.get("score", 0))
                    result.dimension_reasons[d.name] = str(dim_data.get("reason", ""))
                elif isinstance(dim_data, (int, float)):
                    result.dimension_scores[d.name] = float(dim_data)

            result.overall_comment = parsed.get("overall_comment", "")
            result.key_insight = parsed.get("key_insight", "")

            # 解析decision_tags
            tags_data = parsed.get("decision_tags", {})
            if isinstance(tags_data, dict):
                result.decision_tags = DecisionTags(
                    strategy_used=tags_data.get("strategy_used"),
                    risk_level=tags_data.get("risk_level", "中风险"),
                    mistake_type=tags_data.get("mistake_type"),
                    target_alignment=tags_data.get("target_alignment", "无目标"),
                    game_impact=tags_data.get("game_impact", "中性"),
                )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            _log.warning(f"Failed to parse eval response: {e}")
            result.error = f"Parse error: {e}"
            result.confidence = 0.3

        return result

    def _sample(
        self,
        decision_ctxs: List[DecisionContext],
        rate: float,
        strategy: str,
    ) -> List[DecisionContext]:
        """采样决策"""
        if rate >= 1.0:
            return decision_ctxs

        n = max(1, int(len(decision_ctxs) * rate))

        if strategy == "critical_first":
            # 优先采样技能和投票
            skill_vote = [dc for dc in decision_ctxs if dc.event_type in ("skill", "vote")]
            speech = [dc for dc in decision_ctxs if dc.event_type == "speech"]
            # 先从skill/vote取，不足再从speech补
            if len(skill_vote) >= n:
                return random.sample(skill_vote, n)
            else:
                remaining = n - len(skill_vote)
                extra = random.sample(speech, min(remaining, len(speech))) if speech and remaining > 0 else []
                return skill_vote + extra

        elif strategy == "role_balanced":
            # 按角色均匀采样
            by_role: Dict[str, List[DecisionContext]] = {}
            for dc in decision_ctxs:
                by_role.setdefault(dc.role, []).append(dc)
            per_role = max(1, n // max(len(by_role), 1))
            sampled = []
            for role, dcs in by_role.items():
                sampled.extend(random.sample(dcs, min(per_role, len(dcs))))
            return sampled[:n]

        else:  # uniform
            return random.sample(decision_ctxs, min(n, len(decision_ctxs)))

    def _aggregate(self, results: List[EvalResult]) -> Dict[str, Any]:
        """按角色×事件×阶段聚合评测结果"""
        from eval_agent.score_integrator import aggregate_results
        return aggregate_results(results, [])
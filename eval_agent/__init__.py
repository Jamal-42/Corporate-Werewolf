# -*- coding: utf-8 -*-
"""评测智能体 — 独立评测模块

从JSONL中提取丰富的游戏上下文，按角色/动作类型设计差异化评测维度，
最终与规则引擎评分融合。
"""
from eval_agent.judge import EvalJudge
from eval_agent.config import resolve_eval_config, create_eval_model, EvalModelConfig

__all__ = ["EvalJudge", "resolve_eval_config", "create_eval_model", "EvalModelConfig"]


async def evaluate_game_with_llm(
    jsonl_path: str,
    sample_rate: float | None = None,
    sample_strategy: str = "uniform",
    config: EvalModelConfig | None = None,
):
    """便捷入口：对一局游戏进行LLM评测"""
    judge = EvalJudge(config=config)
    return await judge.judge_game(
        jsonl_path=jsonl_path,
        sample_rate=sample_rate,
        strategy=sample_strategy,
    )

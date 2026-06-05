# -*- coding: utf-8 -*-
"""评测智能体 - 独立模型配置

复用 model_config.py 的双后端调度模式，但使用 EVAL_MODEL_* 前缀，
完全独立于游戏Agent。

环境变量：
  EVAL_MODEL_MODEL_NAME    — 评测模型名（默认 qwen-max）
  EVAL_MODEL_API_KEY       — API Key（回退到 DASHSCOPE_API_KEY）
  EVAL_MODEL_BASE_URL      — 设了→OpenAI兼容，未设→百炼（默认空）
  EVAL_MODEL_ENABLE_THINKING — 是否开启思维链（默认 false）
  EVAL_MODEL_GENERATE_KWARGS — 生成参数 JSON（默认 {"temperature":0.3}）
  EVAL_MODEL_MAX_CONCURRENT — 最大并发LLM调用数（默认 3）
  EVAL_MODEL_SAMPLE_RATE   — 默认采样率（默认 1.0）
"""
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from agentscope.model import ChatModelBase, DashScopeChatModel, OpenAIChatModel

from shared.parsing_utils import parse_bool as _parse_bool, parse_json as _parse_json, parse_value as _parse_value


@dataclass
class EvalModelConfig:
    model_name: str = "deepseek-v4-pro"
    api_key: str = ""
    stream: bool = True
    enable_thinking: bool = False
    generate_kwargs: Dict[str, Any] = field(default_factory=lambda: {"temperature": 0.3})
    base_url: Optional[str] = None
    base_http_api_url: Optional[str] = None
    client_args: Optional[Dict[str, Any]] = None
    max_concurrent: int = 3
    sample_rate: float = 1.0


_PREFIX = "EVAL_MODEL_"
_FIELD_SUFFIXES = {
    "model_name": "MODEL_NAME",
    "enable_thinking": "ENABLE_THINKING",
    "generate_kwargs": "GENERATE_KWARGS",
    "api_key": "API_KEY",
    "base_url": "BASE_URL",
}
_SUFFIX_TO_FIELD = {v: k for k, v in _FIELD_SUFFIXES.items()}


def resolve_eval_config() -> EvalModelConfig:
    """从环境变量解析评测模型配置"""
    config = EvalModelConfig(
        api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
    )

    for key, value in os.environ.items():
        if not key.startswith(_PREFIX):
            continue
        suffix = key[len(_PREFIX):]
        field_name = _SUFFIX_TO_FIELD.get(suffix)
        if field_name:
            # 跳过空字符串的 api_key，保留 DASHSCOPE_API_KEY 回退
            if field_name == "api_key" and not value:
                continue
            setattr(config, field_name, _parse_value(field_name, value))

    if not config.api_key:
        config.api_key = os.environ.get("DASHSCOPE_API_KEY", "")

    return config


def create_eval_model(config: EvalModelConfig = None) -> ChatModelBase:
    """根据配置创建评测模型实例

    自动选择后端：
    - 设了 base_url → OpenAIChatModel
    - 未设 base_url → DashScopeChatModel（百炼）
    """
    if config is None:
        config = resolve_eval_config()

    if config.base_url:
        client_args = dict(config.client_args or {})
        client_args.setdefault("base_url", config.base_url)
        return OpenAIChatModel(
            model_name=config.model_name,
            api_key=config.api_key or None,
            stream=config.stream,
            generate_kwargs=config.generate_kwargs if config.generate_kwargs else None,
            client_args=client_args,
        )
    else:
        return DashScopeChatModel(
            model_name=config.model_name,
            api_key=config.api_key,
 stream=config.stream,
            enable_thinking=config.enable_thinking,
            generate_kwargs=config.generate_kwargs if config.generate_kwargs else None,
            base_http_api_url=config.base_http_api_url,
        )
# -*- coding: utf-8 -*-
"""按座位号配置不同模型 - 支持百炼平台和OpenAI兼容接口

优先级：MODEL_SEAT_N_* > MODEL_DEFAULT_* > 硬编码回退(qwen-max + enable_thinking=True)

两种模型后端：
- 百炼平台（默认）：不设 BASE_URL 时自动使用 DashScopeChatModel
- OpenAI兼容接口：设了 BASE_URL 后自动使用 OpenAIChatModel

.env示例：
  # 百炼平台（默认）
  DASHSCOPE_API_KEY=sk-xxx
  MODEL_DEFAULT_MODEL_NAME=qwen-max
  MODEL_DEFAULT_ENABLE_THINKING=true

  # OpenAI兼容接口（设了BASE_URL即切换）
  MODEL_SEAT_1_MODEL_NAME=gpt-4o
  MODEL_SEAT_1_BASE_URL=https://api.openai.com/v1
  MODEL_SEAT_1_API_KEY=sk-xxx

  # 本地部署
  MODEL_SEAT_2_MODEL_NAME=Qwen3-8B
  MODEL_SEAT_2_BASE_URL=http://localhost:8000/v1
  MODEL_SEAT_2_API_KEY=not-needed
"""
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agentscope.model import ChatModelBase, DashScopeChatModel, OpenAIChatModel

from shared.parsing_utils import parse_bool as _parse_bool, parse_json as _parse_json, parse_value as _parse_value


@dataclass
class ModelConfig:
    """单个玩家的模型配置"""
    model_name: str = "deepseek-v4-flash"
    api_key: str = ""
    stream: bool = True
    enable_thinking: bool = True
    generate_kwargs: Dict[str, Any] = field(default_factory=dict)
    base_url: Optional[str] = None
    base_http_api_url: Optional[str] = None
    client_args: Optional[Dict[str, Any]] = None


# 前缀常量
_DEFAULT_PREFIX = "MODEL_DEFAULT_"
_SEAT_PREFIX = "MODEL_SEAT_"

# 字段名 → env键后缀
_FIELD_SUFFIXES = {
    "model_name": "MODEL_NAME",
    "enable_thinking": "ENABLE_THINKING",
    "generate_kwargs": "GENERATE_KWARGS",
    "api_key": "API_KEY",
    "stream": "STREAM",
    "base_url": "BASE_URL",
    "base_http_api_url": "BASE_HTTP_API_URL",
    "client_args": "CLIENT_ARGS",
}

# 后缀 → 字段名（反向映射）
_SUFFIX_TO_FIELD = {v: k for k, v in _FIELD_SUFFIXES.items()}


# 缓存
_env_cache: Optional[tuple] = None


def _scan_env() -> tuple[Dict[str, Any], Dict[int, Dict[str, Any]]]:
    """扫描os.environ中的MODEL_*配置，返回(defaults, seat_configs)"""
    global _env_cache
    if _env_cache is not None:
        return _env_cache

    defaults: Dict[str, Any] = {}
    seat_configs: Dict[int, Dict[str, Any]] = {}

    for key, value in os.environ.items():
        # MODEL_DEFAULT_<FIELD>
        if key.startswith(_DEFAULT_PREFIX):
            suffix = key[len(_DEFAULT_PREFIX):]
            field_name = _SUFFIX_TO_FIELD.get(suffix)
            if field_name:
                defaults[field_name] = _parse_value(field_name, value)
            continue

        # MODEL_SEAT_<N>_<FIELD>
        if key.startswith(_SEAT_PREFIX):
            remainder = key[len(_SEAT_PREFIX):]
            underscore_pos = remainder.find("_")
            if underscore_pos > 0:
                seat_str = remainder[:underscore_pos]
                suffix = remainder[underscore_pos + 1:]
                if seat_str.isdigit():
                    seat_num = int(seat_str)
                    field_name = _SUFFIX_TO_FIELD.get(suffix)
                    if field_name:
                        seat_configs.setdefault(seat_num, {})[field_name] = _parse_value(field_name, value)

    _env_cache = (defaults, seat_configs)
    return defaults, seat_configs


def invalidate_cache() -> None:
    """清除缓存（测试用）"""
    global _env_cache
    _env_cache = None


def resolve_model_config(seat_num: int) -> ModelConfig:
    """解析指定座位号的模型配置

    优先级：座位号配置 > 默认配置 > 硬编码回退

    设了 base_url → OpenAI 兼容接口
    未设 base_url → 百炼平台（DashScopeChatModel）
    """
    defaults, seat_configs = _scan_env()

    config = ModelConfig(
        model_name="deepseek-v4-flash",
        api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
        stream=True,
        enable_thinking=True,
        generate_kwargs={},
    )

    for field_name, value in defaults.items():
        setattr(config, field_name, value)

    seat_override = seat_configs.get(seat_num, {})
    for field_name, value in seat_override.items():
        setattr(config, field_name, value)

    if not config.api_key:
        config.api_key = os.environ.get("DASHSCOPE_API_KEY", "")

    return config


def create_model(seat_num: int) -> ChatModelBase:
    """根据座位号创建模型实例

    自动选择后端：
    - 设了 base_url → OpenAIChatModel（OpenAI兼容接口）
    - 未设 base_url → DashScopeChatModel（百炼平台）
    """
    config = resolve_model_config(seat_num)

    if config.base_url:
        # OpenAI 兼容接口
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
        # 百炼平台
        return DashScopeChatModel(
            model_name=config.model_name,
            api_key=config.api_key,
            stream=config.stream,
            enable_thinking=config.enable_thinking,
            generate_kwargs=config.generate_kwargs if config.generate_kwargs else None,
            base_http_api_url=config.base_http_api_url,
        )


# 向后兼容别名
create_dashscope_model = create_model


def validate_model_configs() -> List[str]:
    """校验模型配置合法性，返回warnings列表"""
    warnings = []
    defaults, seat_configs = _scan_env()

    for seat_num in seat_configs:
        if seat_num < 1 or seat_num > 12:
            warnings.append(f"座位号{seat_num}超出范围(1-12)")

    if "generate_kwargs" in defaults:
        gkw = defaults["generate_kwargs"]
        if not isinstance(gkw, dict):
            warnings.append("MODEL_DEFAULT_GENERATE_KWARGS不是有效的JSON对象")

    for seat_num, cfg in seat_configs.items():
        if "generate_kwargs" in cfg and not isinstance(cfg["generate_kwargs"], dict):
            warnings.append(f"MODEL_SEAT_{seat_num}_GENERATE_KWARGS不是有效的JSON对象")

    return warnings


def get_config_summary() -> str:
    """获取模型配置摘要"""
    defaults, seat_configs = _scan_env()
    lines = []

    default_backend = "OpenAI兼容" if defaults.get("base_url") else "百炼"
    if defaults:
        lines.append(f"  默认({default_backend}): model={defaults.get('model_name', 'deepseek-v4-flash')}, "
                      f"thinking={defaults.get('enable_thinking', True)}")
        if defaults.get("base_url"):
            lines.append(f"    base_url={defaults['base_url']}")

    for seat_num in sorted(seat_configs.keys()):
        cfg = seat_configs[seat_num]
        backend = "OpenAI兼容" if cfg.get("base_url") else "百炼"
        lines.append(f"  {seat_num}号位({backend}): model={cfg.get('model_name', '默认')}, "
                      f"thinking={cfg.get('enable_thinking', '默认')}")
        if cfg.get("base_url"):
            lines.append(f"    base_url={cfg['base_url']}")

    return "\n".join(lines) if lines else "  全部使用默认配置(百炼 deepseek-v4-flash)"

# -*- coding: utf-8 -*-
"""共享模块 — 角色名映射、数据模型、解析工具

集中定义项目内多处重复使用的常量与函数，确保一致性。
"""

from shared.role_mapping import (
    ROLE_ALIASES,
    ROLE_ALIASES_REVERSE,
    ROLE_COLORS,
    VILLAGER_TEAM,
    normalize_role,
    normalize_role_webui,
)
from shared.data_models import DecisionEvent, Finding, ReplayData
from shared.parsing_utils import (
    discover_log_files,
    extract_agent_messages,
    parse_bool,
    parse_json,
    parse_value,
    read_text_auto,
)

__all__ = [
    # role_mapping
    "ROLE_ALIASES",
    "ROLE_ALIASES_REVERSE",
    "ROLE_COLORS",
    "VILLAGER_TEAM",
    "normalize_role",
    "normalize_role_webui",
    # data_models
    "DecisionEvent",
    "Finding",
    "ReplayData",
    # parsing_utils
    "discover_log_files",
    "extract_agent_messages",
    "parse_bool",
    "parse_json",
    "parse_value",
    "read_text_auto",
]

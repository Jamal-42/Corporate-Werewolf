# -*- coding: utf-8 -*-
"""Skills-Agent — 自进化Skills生成与注入

根据评测结果为角色生成阶段化skills指导，支持灵活注入和版本管理。
"""

from skills_agent.generator import SkillsGenerator
from skills_agent.skills_store import SkillsStore

__all__ = ["SkillsGenerator", "SkillsStore"]

# SkillsDispatcher 在 dispatcher.py 创建后自动可用
def __getattr__(name):
    if name == "SkillsDispatcher":
        from skills_agent.dispatcher import SkillsDispatcher
        return SkillsDispatcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

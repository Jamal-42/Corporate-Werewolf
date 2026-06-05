# -*- coding: utf-8 -*-
"""技能注册表 - 动态注册和管理所有游戏技能"""
from typing import Dict, Type, Any, List, Optional
from agentscope.agent import ReActAgent
from skills.base import SkillBase


class SkillRegistry:
    """技能注册表

    管理所有角色的技能实例，提供统一的execute接口。
    main_cn.py各phase方法可调用registry.execute(role, ...)而非直接写技能逻辑。
    """

    _skills: Dict[str, SkillBase] = {}

    def register(self, role: str, skill: SkillBase) -> None:
        """注册一个角色的技能"""
        self._skills[role] = skill

    def get_skill(self, role: str) -> Optional[SkillBase]:
        """获取角色的技能实例"""
        return self._skills.get(role)

    async def execute(self, role: str, agent: ReActAgent,
                      alive_players: List[ReActAgent],
                      game_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """通过角色名执行对应技能"""
        skill = self.get_skill(role)
        if skill is None:
            return None
        return await skill.execute(agent, alive_players, game_state)

    def list_skills(self) -> List[str]:
        """列出所有已注册的角色"""
        return list(self._skills.keys())


def register_skill(role: str):
    """装饰器：自动注册技能类到全局注册表"""
    def decorator(cls: Type[SkillBase]):
        instance = cls()
        _GLOBAL_REGISTRY.register(role, instance)
        return cls
    return decorator


# 全局注册表实例
_GLOBAL_REGISTRY = SkillRegistry()


def get_global_registry() -> SkillRegistry:
    """获取全局注册表"""
    return _GLOBAL_REGISTRY
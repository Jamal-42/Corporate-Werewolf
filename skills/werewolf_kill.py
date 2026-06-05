# -*- coding: utf-8 -*-
"""间谍窃取技能"""
from typing import Any, Dict, List, Optional
from agentscope.agent import ReActAgent
from skills.base import SkillBase
from skills.registry import register_skill
from structured_output_cn import WerewolfKillModelCN, DiscussionModelCN


@register_skill("狼人")
class WerewolfKillSkill(SkillBase):
    role = "狼人"

    async def execute(self, agent: ReActAgent, alive_players: List[ReActAgent],
                      game_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        result = await agent(structured_model=WerewolfKillModelCN)
        return self.parse_result(result)

    def validate_target(self, target: str, alive_players: List[ReActAgent],
                        game_state: Dict[str, Any]) -> bool:
        alive_names = [p.name for p in alive_players]
        return target in alive_names

    def parse_result(self, raw_result: Any) -> Optional[Dict[str, Any]]:
        if raw_result is None or not hasattr(raw_result, 'metadata') or raw_result.metadata is None:
            return None
        meta = raw_result.metadata
        return {
            "target": meta.get("target"),
            "kill_strategy": meta.get("kill_strategy"),
            "team_coordination": meta.get("team_coordination"),
        }

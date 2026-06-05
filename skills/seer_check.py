# -*- coding: utf-8 -*-
"""HR总监背调技能"""
from typing import Any, Dict, List, Optional
from agentscope.agent import ReActAgent
from skills.base import SkillBase
from skills.registry import register_skill
from structured_output_cn import get_seer_model_cn


@register_skill("预言家")
class SeerCheckSkill(SkillBase):
    role = "预言家"

    async def execute(self, agent: ReActAgent, alive_players: List[ReActAgent],
                      game_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger = game_state.get("logger")
        round_num = game_state.get("round_num", 1)
        model_info = game_state.get("model_info", {})
        
        result = await agent(structured_model=get_seer_model_cn(alive_players))
        parsed = self.parse_result(result)
        
        if logger and hasattr(logger, 'save_prompt') and parsed:
            response_content = self._format_response(
                action_type="seer_check",
                target=parsed.get("target", ""),
                reason=parsed.get("check_reason", ""),
                extra={"priority_level": parsed.get("priority_level", 5)}
            )
            self._save_prompt_log(agent, logger, round_num, "seer", model_info, response_content)
        
        return parsed

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
            "check_reason": meta.get("check_reason"),
            "priority_level": meta.get("priority_level"),
        }
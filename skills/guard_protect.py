# -*- coding: utf-8 -*-
"""安保主管加密保护技能"""
from typing import Any, Dict, List, Optional
from agentscope.agent import ReActAgent
from skills.base import SkillBase
from skills.registry import register_skill
from structured_output_cn import get_guard_model_cn


@register_skill("守护者")
class GuardProtectSkill(SkillBase):
    role = "守护者"

    async def execute(self, agent: ReActAgent, alive_players: List[ReActAgent],
                      game_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger = game_state.get("logger")
        round_num = game_state.get("round_num", 1)
        model_info = game_state.get("model_info", {})
        
        last_guarded = game_state.get("last_guarded")
        guardable = [p for p in alive_players if p.name != last_guarded]
        if not guardable:
            return None
        
        result = await agent(structured_model=get_guard_model_cn(guardable))
        parsed = self.parse_result(result)
        
        if logger and hasattr(logger, 'save_prompt') and parsed:
            response_content = self._format_response(
                action_type="guard_protect",
                target=parsed.get("target", ""),
                reason=parsed.get("guard_reason", "")
            )
            self._save_prompt_log(agent, logger, round_num, "guard", model_info, response_content)
        
        return parsed

    def validate_target(self, target: str, alive_players: List[ReActAgent],
                        game_state: Dict[str, Any]) -> bool:
        alive_names = [p.name for p in alive_players]
        last_guarded = game_state.get("last_guarded")
        return target in alive_names and target != last_guarded

    def parse_result(self, raw_result: Any) -> Optional[Dict[str, Any]]:
        if raw_result is None or not hasattr(raw_result, 'metadata') or raw_result.metadata is None:
            return None
        meta = raw_result.metadata
        return {
            "target": meta.get("target"),
            "guard_reason": meta.get("guard_reason"),
        }
# -*- coding: utf-8 -*-
"""法务总监诉讼技能"""
from typing import Any, Dict, List, Optional
from agentscope.agent import ReActAgent
from skills.base import SkillBase
from skills.registry import register_skill
from structured_output_cn import get_hunter_model_cn


@register_skill("猎人")
class HunterShootSkill(SkillBase):
    role = "猎人"

    async def execute(self, agent: ReActAgent, alive_players: List[ReActAgent],
                      game_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger = game_state.get("logger")
        round_num = game_state.get("round_num", 1)
        model_info = game_state.get("model_info", {})
        dead_player = game_state.get("dead_player", "")

        # 排除已出局的猎人自身
        valid_targets = [p for p in alive_players if p.name != dead_player]

        result = await agent(structured_model=get_hunter_model_cn(valid_targets))
        parsed = self.parse_result(result)

        if logger and hasattr(logger, 'save_prompt') and parsed:
            response_content = self._format_response(
                action_type="hunter_shoot",
                target=parsed.get("target", ""),
                reason=parsed.get("shoot_reason", parsed.get("hunter_reason", "")),
                extra={"shoot": parsed.get("shoot", True)}
            )
            self._save_prompt_log(agent, logger, round_num, "hunter", model_info, response_content)

        return parsed

    def validate_target(self, target: str, alive_players: List[ReActAgent],
                        game_state: Dict[str, Any]) -> bool:
        dead_player = game_state.get("dead_player", "")
        alive_names = [p.name for p in alive_players if p.name != dead_player]
        return target in alive_names

    def parse_result(self, raw_result: Any) -> Optional[Dict[str, Any]]:
        if raw_result is None or not hasattr(raw_result, 'metadata') or raw_result.metadata is None:
            return None
        meta = raw_result.metadata
        return {
            "target": meta.get("target"),
            "shoot_reason": meta.get("shoot_reason") or meta.get("hunter_reason"),
            "shoot": meta.get("shoot", True),
        }

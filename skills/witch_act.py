# -*- coding: utf-8 -*-
"""CEO决策技能"""
from typing import Any, Dict, List, Optional
from agentscope.agent import ReActAgent
from skills.base import SkillBase
from skills.registry import register_skill
from structured_output_cn import WitchActionModelCN
import json


@register_skill("女巫")
class WitchActSkill(SkillBase):
    role = "女巫"

    async def execute(self, agent: ReActAgent, alive_players: List[ReActAgent],
                      game_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger = game_state.get("logger")
        round_num = game_state.get("round_num", 1)
        model_info = game_state.get("model_info", {})
        
        result = await agent(structured_model=WitchActionModelCN)
        parsed = self.parse_result(result)
        
        if logger and hasattr(logger, 'save_prompt') and parsed:
            response_content = json.dumps({
                "input": {
                    "use_antidote": parsed.get("use_antidote", False),
                    "use_poison": parsed.get("use_poison", False),
                    "target_name": parsed.get("target_name", ""),
                    "witch_reason": parsed.get("witch_reason", "")
                }
            }, ensure_ascii=False)
            self._save_prompt_log(agent, logger, round_num, "witch", model_info, response_content)
        
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
            "use_antidote": meta.get("use_antidote", False),
            "use_poison": meta.get("use_poison", False),
            "target_name": meta.get("target_name"),
            "witch_reason": meta.get("witch_reason"),
        }
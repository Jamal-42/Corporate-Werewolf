# -*- coding: utf-8 -*-
"""技能基类 - 所有游戏技能的抽象基类"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from agentscope.agent import ReActAgent
import json

from shared.parsing_utils import extract_agent_messages


class SkillBase(ABC):
    """技能抽象基类

    每个技能需要实现：
    - execute: 执行技能逻辑
    - validate_target: 校验目标合法性
    - parse_result: 解析LLM输出结果
    """

    role: str = ""

    def _save_prompt_log(self, agent: ReActAgent, logger: Optional[Any], 
                         round_num: int, phase: str, model_info: Dict = None,
                         response_content: str = None) -> None:
        """保存prompt日志的通用方法
        
        Args:
            agent: 执行技能的Agent
            logger: CombinedLogger实例
            round_num: 当前轮次
            phase: 当前阶段
            model_info: 模型信息字典
            response_content: Agent的响应内容（tool_use格式）
        """
        if not logger or not hasattr(logger, 'save_prompt'):
            return

        messages = extract_agent_messages(agent)

        if response_content:
            messages.append({
                "role": "assistant",
                "content": response_content
            })
        
        try:
            logger.save_prompt(
                messages=messages,
                round_num=round_num,
                phase=phase,
                seat=agent.name,
                model_name=model_info.get("model_name", "unknown") if model_info else "unknown",
            )
        except Exception:
            pass

    def _format_response(self, action_type: str, target: str, reason: str, extra: Dict = None) -> str:
        """格式化响应内容为tool_use格式"""
        input_data = {"target": target}
        if reason:
            input_data["reason"] = reason
        if extra:
            input_data.update(extra)
        
        return json.dumps({
            "input": input_data
        }, ensure_ascii=False)

    @abstractmethod
    async def execute(self, agent: ReActAgent, alive_players: List[ReActAgent],
                      game_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """执行技能，返回技能结果dict或None"""
        pass

    @abstractmethod
    def validate_target(self, target: str, alive_players: List[ReActAgent],
                        game_state: Dict[str, Any]) -> bool:
        """校验目标是否合法（在存活列表内、满足规则约束等）"""
        pass

    @abstractmethod
    def parse_result(self, raw_result: Any) -> Optional[Dict[str, Any]]:
        """解析LLM输出为结构化结果"""
        pass
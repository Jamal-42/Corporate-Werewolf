# -*- coding: utf-8 -*-
"""上下文窗口管理器 - 自动截断Agent记忆，防止context溢出

作为必备功能集成到游戏循环中，每轮结束后自动检查并截断所有Agent的记忆：
- 保留最近N条消息
- 关键事件（死亡/背调结果/身份声明/投票结果）压缩为摘要注入记忆
- 超出窗口时，非关键消息按FIFO淘汰
"""
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from agentscope.message import Msg


@dataclass
class KeyEvent:
    """不可截断的关键事件"""
    round_num: int
    event_type: str  # death, seer_result, identity_claim, vote_result
    content: str


class ContextManager:
    """上下文窗口管理器

    核心功能：
    1. 记录关键游戏事件（死亡/背调/身份声明/投票）
    2. 截断Agent的InMemoryMemory，保留最近N条消息
    3. 截断前将关键事件压缩为摘要注入Agent记忆
    """

    CRITICAL_TYPES = {"death", "seer_result", "identity_claim", "vote_result"}
    
    PUBLIC_TYPES = {"death", "identity_claim", "vote_result"}

    # 事件类型→中文标签
    EVENT_LABELS = {
        "death": "离职",
        "seer_result": "背调结果",
        "identity_claim": "身份声明",
        "vote_result": "投票结果",
    }

    def __init__(self, max_messages: int = 80):
        self.max_messages = max_messages
        self.key_events: List[KeyEvent] = []
        self._log = logging.getLogger("werewolf.diag.context")

    def add_key_event(self, round_num: int, event_type: str, content: str) -> None:
        """记录关键事件（不会被截断，会压缩为摘要注入Agent记忆）"""
        if event_type in self.CRITICAL_TYPES:
            self.key_events.append(KeyEvent(
                round_num=round_num,
                event_type=event_type,
                content=content,
            ))

    def get_key_events_summary(self) -> str:
        """获取关键事件摘要文本
        
        只返回公开类型的事件（不含背调结果）
        背调结果(seer_result)属于HR总监私密信息，不应注入所有玩家记忆
        """
        if not self.key_events:
            return ""

        parts = ["【关键信息摘要】"]
        for evt in self.key_events:
            if evt.event_type not in self.PUBLIC_TYPES:
                continue
            label = self.EVENT_LABELS.get(evt.event_type, evt.event_type)
            parts.append(f"  第{evt.round_num}轮 {label}：{evt.content}")
        return "\n".join(parts)

    def should_truncate(self, agent) -> bool:
        """检查Agent记忆是否需要截断"""
        if not hasattr(agent, 'memory') or not hasattr(agent.memory, 'content'):
            return False
        return len(agent.memory.content) > self.max_messages

    def truncate_agent(self, agent) -> bool:
        """截断单个Agent的记忆

        策略：
        1. 先检查是否超出窗口
        2. 注入关键事件摘要（如果有关键事件且还没注入过）
        3. 保留最近max_messages条消息
        4. 返回是否执行了截断
        """
        if not hasattr(agent, 'memory') or not hasattr(agent.memory, 'content'):
            return False

        memory = agent.memory
        msg_count = len(memory.content)

        if msg_count <= self.max_messages:
            return False

        # 注入关键事件摘要
        summary = self.get_key_events_summary()
        if summary:
            summary_msg = Msg(
                name="系统",
                content=summary,
                role="system",
            )
            memory.content.append(summary_msg)

        # 截断：保留最后max_messages条（注入的摘要也在其中）
        memory.content = memory.content[-self.max_messages:]

        self._log.info(f"[{agent.name}] 记忆截断：{msg_count}→{len(memory.content)}条")
        return True

    def truncate_all_agents(self, agents: list) -> int:
        """截断所有超出窗口的Agent记忆，返回截断的Agent数量

        真人玩家（_is_human=True）不截断，因为真人自行管理记忆。
        """
        truncated = 0
        for agent in agents:
            if getattr(agent, '_is_human', False):
                continue  # 跳过真人玩家
            if self.should_truncate(agent):
                if self.truncate_agent(agent):
                    truncated += 1
        return truncated

    def clear(self) -> None:
        """清空关键事件记录"""
        self.key_events.clear()

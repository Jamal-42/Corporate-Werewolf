# -*- coding: utf-8 -*-
"""上下文窗口管理测试 - Agent记忆截断与关键事件保留"""
import pytest
from unittest.mock import MagicMock

from context_manager import ContextManager, KeyEvent


class MockMemory:
    """模拟AgentScope的InMemoryMemory"""
    def __init__(self, messages=None):
        self.content = list(messages or [])


class MockAgent:
    """模拟ReActAgent"""
    def __init__(self, name, messages=None):
        self.name = name
        self.memory = MockMemory(messages)


def make_msg(name="test", content="hello", role="assistant"):
    """创建Mock Msg对象"""
    msg = MagicMock()
    msg.name = name
    msg.content = content
    msg.role = role
    return msg


class TestKeyEventRecording:
    """关键事件记录"""

    def test_add_key_event(self):
        cm = ContextManager(max_messages=50)
        cm.add_key_event(1, "death", "张三被间谍窃取离职")
        assert len(cm.key_events) == 1
        assert cm.key_events[0].round_num == 1
        assert cm.key_events[0].event_type == "death"
        assert cm.key_events[0].content == "张三被间谍窃取离职"

    def test_ignores_non_critical_type(self):
        cm = ContextManager()
        cm.add_key_event(1, "chat", "普通聊天")
        assert len(cm.key_events) == 0

    def test_all_critical_types(self):
        cm = ContextManager()
        cm.add_key_event(1, "death", "离职")
        cm.add_key_event(1, "seer_result", "背调结果")
        cm.add_key_event(2, "identity_claim", "身份声明")
        cm.add_key_event(2, "vote_result", "投票结果")
        assert len(cm.key_events) == 4


class TestKeyEventsSummary:
    """关键事件摘要"""

    def test_empty_summary(self):
        cm = ContextManager()
        assert cm.get_key_events_summary() == ""

    def test_summary_format(self):
        cm = ContextManager()
        cm.add_key_event(1, "death", "张三离职")
        cm.add_key_event(2, "vote_result", "李四被投出")
        summary = cm.get_key_events_summary()
        assert "【关键信息摘要】" in summary
        assert "第1轮 离职" in summary
        assert "张三离职" in summary
        assert "第2轮 投票结果" in summary
        assert "李四被投出" in summary


class TestShouldTruncate:
    """截断判断"""

    def test_no_memory_attribute(self):
        cm = ContextManager()
        agent = MagicMock(spec=[])
        assert cm.should_truncate(agent) is False

    def test_within_limit(self):
        cm = ContextManager(max_messages=10)
        agent = MockAgent("test", [make_msg() for _ in range(5)])
        assert cm.should_truncate(agent) is False

    def test_exceeds_limit(self):
        cm = ContextManager(max_messages=10)
        agent = MockAgent("test", [make_msg() for _ in range(15)])
        assert cm.should_truncate(agent) is True

    def test_at_limit(self):
        cm = ContextManager(max_messages=10)
        agent = MockAgent("test", [make_msg() for _ in range(10)])
        assert cm.should_truncate(agent) is False


class TestTruncateAgent:
    """单个Agent截断"""

    def test_no_truncate_when_within_limit(self):
        cm = ContextManager(max_messages=20)
        msgs = [make_msg() for _ in range(10)]
        agent = MockAgent("test", msgs)
        result = cm.truncate_agent(agent)
        assert result is False
        assert len(agent.memory.content) == 10

    def test_truncate_reduces_messages(self):
        cm = ContextManager(max_messages=10)
        msgs = [make_msg(content=f"msg_{i}") for i in range(20)]
        agent = MockAgent("test", msgs)
        result = cm.truncate_agent(agent)
        assert result is True
        assert len(agent.memory.content) == 10

    def test_truncate_keeps_recent_messages(self):
        cm = ContextManager(max_messages=5)
        msgs = [make_msg(content=f"msg_{i}") for i in range(10)]
        agent = MockAgent("test", msgs)
        cm.truncate_agent(agent)
        # 保留最后5条（无关键事件摘要时）
        contents = [m.content for m in agent.memory.content]
        assert "msg_5" in contents
        assert "msg_9" in contents
        assert "msg_0" not in contents

    def test_truncate_injects_key_events_summary(self):
        cm = ContextManager(max_messages=5)
        cm.add_key_event(1, "death", "张三离职")
        cm.add_key_event(2, "vote_result", "李四被投出")
        msgs = [make_msg(content=f"msg_{i}") for i in range(10)]
        agent = MockAgent("test", msgs)
        cm.truncate_agent(agent)
        # 应该包含摘要消息
        summary_msgs = [m for m in agent.memory.content if m.content and "关键信息摘要" in str(m.content)]
        assert len(summary_msgs) > 0

    def test_truncate_no_summary_without_key_events(self):
        cm = ContextManager(max_messages=5)
        msgs = [make_msg(content=f"msg_{i}") for i in range(10)]
        agent = MockAgent("test", msgs)
        cm.truncate_agent(agent)
        # 无关键事件，不注入摘要
        assert len(agent.memory.content) == 5


class TestTruncateAllAgents:
    """批量截断"""

    def test_truncate_multiple_agents(self):
        cm = ContextManager(max_messages=5)
        agents = [
            MockAgent("a", [make_msg() for _ in range(10)]),
            MockAgent("b", [make_msg() for _ in range(3)]),
            MockAgent("c", [make_msg() for _ in range(8)]),
        ]
        truncated = cm.truncate_all_agents(agents)
        assert truncated == 2  # a和c被截断
        assert len(agents[0].memory.content) == 5
        assert len(agents[1].memory.content) == 3
        assert len(agents[2].memory.content) == 5

    def test_no_agents_need_truncation(self):
        cm = ContextManager(max_messages=20)
        agents = [
            MockAgent("a", [make_msg() for _ in range(5)]),
            MockAgent("b", [make_msg() for _ in range(3)]),
        ]
        truncated = cm.truncate_all_agents(agents)
        assert truncated == 0


class TestClear:
    """清空关键事件"""

    def test_clear(self):
        cm = ContextManager()
        cm.add_key_event(1, "death", "离职")
        cm.add_key_event(2, "vote_result", "投票")
        cm.clear()
        assert len(cm.key_events) == 0
        assert cm.get_key_events_summary() == ""
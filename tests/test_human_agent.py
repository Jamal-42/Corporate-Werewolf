# -*- coding: utf-8 -*-
"""HumanAgent 单元测试"""
import asyncio
import pytest
from unittest.mock import patch
from agentscope.message import Msg
from agentscope.memory import InMemoryMemory

from human_agent import HumanAgent


def _make_agent(seat_num=3) -> HumanAgent:
    return HumanAgent(name=f"{seat_num}号", sys_prompt="你是预言家", seat_num=seat_num)


def _run(coro):
    """在同步测试中运行异步协程"""
    return asyncio.get_event_loop().run_until_complete(coro)


# ═════════════════════════════════════════════════════════
#  基本属性
# ═════════════════════════════════════════════════════════

class TestHumanAgentBasics:
    def test_attributes(self):
        agent = _make_agent(3)
        assert agent.name == "3号"
        assert agent._sys_prompt == "你是预言家"
        assert agent.seat_num == 3
        assert agent._is_human is True
        assert isinstance(agent.memory, InMemoryMemory)

    def test_memory_initially_empty(self):
        agent = _make_agent()
        assert len(agent.memory.content) == 0


# ═════════════════════════════════════════════════════════
#  observe — 存入 memory + 打印 content
# ═════════════════════════════════════════════════════════

class TestObserve:
    def test_observe_stores_in_memory(self):
        agent = _make_agent()
        msg = Msg(name="游戏主持人", content="天黑请闭眼", role="system")
        _run(agent.observe(msg))
        assert len(agent.memory.content) == 1
        assert agent.memory.content[0].content == "天黑请闭眼"

    def test_observe_list_of_msgs(self):
        agent = _make_agent()
        msgs = [
            Msg(name="游戏主持人", content="公告1", role="system"),
            Msg(name="2号", content="我发言1", role="assistant"),
        ]
        _run(agent.observe(msgs))
        assert len(agent.memory.content) == 2

    def test_observe_none(self):
        agent = _make_agent()
        _run(agent.observe(None))
        assert len(agent.memory.content) == 0

    def test_observe_does_not_print_metadata(self, capsys):
        """observe 只打印 content，不打印 metadata"""
        agent = _make_agent()
        msg = Msg(name="2号", content="我投票给5号", role="assistant",
                  metadata={"vote": "5号", "reason": "可疑", "suspicion_level": 8})
        _run(agent.observe(msg))
        output = capsys.readouterr().out
        assert "5号" in output
        # reason 在 metadata 中，不应打印
        assert "可疑" not in output
        assert "suspicion_level" not in output

    def test_observe_skips_own_assistant_msg(self, capsys):
        """不重复打印自己刚发的消息"""
        agent = _make_agent()
        msg = Msg(name="3号", content="我说的话", role="assistant")
        _run(agent.observe(msg))
        output = capsys.readouterr().out
        assert "我说的话" not in output


# ═════════════════════════════════════════════════════════
#  reply — 自由发言
# ═════════════════════════════════════════════════════════

class TestFreeReply:
    def test_free_reply_returns_msg(self):
        agent = _make_agent()
        with patch('builtins.input', return_value="我觉得2号很可疑"):
            result = _run(agent.reply())
        assert isinstance(result, Msg)
        assert result.name == "3号"
        assert result.content == "我觉得2号很可疑"
        assert result.role == "assistant"
        assert result.metadata is None

    def test_free_reply_empty_input(self):
        """空输入返回默认文本"""
        agent = _make_agent()
        with patch('builtins.input', return_value=""):
            result = _run(agent.reply())
        assert result.content == "（沉默）"

    def test_reply_with_msg_stores_in_memory(self):
        agent = _make_agent()
        prompt_msg = Msg(name="游戏主持人", content="请发言", role="system")
        with patch('builtins.input', return_value="我的发言"):
            result = _run(agent.reply(msg=prompt_msg))
        assert len(agent.memory.content) >= 1


# ═════════════════════════════════════════════════════════
#  reply — 结构化输入
# ═════════════════════════════════════════════════════════

class TestStructuredReply:
    def test_structured_reply_with_vote_model(self):
        """测试投票结构化输入"""
        from structured_output_cn import get_vote_model_cn

        agent = _make_agent()
        alive = [agent, HumanAgent(name="5号", sys_prompt="", seat_num=5)]
        vote_model = get_vote_model_cn(alive)

        # 模拟用户输入：选择投票目标 + 理由 + 怀疑等级
        inputs = iter(["5号", "行为可疑", "7"])
        with patch('builtins.input', side_effect=inputs):
            result = _run(agent.reply(structured_model=vote_model))

        assert isinstance(result, Msg)
        assert result.name == "3号"
        assert result.role == "assistant"
        assert result.metadata is not None
        assert result.metadata.get("vote") == "5号"
        assert result.metadata.get("reason") == "行为可疑"

    def test_structured_reply_with_witch_model(self):
        """测试女巫结构化输入"""
        from structured_output_cn import WitchActionModelCN

        agent = _make_agent()
        # use_antidote(y), use_poison(n), action_reason, target_name
        inputs = iter(["y", "n", "救人", ""])
        with patch('builtins.input', side_effect=inputs):
            result = _run(agent.reply(structured_model=WitchActionModelCN))

        assert result.metadata is not None
        assert result.metadata["use_antidote"] is True
        assert result.metadata["use_poison"] is False

    def test_structured_literal_number_selection(self):
        """测试编号选择（输入数字而非名称）"""
        from structured_output_cn import get_vote_model_cn

        agent = _make_agent()
        other = HumanAgent(name="5号", sys_prompt="", seat_num=5)
        vote_model = get_vote_model_cn([agent, other])

        # 输入编号 "2" 选择第二个选项
        inputs = iter(["2", "测试", "5"])
        with patch('builtins.input', side_effect=inputs):
            result = _run(agent.reply(structured_model=vote_model))

        assert result.metadata is not None
        assert result.metadata.get("vote") is not None


# ═════════════════════════════════════════════════════════
#  get_literal_choices 辅助函数
# ═════════════════════════════════════════════════════════

class TestGetLiteralChoices:
    def test_with_vote_model(self):
        from structured_output_cn import get_vote_model_cn, get_literal_choices

        alive = [HumanAgent(name="1号", sys_prompt="", seat_num=1),
                 HumanAgent(name="3号", sys_prompt="", seat_num=3)]
        vote_model = get_vote_model_cn(alive)
        choices = get_literal_choices(vote_model, "vote")
        assert "1号" in choices
        assert "3号" in choices

    def test_with_non_literal_field(self):
        from structured_output_cn import WitchActionModelCN, get_literal_choices

        choices = get_literal_choices(WitchActionModelCN, "use_antidote")
        assert choices == []

    def test_with_missing_field(self):
        from structured_output_cn import WitchActionModelCN, get_literal_choices

        choices = get_literal_choices(WitchActionModelCN, "nonexistent_field")
        assert choices == []


# ═════════════════════════════════════════════════════════
#  信息隔离
# ═════════════════════════════════════════════════════════

class TestInformationIsolation:
    def test_observe_only_shows_content_not_metadata(self, capsys):
        """核心安全测试：observe 绝不打印 metadata"""
        agent = _make_agent()

        # 模拟一个 AI 玩家的投票结果（含敏感 metadata）
        vote_msg = Msg(
            name="2号",
            content="我投票淘汰5号",
            role="assistant",
            metadata={"vote": "5号", "reason": "因为我查验了5号", "suspicion_level": 9}
        )
        _run(agent.observe(vote_msg))
        output = capsys.readouterr().out

        # content 应该可见
        assert "5号" in output
        # metadata 中的推理不应可见
        assert "因为我查验了5号" not in output
        assert "suspicion_level" not in output

    def test_private_seer_result_visible_to_self(self, capsys):
        """预言家查验结果只发给本人，observe 应显示"""
        agent = _make_agent()
        seer_msg = Msg(
            name="游戏主持人",
            content="背调结果：5号是清白员工",
            role="system",
        )
        _run(agent.observe(seer_msg))
        output = capsys.readouterr().out
        assert "背调结果" in output
        assert "清白员工" in output


# ═════════════════════════════════════════════════════════
#  ContextManager 兼容性
# ═════════════════════════════════════════════════════════

class TestContextManagerCompat:
    def test_skip_human_agent(self):
        from context_manager import ContextManager

        agent = _make_agent()
        for i in range(100):
            agent.memory.content.append(Msg(name="test", content=f"msg {i}", role="assistant"))

        cm = ContextManager(max_messages=20)
        truncated = cm.truncate_all_agents([agent])
        assert truncated == 0
        assert len(agent.memory.content) == 100

    def test_ai_agent_still_truncated(self):
        from context_manager import ContextManager

        class FakeAIAgent:
            name = "1号"
            memory = InMemoryMemory()

        agent = FakeAIAgent()
        for i in range(100):
            agent.memory.content.append(Msg(name="test", content=f"msg {i}", role="assistant"))

        cm = ContextManager(max_messages=20)
        truncated = cm.truncate_all_agents([agent])
        assert truncated == 1


# ═════════════════════════════════════════════════════════
#  HumanAgent 类型提取辅助
# ═════════════════════════════════════════════════════════

class TestTypeExtraction:
    def test_extract_literal_choices(self):
        from typing import Literal

        class TestModel:
            model_fields = {
                "target": type("F", (), {
                    "__origin__": Literal,
                    "__args__": ("1号", "3号", "5号"),
                }),
            }

        agent = _make_agent()
        choices = agent._extract_literal_choices(TestModel.model_fields["target"])
        assert choices == ["1号", "3号", "5号"]

    def test_is_bool_type(self):
        agent = _make_agent()
        assert agent._is_bool_type(bool) is True
        assert agent._is_bool_type(str) is False

    def test_is_int_type(self):
        agent = _make_agent()
        assert agent._is_int_type(int) is True
        assert agent._is_int_type(str) is False

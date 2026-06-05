# -*- coding: utf-8 -*-
"""JSONL解析器测试 — 验证 parse_log_jsonl 和 parse_game_log_jsonl"""
import json
import tempfile
import pytest
from pathlib import Path

from jsonl_parser import (
    parse_log_jsonl,
    parse_game_log_jsonl,
    DecisionEvent,
    ReplayData,
)


def _write_jsonl(events: list[dict], path: Path) -> None:
    """将事件列表写入 .jsonl 文件"""
    with open(path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _make_game_init() -> dict:
    return {
        "event_type": "game_init",
        "timestamp": "2026-01-01T00:00:00",
        "player_count": 6,
        "prompt_version": "v2",
        "model_name": "qwen-max",
        "character_role_map": [
            {"character_name": "PUA总裁", "role": "狼人", "seat_num": 1},
            {"character_name": "逻辑怪", "role": "预言家", "seat_num": 2},
            {"character_name": "知心姐", "role": "女巫", "seat_num": 3},
            {"character_name": "暴躁哥", "role": "猎人", "seat_num": 4},
            {"character_name": "铁头哥", "role": "村民", "seat_num": 5},
            {"character_name": "老油条", "role": "村民", "seat_num": 6},
        ],
    }


class TestParseLogJsonl:
    def test_game_init_extracts_roles(self):
        events = [_make_game_init()]
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        _write_jsonl(events, path)

        roles, player_order, decision_events = parse_log_jsonl(path)
        assert roles["1号"] == "狼人"
        assert roles["2号"] == "预言家"
        assert roles["3号"] == "女巫"
        assert "1号" in player_order
        path.unlink()

    def test_decision_event(self):
        events = [
            _make_game_init(),
            {
                "event_type": "decision",
                "timestamp": "2026-01-01T00:01:00",
                "round": 1,
                "phase": "werewolf",
                "player": "1号",
                "role": "狼人",
                "action": "间谍窃取",
                "target": "5号",
                "reasoning_steps": None,
                "key_evidence": None,
                "full_output": None,
            },
        ]
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        _write_jsonl(events, path)

        roles, player_order, decision_events = parse_log_jsonl(path)
        assert len(decision_events) == 1
        assert decision_events[0].player == "1号"
        assert decision_events[0].action == "间谍窃取"
        assert decision_events[0].target == "5号"
        path.unlink()

    def test_vote_result_event(self):
        events = [
            _make_game_init(),
            {
                "event_type": "vote_result",
                "timestamp": "2026-01-01T00:02:00",
                "round": 1,
                "votes": {"1号": "6号", "2号": "5号"},
                "voted_out": "5号",
                "vote_count": 3,
            },
        ]
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        _write_jsonl(events, path)

        roles, player_order, decision_events = parse_log_jsonl(path)
        assert len(decision_events) == 2  # 两个投票者
        vote_events = [e for e in decision_events if e.category == "vote"]
        assert len(vote_events) == 2
        assert vote_events[0].player == "1号"
        assert vote_events[0].target == "6号"
        path.unlink()

    def test_skill_resolution_event(self):
        events = [
            _make_game_init(),
            {
                "event_type": "skill_resolution",
                "timestamp": "2026-01-01T00:01:00",
                "round": 1,
                "skill_type": "spy_steal",
                "source_player": "间谍团队",
                "target_player": "5号",
                "result": "窃取成功",
                "rule_applied": None,
            },
        ]
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        _write_jsonl(events, path)

        roles, player_order, decision_events = parse_log_jsonl(path)
        assert len(decision_events) == 1
        assert decision_events[0].action == "间谍窃取"
        assert decision_events[0].target == "5号"
        path.unlink()

    def test_death_event(self):
        events = [
            _make_game_init(),
            {
                "event_type": "death",
                "timestamp": "2026-01-01T00:01:00",
                "round": 1,
                "player": "5号",
                "cause": "间谍窃取",
            },
        ]
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        _write_jsonl(events, path)

        roles, player_order, decision_events = parse_log_jsonl(path)
        assert len(decision_events) == 1
        assert decision_events[0].player == "5号"
        assert decision_events[0].action == "死亡"
        path.unlink()

    def test_model_call_event(self):
        events = [
            _make_game_init(),
            {
                "event_type": "model_call",
                "timestamp": "2026-01-01T00:01:00",
                "player": "1号",
                "role": "狼人",
                "phase": "werewolf",
                "model_name": "qwen-max",
                "prompt_version": "v2",
                "input_tokens": 100,
                "output_tokens": 50,
                "latency_ms": 200.0,
            },
        ]
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        _write_jsonl(events, path)

        roles, player_order, decision_events = parse_log_jsonl(path)
        assert len(decision_events) == 1
        assert decision_events[0].action == "模型调用"
        assert decision_events[0].metadata["model_name"] == "qwen-max"
        assert decision_events[0].metadata["input_tokens"] == 100
        path.unlink()

    def test_empty_jsonl(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        _write_jsonl([], path)

        roles, player_order, decision_events = parse_log_jsonl(path)
        assert roles == {}
        assert player_order == []
        assert decision_events == []
        path.unlink()


class TestParseGameLogJsonl:
    def test_full_game_replay(self):
        events = [
            _make_game_init(),
            {"event_type": "night_start", "timestamp": "2026-01-01T00:01:00", "round": 1},
            {
                "event_type": "skill_resolution",
                "timestamp": "2026-01-01T00:02:00",
                "round": 1,
                "skill_type": "spy_steal",
                "source_player": "间谍团队",
                "target_player": "5号",
                "result": "窃取目标5号",
            },
            {"event_type": "death", "timestamp": "2026-01-01T00:03:00", "round": 1, "player": "5号", "cause": "间谍窃取"},
            {"event_type": "day_start", "timestamp": "2026-01-01T00:04:00", "round": 1},
            {
                "event_type": "vote_result",
                "timestamp": "2026-01-01T00:05:00",
                "round": 1,
                "votes": {"1号": "6号"},
                "voted_out": "6号",
                "vote_count": 3,
            },
            {"event_type": "game_over", "timestamp": "2026-01-01T00:06:00", "winner": "间谍阵营胜利", "total_rounds": 1},
        ]
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        _write_jsonl(events, path)

        replay = parse_game_log_jsonl(path)
        assert isinstance(replay, ReplayData)
        assert len(replay.players) == 6
        assert replay.players[0]["name"] == "1号"
        assert replay.players[0]["role"] == "商业间谍"

        # 检查事件类型序列
        event_types = [e["type"] for e in replay.events]
        assert "setup" in event_types
        assert "phase" in event_types
        assert "attack" in event_types
        assert "death" in event_types
        assert "vote" in event_types
        assert "ending" in event_types

        # 验证5号被标记为死亡
        dead_player = next(p for p in replay.events[-1]["players"] if p["name"] == "5号")
        assert dead_player["alive"] is False

        path.unlink()

    def test_event_dict_format(self):
        """验证事件dict包含web_ui前端所需的所有字段"""
        events = [
            _make_game_init(),
            {"event_type": "night_start", "timestamp": "2026-01-01T00:01:00", "round": 1},
        ]
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        _write_jsonl(events, path)

        replay = parse_game_log_jsonl(path)
        for event in replay.events:
            required_keys = {"id", "type", "text", "speaker", "round", "phase",
                           "focus_players", "actor", "actor_role", "target", "players"}
            assert required_keys.issubset(event.keys())
        path.unlink()

    def test_guard_protection_event(self):
        events = [
            _make_game_init(),
            {
                "event_type": "skill_resolution",
                "timestamp": "2026-01-01T00:02:00",
                "round": 1,
                "skill_type": "guard_protect",
                "source_player": "5号",
                "target_player": "2号",
                "result": "加密保护成功",
            },
        ]
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        _write_jsonl(events, path)

        replay = parse_game_log_jsonl(path)
        guard_events = [e for e in replay.events if e["type"] == "save"]
        assert len(guard_events) == 1
        assert guard_events[0]["actor_role"] == "守护者"
        assert guard_events[0]["target"] == "2号"
        path.unlink()
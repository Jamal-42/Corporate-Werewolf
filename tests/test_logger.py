# -*- coding: utf-8 -*-
"""JSONL日志完整性测试"""
import json
import pytest
import tempfile
from pathlib import Path
from game_logger import JSONGameLogger


class TestJSONGameLogger:
    def test_log_game_init(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name
        logger = JSONGameLogger(path)

        character_role_map = [
            {
                "character_name": "PUA总裁",
                "role": "狼人",
                "workplace_title": "VP·战略副总裁",
                "personality": "城府极深",
                "speaking_style": "慢条斯理",
                "game_strategy": "控场",
            }
        ]
        logger.log_game_init(player_count=12, character_role_map=character_role_map)
        logger.close()

        with open(path, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f]

        assert len(events) == 1
        assert events[0]["event_type"] == "game_init"
        assert events[0]["player_count"] == 12
        assert events[0]["character_role_map"][0]["character_name"] == "PUA总裁"
        assert events[0]["character_role_map"][0]["role"] == "狼人"
        Path(path).unlink()

    def test_log_death(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name
        logger = JSONGameLogger(path)
        logger.log_death(round_num=1, player="卷王", cause="间谍窃取", seat="7号")
        logger.close()

        with open(path, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f]

        assert events[0]["event_type"] == "death"
        assert events[0]["player"] == "卷王"
        assert events[0]["cause"] == "间谍窃取"
        assert events[0]["seat"] == "7号"
        Path(path).unlink()

    def test_log_game_over(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name
        logger = JSONGameLogger(path)
        logger.log_game_over(
            winner="公司阵营胜利！所有间谍已被清除！",
            total_rounds=5,
            survivors=[{"name": "逻辑怪", "seat": "2号", "role": "预言家"}],
        )
        logger.close()

        with open(path, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f]

        assert events[0]["event_type"] == "game_over"
        assert events[0]["winner"] == "公司阵营胜利！所有间谍已被清除！"
        Path(path).unlink()

    def test_log_skill_resolution(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name
        logger = JSONGameLogger(path)
        logger.log_skill_resolution(
            round_num=1, skill_type="spy_steal",
            source_player="间谍团队", target_player="卷王",
            result="窃取成功",
            rule_applied="被加密保护抵消",
            source_seat=None, target_seat="7号",
        )
        logger.close()

        with open(path, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f]

        assert events[0]["event_type"] == "skill_resolution"
        assert events[0]["rule_applied"] == "被加密保护抵消"
        Path(path).unlink()

    def test_multiple_events(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name
        logger = JSONGameLogger(path)
        logger.log_night_start(round_num=1)
        logger.log_death(round_num=1, player="卷王", cause="间谍窃取", seat="7号")
        logger.log_day_start(round_num=1)
        logger.log_game_over(winner="公司阵营", total_rounds=3, survivors=[])
        logger.close()

        with open(path, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f]

        assert len(events) == 4
        assert events[0]["event_type"] == "night_start"
        assert events[1]["event_type"] == "death"
        assert events[2]["event_type"] == "day_start"
        assert events[3]["event_type"] == "game_over"
        Path(path).unlink()

    def test_log_model_call(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name
        logger = JSONGameLogger(path)
        logger.log_model_call(
            player="PUA总裁",
            role="狼人",
            phase="werewolf",
            model_name="qwen-max",
            prompt_version="v2",
            input_tokens=100,
            output_tokens=50,
            latency_ms=200.0,
            seat="1号",
        )
        logger.close()

        with open(path, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f]

        assert len(events) == 1
        assert events[0]["event_type"] == "model_call"
        assert events[0]["player"] == "PUA总裁"
        assert events[0]["role"] == "狼人"
        assert events[0]["phase"] == "werewolf"
        assert events[0]["model_name"] == "qwen-max"
        assert events[0]["input_tokens"] == 100
        assert events[0]["output_tokens"] == 50
        assert events[0]["seat"] == "1号"
        Path(path).unlink()

    def test_log_decision(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name
        logger = JSONGameLogger(path)
        logger.log_decision(
            round_num=1,
            phase="werewolf",
            player="PUA总裁",
            role="狼人",
            action="间谍窃取",
            target="铁头哥",
            reasoning_steps=["铁头哥发言可疑", "投票方向不明"],
            key_evidence="铁头哥第1轮投了逻辑怪",
            full_output={"target": "铁头哥", "kill_strategy": "先排除可疑者"},
        )
        logger.close()

        with open(path, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f]

        assert len(events) == 1
        assert events[0]["event_type"] == "decision"
        assert events[0]["player"] == "PUA总裁"
        assert events[0]["action"] == "间谍窃取"
        assert events[0]["target"] == "铁头哥"
        assert len(events[0]["reasoning_steps"]) == 2
        assert events[0]["key_evidence"] == "铁头哥第1轮投了逻辑怪"
        Path(path).unlink()

    def test_log_vote_result(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name
        logger = JSONGameLogger(path)
        logger.log_vote_result(
            round_num=1,
            votes={"1号": "5号", "2号": "6号", "3号": "5号"},
            voted_out="5号",
            vote_count=2,
            seat_votes={"1号": "5号", "2号": "6号", "3号": "5号"},
        )
        logger.close()

        with open(path, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f]

        assert len(events) == 1
        assert events[0]["event_type"] == "vote_result"
        assert events[0]["votes"]["1号"] == "5号"
        assert events[0]["voted_out"] == "5号"
        assert events[0]["vote_count"] == 2
        assert events[0]["seat_votes"]["1号"] == "5号"
        Path(path).unlink()

    def test_log_model_call_optional_fields(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            path = f.name
        logger = JSONGameLogger(path)
        logger.log_model_call(
            player="逻辑怪",
            role="预言家",
            phase="seer",
            model_name="qwen-plus",
            prompt_version="v2",
        )
        logger.close()

        with open(path, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f]

        assert events[0]["input_tokens"] is None
        assert events[0]["output_tokens"] is None
        assert events[0]["latency_ms"] is None
        Path(path).unlink()
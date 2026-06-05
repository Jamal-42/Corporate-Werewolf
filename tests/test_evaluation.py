# -*- coding: utf-8 -*-
"""评测逻辑测试"""
import pytest
from evaluation_cn import (
    evaluate_log,
    demo_bad_case_log,
    detect_category,
    parse_log_text,
    score_speech,
    score_vote,
    score_skill,
)
from shared.role_mapping import normalize_role
from shared.data_models import DecisionEvent
from collections import Counter


class TestNormalizeRole:
    def test_alias_mapping(self):
        assert normalize_role("间谍") == "狼人"
        assert normalize_role("HR总监") == "预言家"
        assert normalize_role("CEO") == "女巫"
        assert normalize_role("法务总监") == "猎人"
        assert normalize_role("安保主管") == "守护者"

    def test_unmapped_role_unchanged(self):
        assert normalize_role("村民") == "村民"
        assert normalize_role("预言家") == "预言家"


class TestDetectCategory:
    def test_vote_detection(self):
        result = detect_category({"vote": "张三", "reason": "可疑"})
        assert result[0] == "vote"

    def test_werewolf_kill_detection(self):
        result = detect_category({"target": "张三", "kill_strategy": "策略"})
        assert result[0] == "skill"
        assert "间谍" in result[1] or "窃取" in result[1]

    def test_seer_check_detection(self):
        result = detect_category({"target": "张三", "check_reason": "可疑"})
        assert result[0] == "skill"

    def test_discussion_detection(self):
        result = detect_category({"reach_agreement": False, "key_evidence": "证据"})
        assert result[0] == "speech"


class TestDemoBadCase:
    def test_demo_generates_report(self):
        report = evaluate_log(text=demo_bad_case_log())
        assert "summary" in report
        assert "leaderboard" in report
        assert "findings" in report

    def test_demo_has_high_severity_findings(self):
        report = evaluate_log(text=demo_bad_case_log())
        assert report["summary"]["high_severity_mistakes"] > 0

    def test_demo_uses_seat_numbers(self):
        log = demo_bad_case_log()
        assert "1号" in log
        assert "2号" in log

# -*- coding: utf-8 -*-
"""胜负判定测试"""
import pytest
from unittest.mock import MagicMock
from utils_cn import check_winning_cn


def make_agent(name: str) -> MagicMock:
    agent = MagicMock()
    agent.name = name
    return agent


class TestWinningConditions:
    def test_company_wins_when_all_werewolves_dead(self):
        agents = [make_agent("A"), make_agent("B")]
        roles = {"A": "村民", "B": "预言家"}
        result = check_winning_cn(agents, roles)
        assert result is not None
        assert "公司" in result

    def test_spy_wins_when_equal_to_good(self):
        agents = [make_agent("A"), make_agent("B")]
        roles = {"A": "狼人", "B": "村民"}
        result = check_winning_cn(agents, roles)
        assert result is not None
        assert "间谍" in result

    def test_spy_wins_when_more_than_good(self):
        agents = [make_agent("A"), make_agent("B"), make_agent("C")]
        roles = {"A": "狼人", "B": "狼人", "C": "村民"}
        result = check_winning_cn(agents, roles)
        assert result is not None
        assert "间谍" in result

    def test_game_continues_when_good_majority(self):
        agents = [make_agent("A"), make_agent("B"), make_agent("C")]
        roles = {"A": "狼人", "B": "村民", "C": "预言家"}
        result = check_winning_cn(agents, roles)
        assert result is None

    def test_spy_wins_with_single_werewolf_single_villager(self):
        agents = [make_agent("A"), make_agent("B")]
        roles = {"A": "狼人", "B": "猎人"}
        result = check_winning_cn(agents, roles)
        assert result is not None
        assert "间谍" in result

# -*- coding: utf-8 -*-
"""投票与平票测试"""
import pytest
from utils_cn import majority_vote_cn


class TestMajorityVote:
    def test_simple_majority(self):
        votes = {"A": "X", "B": "X", "C": "Y"}
        result, count = majority_vote_cn(votes)
        assert result == "X"
        assert count == 2

    def test_tie_results_in_no_elimination(self):
        votes = {"A": "X", "B": "Y"}
        result, count = majority_vote_cn(votes)
        assert result == "平票无人出局"

    def test_none_votes_filtered(self):
        votes = {"A": "X", "B": None, "C": ""}
        result, count = majority_vote_cn(votes)
        assert result == "X"
        assert count == 1

    def test_all_none_votes(self):
        votes = {"A": None, "B": None}
        result, count = majority_vote_cn(votes)
        assert result == "无人"

    def test_empty_votes(self):
        result, count = majority_vote_cn({})
        assert result == "无人"

    def test_three_way_tie(self):
        votes = {"A": "X", "B": "Y", "C": "Z"}
        result, count = majority_vote_cn(votes)
        assert result == "平票无人出局"

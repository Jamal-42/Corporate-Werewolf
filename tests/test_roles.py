# -*- coding: utf-8 -*-
"""角色配置测试"""
import pytest
from game_roles import GameRoles


class TestRoleSetup:
    def test_6_player_setup(self):
        setup = GameRoles.get_standard_setup(6)
        assert len(setup) == 6
        assert setup.count("狼人") == 2
        assert "预言家" in setup
        assert "女巫" in setup
        assert setup.count("村民") == 2

    def test_9_player_setup(self):
        setup = GameRoles.get_standard_setup(9)
        assert len(setup) == 9
        assert setup.count("狼人") == 3
        assert "预言家" in setup
        assert "女巫" in setup
        assert "猎人" in setup
        assert setup.count("村民") == 3

    def test_12_player_setup(self):
        setup = GameRoles.get_standard_setup(12)
        assert len(setup) == 12
        assert setup.count("狼人") == 4
        assert setup.count("预言家") == 1
        assert setup.count("女巫") == 1
        assert setup.count("猎人") == 1
        assert setup.count("守护者") == 1
        assert setup.count("村民") == 4

    def test_12_player_role_balance(self):
        setup = GameRoles.get_standard_setup(12)
        good_specials = [r for r in setup if r in ("预言家", "女巫", "猎人", "守护者")]
        assert len(good_specials) == 4  # 4神牌
        assert setup.count("狼人") == 4  # 4间谍
        assert setup.count("村民") == 4  # 4普通员工

    def test_all_characters_count(self):
        characters = GameRoles.get_all_characters()
        assert len(characters) == 12  # 12个人设

    def test_is_werewolf(self):
        assert GameRoles.is_werewolf("狼人") is True
        assert GameRoles.is_werewolf("预言家") is False
        assert GameRoles.is_werewolf("村民") is False

    def test_is_villager_team(self):
        assert GameRoles.is_villager_team("预言家") is True
        assert GameRoles.is_villager_team("女巫") is True
        assert GameRoles.is_villager_team("狼人") is False
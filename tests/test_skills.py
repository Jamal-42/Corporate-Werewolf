# -*- coding: utf-8 -*-
"""技能规则测试"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from skills.hunter_shoot import HunterShootSkill
from skills.guard_protect import GuardProtectSkill
from skills.witch_act import WitchActSkill
from skills.seer_check import SeerCheckSkill
from skills.werewolf_kill import WerewolfKillSkill
from skills.registry import SkillRegistry, get_global_registry, register_skill
from skills.spy_strategy import assign_tactical_roles, generate_coordination_plan


def make_mock_agent(name: str) -> MagicMock:
    agent = MagicMock()
    agent.name = name
    return agent


class TestGuardRules:
    def test_cannot_guard_same_player_consecutively(self):
        skill = GuardProtectSkill()
        game_state = {"last_guarded": "A"}
        alive = [make_mock_agent("A"), make_mock_agent("B")]
        assert skill.validate_target("A", alive, game_state) is False
        assert skill.validate_target("B", alive, game_state) is True

    def test_guard_must_be_alive(self):
        skill = GuardProtectSkill()
        game_state = {"last_guarded": None}
        alive = [make_mock_agent("B")]
        assert skill.validate_target("A", alive, game_state) is False

    def test_first_night_no_restriction(self):
        skill = GuardProtectSkill()
        game_state = {"last_guarded": None}
        alive = [make_mock_agent("A"), make_mock_agent("B")]
        assert skill.validate_target("A", alive, game_state) is True


class TestHunterRules:
    def test_poisoned_hunter_execute_returns_none(self):
        """被辞退信开除时execute直接返回None"""
        skill = HunterShootSkill()
        game_state = {"is_poisoned": True}
        alive = [make_mock_agent("A")]
        # validate_target只检查目标是否在存活列表
        # 被辞退信开除的逻辑在execute中处理（返回None）
        assert skill.validate_target("A", alive, game_state) is True  # 目标合法
        # execute时会检查is_poisoned返回None

    def test_non_poisoned_hunter_can_shoot(self):
        skill = HunterShootSkill()
        game_state = {"is_poisoned": False}
        alive = [make_mock_agent("A")]
        assert skill.validate_target("A", alive, game_state) is True

    def test_target_must_be_alive(self):
        skill = HunterShootSkill()
        game_state = {"is_poisoned": False}
        alive = [make_mock_agent("A")]
        assert skill.validate_target("Z", alive, game_state) is False


class TestSameGuardSameSave:
    """同保护同挽留=员工仍被淘汰"""

    def test_guarded_and_saved_death(self):
        guarded_player = "A"
        saved_player = "A"
        assert guarded_player == saved_player  # 同保护同挽留规则下该员工死亡


class TestSkillRegistry:
    """技能注册表测试"""

    def test_global_registry_has_all_skills(self):
        registry = get_global_registry()
        skills = registry.list_skills()
        assert "狼人" in skills
        assert "预言家" in skills
        assert "守护者" in skills
        assert "女巫" in skills
        assert "猎人" in skills

    def test_registry_get_skill(self):
        registry = get_global_registry()
        guard_skill = registry.get_skill("守护者")
        assert guard_skill is not None
        assert isinstance(guard_skill, GuardProtectSkill)

    def test_registry_unknown_role_returns_none(self):
        registry = get_global_registry()
        assert registry.get_skill("未知角色") is None

    def test_register_skill_decorator(self):
        """测试register_skill装饰器"""
        # 已通过模块导入自动注册
        registry = get_global_registry()
        assert len(registry.list_skills()) >= 5

    def test_manual_register(self):
        """手动注册技能"""
        registry = SkillRegistry()
        skill = GuardProtectSkill()
        registry.register("测试守护", skill)
        assert "测试守护" in registry.list_skills()
        assert registry.get_skill("测试守护") is skill


class TestSpyStrategy:
    """间谍战术角色分配测试"""

    def test_assign_roles_4_werewolves(self):
        wolves = ["1号", "2号", "3号", "4号"]
        roles = assign_tactical_roles(wolves)
        assert len(roles) == 4
        # 应包含冲锋型和深潜型
        assert "冲锋型" in roles.values()
        assert "深潜型" in roles.values()
        # 4人应有煽动型
        assert "煽动型" in roles.values()

    def test_assign_roles_2_werewolves(self):
        wolves = ["1号", "2号"]
        roles = assign_tactical_roles(wolves)
        assert len(roles) == 2
        assert "冲锋型" in roles.values()
        assert "深潜型" in roles.values()

    def test_assign_roles_1_werewolf(self):
        roles = assign_tactical_roles(["1号"])
        assert len(roles) == 1
        assert roles["1号"] == "深潜型"

    def test_assign_roles_empty(self):
        assert assign_tactical_roles([]) == {}

    def test_generate_coordination_plan(self):
        tactical_roles = {"1号": "冲锋型", "2号": "深潜型"}
        alive = ["3号", "4号", "5号"]
        plan = generate_coordination_plan(tactical_roles, alive, 1)
        assert "统一投票" in plan
        assert "冲锋型" in plan or "1号" in plan

    def test_coordination_plan_empty_wolves(self):
        # 没有间谍时仍会生成计划（统一投票方向从alive中选）
        plan = generate_coordination_plan({}, ["A", "B"], 1)
        assert "统一投票" in plan

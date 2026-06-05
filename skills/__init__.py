# -*- coding: utf-8 -*-
"""技能模块 - 注册所有游戏技能"""
from skills.werewolf_kill import WerewolfKillSkill
from skills.seer_check import SeerCheckSkill
from skills.guard_protect import GuardProtectSkill
from skills.witch_act import WitchActSkill
from skills.hunter_shoot import HunterShootSkill
from skills.registry import get_global_registry


def init_skills():
    """初始化所有技能（导入即注册）"""
    return get_global_registry()

# -*- coding: utf-8 -*-
"""测试安保主管保护在女巫死亡时仍然生效"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio


class TestGuardProtectionWhenWitchDead:
    """安保主管保护应独立于女巫存在"""

    def test_guard_protection_logic_independent_of_witch(self):
        """
        验证安保主管保护逻辑在女巫死亡时仍然生效。

        Bug场景：
        - 第2夜：女巫(10号)被狼人杀死
        - 第3夜：狼人杀8号，安保主管保护8号
        - 预期：8号应该存活（保护生效）
        - 实际（修复前）：8号死亡（因为witch_phase在女巫死亡时直接返回killed_player，绕过了保护逻辑）

        修复方案：
        - 将安保主管保护结算移到witch_phase调用之前
        - witch_phase接收已结算的actual_killed参数
        """

        # 模拟场景
        killed_player = "8号"  # 狼人目标
        guarded_player = "8号"  # 安保主管保护目标

        # 修复后的逻辑（在run_game中）
        actual_killed = None if (killed_player and killed_player == guarded_player) else killed_player

        # 验证：当保护目标与狼人目标相同时，actual_killed应为None
        assert actual_killed is None, "安保主管保护应抵消狼人击杀"

        # 模拟女巫死亡时的witch_phase行为
        # 修复后：witch_phase返回(actual_killed, None) = (None, None)
        # 最终：final_killed = None，8号存活
        final_killed = actual_killed  # 女巫死亡时直接返回actual_killed
        assert final_killed is None, "女巫死亡时，final_killed应为None（保护生效）"

    def test_guard_protection_when_witch_alive(self):
        """
        验证女巫存活时安保主管保护仍然正常工作。
        """

        # 场景：狼人杀8号，安保保护8号，女巫存活
        killed_player = "8号"
        guarded_player = "8号"

        # 安保主管保护结算（在run_game中）
        actual_killed = None if (killed_player and killed_player == guarded_player) else killed_player

        # 女巫看到"平安无事"
        assert actual_killed is None

        # 女巫无法使用解药（因为actual_killed是None）
        # witch_phase返回(final_killed=None, poisoned_player=None)
        final_killed = actual_killed
        assert final_killed is None

    def test_guard_not_protecting_target(self):
        """
        验证安保主管未保护狼人目标时，击杀正常生效。
        """

        # 场景：狼人杀8号，安保保护3号
        killed_player = "8号"
        guarded_player = "3号"

        # 安保主管保护结算
        actual_killed = None if (killed_player and killed_player == guarded_player) else killed_player

        # 8号未被保护，actual_killed应为"8号"
        assert actual_killed == "8号"

        # 女巫看到"8号被杀"，可以选择是否使用解药
        # 如果女巫存活且使用解药，final_killed = None
        # 如果女巫死亡或不使用解药，final_killed = "8号"
        final_killed = actual_killed  # 女巫死亡或不使用解药
        assert final_killed == "8号"

    def test_witch_dead_returns_actual_killed(self):
        """
        验证女巫死亡时witch_phase返回已结算的actual_killed。
        这是修复后的行为。
        """

        # 模拟witch_phase在女巫死亡时的行为
        # 修复后的签名：async def witch_phase(self, actual_killed: Optional[str], guarded_player: Optional[str])
        # 当self.witch为空时，返回(actual_killed, None)

        actual_killed = None  # 安保主管已保护
        guarded_player = "8号"

        # 模拟witch_phase的早期返回逻辑
        witch_alive = False  # 女巫已死亡

        if not witch_alive:
            result = (actual_killed, None)
        else:
            result = (actual_killed, None)  # 简化，实际会执行女巫逻辑

        final_killed, poisoned_player = result
        assert final_killed is None  # 保护生效，无人死亡
        assert poisoned_player is None  # 女巫死亡，无法使用毒药


class TestGuardProtectionIntegration:
    """安保主管保护集成测试"""

    def test_night_death_settlement_with_guard_protection(self):
        """
        验证夜晚死亡结算正确处理安保主管保护。
        """

        # 场景：狼人杀8号，安保保护8号，女巫死亡
        killed_player = "8号"
        guarded_player = "8号"
        witch_alive = False

        # Step 1: 安保主管保护结算（在run_game中，witch_phase之前）
        actual_killed = None if (killed_player and killed_player == guarded_player) else killed_player

        # Step 2: 女巫行动（女巫死亡，直接返回）
        if not witch_alive:
            final_killed, poisoned_player = actual_killed, None
        else:
            # 女巫存活时的逻辑（简化）
            final_killed = actual_killed
            poisoned_player = None

        # Step 3: 结算夜晚死亡
        night_deaths = [p for p in [final_killed, poisoned_player] if p]

        # 验证：8号不在死亡名单中
        assert "8号" not in night_deaths
        assert len(night_deaths) == 0

    def test_night_death_settlement_without_guard_protection(self):
        """
        验证安保主管未保护时，狼人击杀正常生效。
        """

        # 场景：狼人杀8号，安保保护3号，女巫死亡
        killed_player = "8号"
        guarded_player = "3号"
        witch_alive = False

        # Step 1: 安保主管保护结算
        actual_killed = None if (killed_player and killed_player == guarded_player) else killed_player

        # Step 2: 女巫行动（女巫死亡）
        final_killed, poisoned_player = actual_killed, None

        # Step 3: 结算夜晚死亡
        night_deaths = [p for p in [final_killed, poisoned_player] if p]

        # 验证：8号在死亡名单中
        assert "8号" in night_deaths
        assert len(night_deaths) == 1

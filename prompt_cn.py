# -*- coding: utf-8 -*-
"""职场狼人杀中文提示词管理 - 支持版本化加载"""
from pathlib import Path
from game_roles import GameRoles


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

ROLE_TO_FILE = {
    "狼人": "werewolf",
    "预言家": "seer",
    "女巫": "witch",
    "猎人": "hunter",
    "守护者": "guard",
    "村民": "villager",
}

# 当前最新版本
DEFAULT_VERSION = "v2"


class PromptManager:
    """版本化提示词管理器"""

    def __init__(self, version: str = DEFAULT_VERSION):
        self.version = version
        self._cache: dict[str, str] = {}

    def _load_prompt(self, role: str) -> str:
        """从文件加载角色提示词"""
        file_key = ROLE_TO_FILE.get(role, "villager")
        prompt_path = PROMPTS_DIR / self.version / f"{file_key}.txt"

        if not prompt_path.exists():
            # 回退到默认版本
            fallback = PROMPTS_DIR / DEFAULT_VERSION / f"{file_key}.txt"
            if fallback.exists():
                prompt_path = fallback
            else:
                return f"[错误：找不到 {role} 的提示词文件]"

        return prompt_path.read_text(encoding="utf-8")

    def get_role_prompt(self, role: str, character: str, seat_num: int = 1) -> str:
        """获取完整角色提示词（人设+角色指令）"""
        cache_key = f"{self.version}:{role}:{character}:{seat_num}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        character_prompt = GameRoles.get_character_prompt(seat_num, character)
        role_prompt = self._load_prompt(role)

        # 组合：人设描述 + 角色指令（人设在前，角色指令在后）
        full_prompt = f"{character_prompt}\n\n{role_prompt}"

        self._cache[cache_key] = full_prompt
        return full_prompt
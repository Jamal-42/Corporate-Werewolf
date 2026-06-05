# -*- coding: utf-8 -*-
"""Skills调度器 — 按目标规则注入Skills到Agent，支持事件类型粒度

targets 语法：
  "all"                       — 全局注入
  "faction:间谍" / "faction:公司"  — 按阵营
  "seat:1,3,5"                — 按座位号
  "role:预言家"                — 按角色（传统名）
  "character:逻辑怪"          — 按人设
  支持用 "+" 组合：如 "faction:间谍+seat:5"
"""
import logging
import re
from typing import Dict, List, Optional, Set

from agentscope.message import Msg

from skills_agent.skills_store import SkillsStore, WORKPLACE_ROLE, ROLE_WORKPLACE

_log = logging.getLogger("werewolf.diag.skills")


def _parse_game_stage(round_num: int, total_rounds: int = 6) -> str:
    if round_num <= 2:
        return "early"
    elif round_num <= 4:
        return "mid"
    else:
        return "late"


def _extract_stage_section(content: str, stage: str) -> str:
    """从skills内容中提取指定阶段的文本块"""
    stage_pattern = re.compile(
        rf"###\s*.*?{stage}.*?策略\s*\n(.*?)(?=\n###(?!#)|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = stage_pattern.search(content)
    if m:
        return m.group(1).strip()
    return ""


# 事件类型 → 中文标签映射
_EVENT_LABELS = {
    "speech": "发言阶段",
    "vote": "投票阶段",
    "skill": "技能阶段",
    "werewolf": "技能阶段",
    "seer": "技能阶段",
    "guard": "技能阶段",
    "witch": "技能阶段",
    "hunter": "技能阶段",
    "day_discussion": "发言阶段",
    "day_vote": "投票阶段",
}


def _phase_to_event_type(phase: str) -> str:
    """将游戏phase名映射为事件类型（speech/vote/skill）"""
    return {
        "werewolf": "skill",
        "seer": "skill",
        "guard": "skill",
        "witch": "skill",
        "hunter": "skill",
        "day_discussion": "speech",
        "day_vote": "vote",
    }.get(phase, "speech")


def _extract_event_section(content: str, stage: str, event_type: str) -> str:
    """从skills内容中提取指定阶段+事件类型的文本块

    匹配模式: #### 发言阶段 / #### 投票阶段 / #### 技能阶段
    """
    label = _EVENT_LABELS.get(event_type, "")
    if not label:
        return _extract_stage_section(content, stage)

    stage_section = _extract_stage_section(content, stage)
    if not stage_section:
        return ""

    pattern = re.compile(
        rf"####\s*{re.escape(label)}.*?\n(.*?)(?=\n####|\n###|\Z)",
        re.DOTALL,
    )
    m = pattern.search(stage_section)
    if m:
        return m.group(1).strip()
    # fallback 到整个 stage section
    return stage_section


def _parse_targets(targets_str: str) -> List[dict]:
    rules = []
    for part in targets_str.split("+"):
        part = part.strip()
        if not part:
            continue
        if part == "all":
            rules.append({"type": "all"})
        elif part.startswith("faction:"):
            faction = part[len("faction:"):]
            rules.append({"type": "faction", "value": faction})
        elif part.startswith("seat:"):
            seats = [int(s.strip()) for s in part[len("seat:"):].split(",") if s.strip().isdigit()]
            rules.append({"type": "seat", "value": seats})
        elif part.startswith("role:"):
            role = part[len("role:"):]
            rules.append({"type": "role", "value": role})
        elif part.startswith("character:"):
            character = part[len("character:"):]
            rules.append({"type": "character", "value": character})
    return rules


class SkillsDispatcher:
    """Skills调度器 — 控制Skills注入时机和目标，支持事件类型粒度"""

    def __init__(self, version: str, targets: str = "all",
                 store: Optional[SkillsStore] = None):
        self.version = version
        self.targets = targets
        self.rules = _parse_targets(targets)
        self.store = store or SkillsStore()
        self.injected_seats: Set[int] = set()
        self._skills_cache: Dict[str, Optional[str]] = {}
        self._phase_skills_cache: Dict[str, Optional[str]] = {}

    def _load_skills(self, role_workplace: str) -> Optional[str]:
        if role_workplace not in self._skills_cache:
            self._skills_cache[role_workplace] = self.store.load(self.version, role_workplace)
        return self._skills_cache[role_workplace]

    def _load_sub_skills(self, role: str, stage: str, event_type: str) -> Optional[str]:
        """加载子文件 skills/versions/{v}/{role}.{stage}.{event_type}.md"""
        role_workplace = ROLE_WORKPLACE.get(role, role)
        filename = f"{role_workplace}.{stage}.{event_type}.md"
        cache_key = f"{filename}"
        if cache_key in self._phase_skills_cache:
            return self._phase_skills_cache[cache_key]
        content = self.store.load(self.version, role_workplace, filename=filename)
        self._phase_skills_cache[cache_key] = content
        return content

    def should_inject(self, seat: int, role: str, faction: str,
                      character: str) -> bool:
        if not self.rules:
            return False

        for rule in self.rules:
            rtype = rule["type"]
            if rtype == "all":
                return True
            elif rtype == "faction":
                if rule["value"] == "间谍" and role == "狼人":
                    return True
                if rule["value"] == "公司" and role != "狼人":
                    return True
            elif rtype == "seat":
                if seat in rule["value"]:
                    return True
            elif rtype == "role":
                if role == rule["value"]:
                    return True
            elif rtype == "character":
                if character == rule["value"]:
                    return True
        return False

    def get_initial_skills(self, role: str) -> str:
        role_workplace = ROLE_WORKPLACE.get(role, role)
        content = self._load_skills(role_workplace)
        if not content:
            return ""

        return (
            f"\n\n---\n"
            f"【决策指导Skills】以下是基于历史评测优化的策略指导，请严格参考：\n"
            f"{content}\n"
            f"---\n"
        )

    def inject_initial(self, agent, seat: int, role: str,
                       faction: str, character: str) -> bool:
        if not self.should_inject(seat, role, faction, character):
            return False

        skills_prompt = self.get_initial_skills(role)
        if not skills_prompt:
            return False

        agent._sys_prompt += skills_prompt
        self.injected_seats.add(seat)
        _log.info(f"Skills injected (initial): seat={seat}, role={role}")
        return True

    def get_phase_skills(self, role: str, stage: str, event_type: str = None) -> Optional[str]:
        """获取指定阶段(+事件类型)的skills片段

        优先加载子文件，fallback到主文件提取
        """
        role_workplace = ROLE_WORKPLACE.get(role, role)

        # 尝试加载子文件
        if event_type:
            sub_content = self._load_sub_skills(role, stage, event_type)
            if sub_content:
                et_label = _EVENT_LABELS.get(event_type, event_type)
                return (
                    f"【{stage}阶段·{et_label}策略提示】\n{sub_content}\n"
                    f"请在当前决策中参考以上策略指导。"
                )

        # fallback: 从主文件提取
        content = self._load_skills(role_workplace)
        if not content:
            return None

        if event_type:
            section = _extract_event_section(content, stage, event_type)
        else:
            section = _extract_stage_section(content, stage)

        if not section:
            return None

        if event_type:
            et_label = _EVENT_LABELS.get(event_type, event_type)
            phase_prompt = (
                f"【{stage}阶段·{et_label}策略提示】\n{section}\n"
                f"请在当前决策中参考以上策略指导。"
            )
        else:
            phase_prompt = (
                f"【当前阶段策略提示（{stage}阶段）】\n{section}\n"
                f"请在当前决策中参考以上策略指导。"
            )
        return phase_prompt

    async def inject_phase_skills(self, agent, phase: str, round_num: int,
                            role: str, seat: int) -> bool:
        """阶段注入：通过Msg通知当前阶段推荐行为

        Args:
            agent: ReActAgent
            phase: 当前阶段名（werewolf/seer/guard/witch/hunter/day_vote/day_discussion）
            round_num: 当前轮次
            role: 角色名（传统名）
            seat: 座位号
        """
        if seat not in self.injected_seats:
            return False

        stage = _parse_game_stage(round_num)
        event_type = _phase_to_event_type(phase)
        phase_prompt = self.get_phase_skills(role, stage, event_type)
        if not phase_prompt:
            return False

        msg = Msg(
            name="system",
            content=phase_prompt,
            role="system",
        )
        await agent.memory.add(msg)
        _log.info(f"Skills injected (phase): seat={seat}, stage={stage}, phase={phase}, event_type={event_type}")
        return True

    def get_injected_seats_list(self) -> List[int]:
        return sorted(self.injected_seats)

    def get_meta(self) -> dict:
        return {
            "skills_version": self.version,
            "skills_targets": self.targets,
            "injected_seats": self.get_injected_seats_list(),
        }

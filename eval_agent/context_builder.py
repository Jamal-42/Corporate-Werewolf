# -*- coding: utf-8 -*-
"""从JSONL构建评测上下文

单次遍历JSONL，为每个待评测决策构建丰富的结构化上下文，
包括信息不对称分析、历史摘要、上帝视角结果等。
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shared.role_mapping import ROLE_ALIASES_TO_WORKPLACE as ROLE_ALIASES, normalize_role_to_workplace as _normalize_role

_log = logging.getLogger("werewolf.diag.eval")

SPY_ROLES = {"间谍", "狼人"}
GOOD_ROLES = {"HR总监", "预言家", "CEO", "女巫", "法务总监", "猎人", "安保主管", "守护者", "村民", "普通员工"}


@dataclass
class GameContext:
    """全局游戏上下文（上帝视角）"""
    player_count: int = 0
    role_map: Dict[str, str] = field(default_factory=dict)          # "2号" → "间谍"
    character_map: Dict[str, dict] = field(default_factory=dict)    # "2号" → {personality, ...}
    seat_to_name: Dict[str, str] = field(default_factory=dict)     # "2号" → "卷王"
    alive_per_round: Dict[int, List[str]] = field(default_factory=dict)
    deaths: List[Dict] = field(default_factory=list)
    vote_results: List[Dict] = field(default_factory=list)
    winner: Optional[str] = None
    total_rounds: int = 0
    survivors: List[Dict] = field(default_factory=list)


@dataclass
class DecisionContext:
    """单个待评测决策的上下文"""
    # 决策本身
    event_id: int = 0
    event_type: str = ""            # "speech" / "vote" / "skill"
    round: int = 0
    phase: str = ""
    player: str = ""
    role: str = ""
    action: str = ""
    target: Optional[str] = None
    reasoning_steps: Optional[List[str]] = None
    key_evidence: Optional[str] = None
    full_output: Optional[Dict] = None
    llm_output_text: Optional[str] = None
    suspicion_level: Optional[int] = None

    # 决策时的游戏状态
    alive_at_decision: List[str] = field(default_factory=list)
    witch_has_antidote: Optional[bool] = None
    witch_has_poison: Optional[bool] = None
    last_guarded: Optional[str] = None

    # 决策前的历史
    prior_deaths_summary: str = ""
    prior_vote_summaries: List[str] = field(default_factory=list)
    prior_speech_summaries: List[str] = field(default_factory=list)

    # 信息不对称分析
    known_to_player: List[str] = field(default_factory=list)
    unknown_to_player: List[str] = field(default_factory=list)
    info_advantage: bool = False

    # 决策后的结果（上帝视角）
    target_actual_role: Optional[str] = None
    target_died_this_round: bool = False
    team_won: bool = False
    game_stage: str = ""            # "early" / "mid" / "late"


def _is_spy(role: str) -> bool:
    return role in SPY_ROLES


def _classify_event_type(action: str, phase: str) -> str:
    """将action+phase映射为评测事件类型"""
    if action == "投票" or "vote" in phase:
        return "vote"
    skill_actions = {"间谍窃取", "HR背调", "加密保护", "CEO挽留", "CEO辞退", "法务诉讼"}
    if action in skill_actions:
        return "skill"
    return "speech"


def _determine_game_stage(round_num: int, total_rounds: int) -> str:
    if total_rounds <= 3:
        if round_num == 1:
            return "early"
        if round_num == total_rounds:
            return "late"
        return "mid"
    if round_num == 1:
        return "early"
    if round_num >= total_rounds - 1:
        return "late"
    return "mid"


def _build_prior_deaths_summary(deaths: List[Dict], up_to_round: int) -> str:
    """构建决策前的死亡摘要"""
    parts = []
    for d in deaths:
        r = d.get("round", 0)
        if r >= up_to_round:
            break
        player = d.get("player", "?")
        cause = d.get("cause", "未知")
        phase = "夜" if "窃取" in cause or "毒" in cause else "天"
        parts.append(f"第{r}{phase}: {player}{cause}")
    return "; ".join(parts) if parts else "无"


def _build_prior_vote_summaries(vote_results: List[Dict], up_to_round: int) -> List[str]:
    """构建决策前的投票摘要"""
    summaries = []
    for v in vote_results:
        r = v.get("round", 0)
        if r >= up_to_round:
            break
        voted_out = v.get("voted_out")
        vote_count = v.get("vote_count", 0)
        if voted_out:
            summaries.append(f"第{r}天: {voted_out}以{vote_count}票被投出")
    return summaries


def _build_known_info(player: str, role: str, role_map: Dict[str, str],
                      events_up_to: List[Dict], seat_to_name: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """分析决策者已知/未知的信息"""
    known = []
    unknown = []

    # 间谍知道队友身份
    if _is_spy(role):
        teammates = [p for p, r in role_map.items() if _is_spy(r) and p != player]
        if teammates:
            names = [seat_to_name.get(p, p) for p in teammates]
            known.append(f"你的间谍队友: {', '.join(names)}")

    # 收集已公开的信息
    for ev in events_up_to:
        et = ev.get("event_type", "")
        if et == "vote_result":
            voted_out = ev.get("voted_out")
            if voted_out:
                known.append(f"第{ev.get('round', '?')}天: {voted_out}被投出")
        elif et == "death":
            p = ev.get("player", "")
            cause = ev.get("cause", "")
            known.append(f"第{ev.get('round', '?')}夜: {p}{cause}")

    # 上帝视角的未知信息
    if not _is_spy(role):
        spies = [p for p, r in role_map.items() if _is_spy(r)]
        names = [seat_to_name.get(p, p) for p in spies]
        unknown.append(f"间谍身份（上帝视角）: {', '.join(names)}")

    return known, unknown


def build_evaluation_contexts(
    jsonl_path: str | Path,
) -> Tuple[GameContext, List[DecisionContext]]:
    """单次遍历JSONL，构建所有评测上下文

    Returns:
        (GameContext, List[DecisionContext])
    """
    jsonl_path = Path(jsonl_path)

    # 阶段1: 单次遍历收集所有原始事件
    raw_events: List[Dict] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw_events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # 阶段2: 构建GameContext
    game_ctx = GameContext()
    model_calls_by_key: Dict[str, List[Dict]] = {}   # (player, round, phase) → [model_call events]
    state_snapshots: List[Dict] = []
    all_decisions: List[Dict] = []
    # 反向映射：人设名 → 座次号（用于统一player标识）
    name_to_seat: Dict[str, str] = {}

    for event in raw_events:
        et = event.get("event_type", "")

        if et == "game_init":
            game_ctx.player_count = event.get("player_count", 0)
            for entry in event.get("character_role_map", []):
                seat_num = entry.get("seat_num")
                key = f"{seat_num}号" if seat_num else entry.get("character_name", "")
                role = _normalize_role(entry.get("role", ""))
                game_ctx.role_map[key] = role
                game_ctx.seat_to_name[key] = entry.get("character_name", "")
                char_name = entry.get("character_name", "")
                if char_name and char_name != key:
                    name_to_seat[char_name] = key
                game_ctx.character_map[key] = {
                    "character_name": entry.get("character_name", ""),
                    "workplace_title": entry.get("workplace_title", ""),
                    "personality": entry.get("personality", ""),
                    "speaking_style": entry.get("speaking_style", ""),
                    "game_strategy": entry.get("game_strategy", ""),
                    "model_name": entry.get("model_name", ""),
                    "enable_thinking": entry.get("enable_thinking", True),
                }

        elif et == "state_snapshot":
            state_snapshots.append(event)

        elif et == "death":
            game_ctx.deaths.append({
                "round": event.get("round", 0),
                "player": event.get("player", ""),
                "cause": event.get("cause", ""),
            })
            r = event.get("round", 0)
            alive = event.get("alive_players", [])
            if alive:
                game_ctx.alive_per_round[r] = alive

        elif et == "vote_result":
            game_ctx.vote_results.append({
                "round": event.get("round", 0),
                "votes": event.get("votes", {}),
                "voted_out": event.get("voted_out"),
                "vote_count": event.get("vote_count", 0),
            })

        elif et == "game_over":
            game_ctx.winner = event.get("winner", "")
            game_ctx.total_rounds = event.get("total_rounds", 0)
            game_ctx.survivors = event.get("survivors", [])

        elif et == "model_call":
            player = event.get("player", "")
            player = name_to_seat.get(player, player)
            phase = event.get("phase", "")
            key = (player, phase)
            model_calls_by_key.setdefault(key, []).append(event)

        elif et == "decision":
            all_decisions.append(event)

    # 补充alive_per_round：从state_snapshot中提取
    for snap in state_snapshots:
        r = snap.get("round", 0)
        if r not in game_ctx.alive_per_round and snap.get("alive_players"):
            game_ctx.alive_per_round[r] = snap["alive_players"]

    # 阶段3: 为每个decision构建DecisionContext
    decision_contexts: List[DecisionContext] = []

    for idx, dec in enumerate(all_decisions):
        player = dec.get("player", "")
        player = name_to_seat.get(player, player)
        role_raw = dec.get("role", "")
        role = _normalize_role(role_raw)
        round_num = dec.get("round", 0) or 0
        phase = dec.get("phase", "")
        action = dec.get("action", "")
        target = dec.get("target")

        # 跳过非核心决策（死亡事件、模型调用等）
        event_type = _classify_event_type(action, phase)
        if action == "死亡" or action == "模型调用":
            continue

        # 匹配model_call以获取完整LLM输出
        llm_output_text = None
        suspicion_level = None
        # 尝试通过(player, phase)匹配
        for key_pattern in [(player, phase), (player, f"{phase}_discussion"), (player, f"{phase}_vote")]:
            candidates = model_calls_by_key.get(key_pattern, [])
            if candidates:
                # 取最后一个（如果有多轮讨论）
                last_mc = candidates[-1]
                output_content = last_mc.get("output_content", {})
                if isinstance(output_content, dict):
                    llm_output_text = output_content.get("content")
                    metadata = output_content.get("metadata")
                    if isinstance(metadata, dict):
                        sl = metadata.get("suspicion_level")
                        if sl is not None:
                            try:
                                suspicion_level = int(sl)
                            except (ValueError, TypeError):
                                pass
                break

        # 也尝试通过seat匹配
        seat = dec.get("seat", "")
        if llm_output_text is None and seat:
            for (p, ph), mcs in model_calls_by_key.items():
                if ph == phase or ph.startswith(phase):
                    for mc in mcs:
                        mc_seat = mc.get("seat", "")
                        if mc_seat == seat:
                            output_content = mc.get("output_content", {})
                            if isinstance(output_content, dict):
                                llm_output_text = output_content.get("content")
                                metadata = output_content.get("metadata")
                                if isinstance(metadata, dict):
                                    sl = metadata.get("suspicion_level")
                                    if sl is not None:
                                        try:
                                            suspicion_level = int(sl)
                                        except (ValueError, TypeError):
                                            pass
                            break
                    if llm_output_text:
                        break

        # 决策时的存活状态
        alive_at = game_ctx.alive_per_round.get(round_num, [])
        if not alive_at:
            # 回退：从deaths推导
            dead_players = {d["player"] for d in game_ctx.deaths if d.get("round", 0) < round_num}
            alive_at = [p for p in game_ctx.role_map if p not in dead_players]

        # 从state_snapshot获取女巫/守卫状态
        witch_has_antidote = None
        witch_has_poison = None
        last_guarded = None
        for snap in reversed(state_snapshots):
            if snap.get("round", 0) <= round_num:
                antidote_val = snap.get("witch_has_antidote")
                # 容错：实际JSONL中可能是列表而非bool
                if isinstance(antidote_val, bool):
                    witch_has_antidote = antidote_val
                elif isinstance(antidote_val, list):
                    witch_has_antidote = len(antidote_val) > 0
                else:
                    witch_has_antidote = bool(antidote_val)

                poison_val = snap.get("witch_has_poison")
                if isinstance(poison_val, bool):
                    witch_has_poison = poison_val
                else:
                    witch_has_poison = bool(poison_val)

                lg = snap.get("last_guarded")
                if isinstance(lg, bool):
                    last_guarded = snap.get("alive_characters")
                elif isinstance(lg, str):
                    last_guarded = lg
                break

        # 决策前历史
        prior_deaths = _build_prior_deaths_summary(game_ctx.deaths, round_num)
        prior_votes = _build_prior_vote_summaries(game_ctx.vote_results, round_num)

        # 收集决策前的发言摘要（最近2轮）
        prior_speeches = []
        for prev_dec in all_decisions:
            prev_round = prev_dec.get("round", 0) or 0
            if prev_round >= round_num:
                break
            if round_num - prev_round > 2:
                continue
            prev_action = prev_dec.get("action", "")
            if prev_action == "公开发言" and prev_dec.get("key_evidence"):
                prior_speeches.append(
                    f"第{prev_round}轮 {prev_dec.get('player', '')}: {prev_dec['key_evidence'][:100]}"
                )

        # 信息不对称分析
        events_up_to = [e for e in raw_events
                        if (e.get("round") or 0) < round_num or e.get("event_type") in ("game_init",)]
        known, unknown = _build_known_info(player, role, game_ctx.role_map, events_up_to, game_ctx.seat_to_name)
        info_advantage = _is_spy(role)  # 间谍天然有信息优势

        # 上帝视角结果
        target_actual_role = None
        if target and target in game_ctx.role_map:
            target_actual_role = game_ctx.role_map[target]

        target_died_this_round = any(
            d.get("player") == target and d.get("round") == round_num
            for d in game_ctx.deaths
        )

        # 阵营是否获胜
        spy_won = game_ctx.winner in ("潜伏阵营", "狼人", "间谍")
        player_is_spy = _is_spy(role)
        team_won = (spy_won and player_is_spy) or (not spy_won and not player_is_spy)

        game_stage = _determine_game_stage(round_num, game_ctx.total_rounds or round_num + 1)

        dc = DecisionContext(
            event_id=idx + 1,
            event_type=event_type,
            round=round_num,
            phase=phase,
            player=player,
            role=role,
            action=action,
            target=target,
            reasoning_steps=dec.get("reasoning_steps"),
            key_evidence=dec.get("key_evidence"),
            full_output=dec.get("full_output"),
            llm_output_text=llm_output_text,
            suspicion_level=suspicion_level,
            alive_at_decision=alive_at,
            witch_has_antidote=witch_has_antidote,
            witch_has_poison=witch_has_poison,
            last_guarded=last_guarded,
            prior_deaths_summary=prior_deaths,
            prior_vote_summaries=prior_votes,
            prior_speech_summaries=prior_speeches[-10:],  # 最多保留10条
            known_to_player=known,
            unknown_to_player=unknown,
            info_advantage=info_advantage,
            target_actual_role=target_actual_role,
            target_died_this_round=target_died_this_round,
            team_won=team_won,
            game_stage=game_stage,
        )
        decision_contexts.append(dc)

    _log.info(f"Context builder: {len(raw_events)} raw events → {len(decision_contexts)} decision contexts")
    return game_ctx, decision_contexts

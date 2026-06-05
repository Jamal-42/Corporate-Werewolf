# -*- coding: utf-8 -*-
"""JSONL结构化日志解析器 — 替代正则解析 .txt 文件

提供两个解析函数：
- parse_log_jsonl(): 供 evaluation_cn.py 使用，返回 (roles, player_order, events)
- parse_game_log_jsonl(): 供 web_ui.py 使用，返回 ReplayData
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from shared.role_mapping import ROLE_ALIASES, ROLE_COLORS, normalize_role
from shared.data_models import DecisionEvent, ReplayData


# ── evaluation_cn.py 兼容 ──────────────────────────────────────────────


def _to_seat_key(name: str, seat_map: dict) -> str:
    """将任意玩家标识统一为座次号（如'1号'）

    seat_map: {人设名/座次名 -> 座次号} 反向映射
    """
    if not name:
        return name
    # 已经是X号格式
    if len(name) >= 2 and name[-1] == "号" and name[:-1].isdigit():
        return name
    # 从seat_map查找
    return seat_map.get(name, name)


def _skill_type_to_action(skill_type: str) -> tuple[str, str]:
    """将 skill_type 映射为 (category, action)"""
    mapping = {
        "spy_steal": ("skill", "间谍窃取"),
        "seer_check": ("skill", "HR背调"),
        "guard_protect": ("skill", "加密保护"),
        "witch_antidote": ("skill", "CEO挽留"),
        "witch_poison": ("skill", "CEO辞退"),
        "hunter_shoot": ("skill", "法务诉讼"),
    }
    return mapping.get(skill_type, ("skill", skill_type))


def _phase_from_event(event: dict) -> str:
    """从事件推断阶段"""
    et = event.get("event_type", "")
    if et in ("night_start",):
        return "夜晚"
    if et in ("day_start",):
        return "白天讨论"
    phase = event.get("phase", "")
    if "night" in phase or "werewolf" in phase or "seer" in phase or "guard" in phase or "witch" in phase:
        return "夜晚"
    if "vote" in phase:
        return "白天投票"
    if "day" in phase or "discussion" in phase or "hunter" in phase:
        return "白天讨论"
    return "白天讨论"


def parse_log_jsonl(jsonl_path: Path | str) -> tuple[dict[str, str], list[str], list[DecisionEvent]]:
    """解析 .jsonl 文件，返回 (roles, player_order, events)

    兼容 evaluation_cn.py 的 parse_log_text() 返回格式。
    """
    if isinstance(jsonl_path, str):
        jsonl_path = Path(jsonl_path)

    roles: dict[str, str] = {}
    player_order: list[str] = []
    events: list[DecisionEvent] = []
    event_id = 0
    # 反向映射：人设名/旧key -> 座次号
    seat_map: dict[str, str] = {}

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            et = event.get("event_type", "")

            if et == "game_init":
                for entry in event.get("character_role_map", []):
                    name = entry.get("character_name", "")
                    seat = entry.get("seat_num")
                    key = f"{seat}号" if seat else name
                    role = normalize_role(entry.get("role", ""))
                    if key:
                        roles[key] = role
                        if key not in player_order:
                            player_order.append(key)
                    if name and name != key:
                        roles[name] = role
                        seat_map[name] = key

            elif et == "decision":
                event_id += 1
                player = event.get("player", "")
                player = _to_seat_key(player, seat_map)
                role = normalize_role(event.get("role", ""))
                action = event.get("action", "")
                target = event.get("target")
                if target:
                    target = _to_seat_key(target, seat_map)
                phase = _phase_from_event(event)
                category = "vote" if action == "投票" else "skill" if action in (
                    "间谍窃取", "HR背调", "加密保护", "CEO挽留", "CEO辞退", "法务诉讼"
                ) else "speech"
                reason = event.get("key_evidence") or ""
                raw = json.dumps(event.get("full_output") or event, ensure_ascii=False)
                metadata = {}
                if event.get("reasoning_steps"):
                    metadata["reasoning_steps"] = event["reasoning_steps"]
                if event.get("key_evidence"):
                    metadata["key_evidence"] = event["key_evidence"]
                events.append(DecisionEvent(
                    id=event_id,
                    round=event.get("round"),
                    phase=phase,
                    player=player,
                    role=role or roles.get(player, "未知"),
                    category=category,
                    action=action,
                    target=target,
                    reason=reason,
                    raw=raw,
                    metadata=metadata,
                ))

            elif et == "vote_result":
                event_id += 1
                votes = event.get("votes", {})
                voted_out = event.get("voted_out")
                vote_count = event.get("vote_count", 0)
                seat_votes = event.get("seat_votes")
                # 优先使用 seat_votes（座次号->座次号），否则翻译 votes
                vote_map = {}
                if seat_votes and isinstance(seat_votes, dict):
                    for voter, target in seat_votes.items():
                        v = _to_seat_key(voter, seat_map)
                        t = _to_seat_key(target, seat_map) if target else target
                        vote_map[v] = t
                else:
                    for voter, target in votes.items():
                        v = _to_seat_key(voter, seat_map)
                        t = _to_seat_key(target, seat_map) if target else target
                        vote_map[v] = t
                for voter, target in vote_map.items():
                    event_id += 1
                    events.append(DecisionEvent(
                        id=event_id,
                        round=event.get("round"),
                        phase="白天投票",
                        player=voter,
                        role=roles.get(voter, "未知"),
                        category="vote",
                        action="投票",
                        target=target,
                        reason="",
                        raw=json.dumps({"vote": target, "voted_out": voted_out, "vote_count": vote_count}, ensure_ascii=False),
                        metadata={"voted_out": voted_out, "vote_count": vote_count},
                    ))

            elif et == "skill_resolution":
                event_id += 1
                skill_type = event.get("skill_type", "")
                category, action = _skill_type_to_action(skill_type)
                source = event.get("source_player", "")
                source = _to_seat_key(source, seat_map)
                target = event.get("target_player")
                if target:
                    target = _to_seat_key(target, seat_map)
                events.append(DecisionEvent(
                    id=event_id,
                    round=event.get("round"),
                    phase="夜晚",
                    player=source,
                    role=roles.get(source, "未知"),
                    category=category,
                    action=action,
                    target=target,
                    reason=event.get("result", ""),
                    raw=json.dumps(event, ensure_ascii=False),
                    metadata={"rule_applied": event.get("rule_applied", "")},
                ))

            elif et == "death":
                event_id += 1
                player = event.get("player", "")
                player = _to_seat_key(player, seat_map)
                cause = event.get("cause", "")
                events.append(DecisionEvent(
                    id=event_id,
                    round=event.get("round"),
                    phase="夜晚",
                    player=player,
                    role=roles.get(player, "未知"),
                    category="skill",
                    action="死亡",
                    target=None,
                    reason=cause,
                    raw=json.dumps(event, ensure_ascii=False),
                    metadata={"cause": cause},
                ))

            elif et == "model_call":
                event_id += 1
                player = event.get("player", "")
                events.append(DecisionEvent(
                    id=event_id,
                    round=None,
                    phase=event.get("phase", ""),
                    player=player,
                    role=roles.get(player, "未知"),
                    category="other",
                    action="模型调用",
                    target=None,
                    reason="",
                    raw=json.dumps(event, ensure_ascii=False),
                    metadata={
                        "model_name": event.get("model_name", ""),
                        "input_tokens": event.get("input_tokens"),
                        "output_tokens": event.get("output_tokens"),
                        "latency_ms": event.get("latency_ms"),
                    },
                ))

    return roles, player_order, events


# ── web_ui.py 兼容 ──────────────────────────────────────────────────────


def _normalize_webui_role(role: str | None) -> str:
    """web_ui 使用的角色归一化 — 将游戏角色映射到职场名称"""
    aliases = {
        "间谍": "商业间谍", "狼人": "商业间谍",
        "HR总监": "预言家", "预言家": "预言家",
        "CEO": "女巫", "女巫": "女巫",
        "法务总监": "猎人", "猎人": "猎人",
        "安保主管": "守护者", "守护者": "守护者",
        "村民": "普通员工", "普通员工": "普通员工",
    }
    return aliases.get(role or "", role or "普通员工")


def _build_player(name: str, role: str | None, idx: int) -> dict[str, Any]:
    normalized = _normalize_webui_role(role)
    return {
        "name": name,
        "role": normalized,
        "alive": True,
        "color": ROLE_COLORS.get(normalized, "#475569"),
        "index": idx,
    }


def _append_event(
    events: list[dict[str, Any]],
    player_map: dict[str, dict[str, Any]],
    player_order: list[str],
    *,
    event_type: str,
    text: str,
    round_num: int | None,
    phase: str,
    speaker: str | None = None,
    focus_players: list[str] | None = None,
    actor: str | None = None,
    actor_role: str | None = None,
    target: str | None = None,
) -> None:
    events.append({
        "id": len(events) + 1,
        "type": event_type,
        "text": text,
        "speaker": speaker,
        "round": round_num,
        "phase": phase,
        "focus_players": focus_players or [],
        "actor": actor,
        "actor_role": actor_role,
        "target": target,
        "players": [_snapshot_player(player_map[n]) for n in player_order if n in player_map],
    })


def _snapshot_player(p: dict[str, Any]) -> dict[str, Any]:
    return {"name": p["name"], "role": p["role"], "alive": p["alive"], "color": p["color"], "index": p["index"]}


def _mark_dead(player_map: dict[str, dict[str, Any]], names: list[str]) -> None:
    for name in names:
        if name in player_map:
            player_map[name]["alive"] = False


def parse_game_log_jsonl(jsonl_path: Path | str) -> ReplayData:
    """解析 .jsonl 文件，返回 ReplayData

    兼容 web_ui.py 的 parse_game_log() 返回格式。
    """
    if isinstance(jsonl_path, str):
        jsonl_path = Path(jsonl_path)

    player_order: list[str] = []
    player_map: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    round_num: int | None = None
    phase = "序章"

    with open(jsonl_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    # 重新从头读取并逐行解析
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            et = event.get("event_type", "")

            if et == "game_init":
                for entry in event.get("character_role_map", []):
                    name = entry.get("character_name", "")
                    seat = entry.get("seat_num")
                    role = entry.get("role")
                    # Use seat number as primary key if available
                    key = f"{seat}号" if seat else name
                    if key and key not in player_map:
                        player_order.append(key)
                        player_map[key] = _build_player(key, role, len(player_order) - 1)
                    elif name and name not in player_map:
                        player_order.append(name)
                        player_map[name] = _build_player(name, role, len(player_order) - 1)
                _append_event(events, player_map, player_order,
                              event_type="setup", text="玩家入场，围桌落座。",
                              round_num=round_num, phase=phase,
                              focus_players=list(player_order))

            elif et == "night_start":
                round_num = event.get("round", round_num)
                phase = "夜晚"
                _append_event(events, player_map, player_order,
                              event_type="phase", text=f"第 {round_num} 夜，天黑请闭眼。",
                              round_num=round_num, phase=phase)

            elif et == "day_start":
                round_num = event.get("round", round_num)
                phase = "白天"
                _append_event(events, player_map, player_order,
                              event_type="phase", text=f"第 {round_num} 天，太阳升起。",
                              round_num=round_num, phase=phase)

            elif et == "death":
                player = event.get("player", "")
                cause = event.get("cause", "")
                round_num = event.get("round", round_num)
                _mark_dead(player_map, [player])
                _append_event(events, player_map, player_order,
                              event_type="death", text=f"{player} 因{cause}出局。",
                              round_num=round_num, phase=phase,
                              focus_players=[player])

            elif et == "skill_resolution":
                round_num = event.get("round", round_num)
                skill_type = event.get("skill_type", "")
                source = event.get("source_player", "")
                target_player = event.get("target_player")
                result = event.get("result", "")

                if "spy" in skill_type or "steal" in skill_type:
                    event_type = "attack"
                    text = f"间谍将目标锁定为 {target_player}。"
                    actor_role = "商业间谍"
                elif "guard" in skill_type or "protect" in skill_type:
                    event_type = "save"
                    text = f"安保主管保护了 {target_player}。"
                    actor_role = "守护者"
                elif "seer" in skill_type or "check" in skill_type:
                    event_type = "inspect"
                    text = f"预言家查验了 {target_player}。"
                    actor_role = "预言家"
                else:
                    event_type = "narration"
                    text = result
                    actor_role = None

                _append_event(events, player_map, player_order,
                              event_type=event_type, text=text,
                              round_num=round_num, phase=phase,
                              focus_players=[target_player] if target_player else [],
                              actor=source, actor_role=actor_role,
                              target=target_player)

            elif et == "vote_result":
                round_num = event.get("round", round_num)
                voted_out = event.get("voted_out")
                vote_count = event.get("vote_count", 0)
                if voted_out:
                    _mark_dead(player_map, [voted_out])
                    _append_event(events, player_map, player_order,
                                  event_type="vote",
                                  text=f"{voted_out} 被投票淘汰，票数 {vote_count}。",
                                  round_num=round_num, phase="白天",
                                  focus_players=[voted_out])

            elif et == "decision":
                player = event.get("player", "")
                action = event.get("action", "")
                target = event.get("target")
                round_num = event.get("round", round_num)
                phase_val = _phase_from_event(event)
                if phase_val == "夜晚":
                    continue  # 夜晚决策由 skill_resolution 处理
                # 白天发言
                if action == "公开发言":
                    reason = event.get("key_evidence") or ""
                    _append_event(events, player_map, player_order,
                                  event_type="speech", text=reason or f"{player} 发言了。",
                                  round_num=round_num, phase="白天",
                                  speaker=player, focus_players=[player],
                                  actor=player)

            elif et == "game_over":
                winner = event.get("winner", "")
                _append_event(events, player_map, player_order,
                              event_type="ending",
                              text=f"游戏结束！{winner}",
                              round_num=round_num, phase=phase)

    if not player_order:
        raise ValueError("JSONL日志中未识别到玩家信息，无法生成回放")

    if not events:
        _append_event(events, player_map, player_order,
                      event_type="setup", text="日志已加载，但没有识别到可回放事件。",
                      round_num=round_num, phase=phase)

    return ReplayData(
        source_file=jsonl_path.name,
        players=[_snapshot_player(player_map[n]) for n in player_order if n in player_map],
        events=events,
        raw_text=raw_text,
    )

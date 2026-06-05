# -*- coding: utf-8 -*-
"""结构化JSON日志系统 - 记录游戏全过程的关键信息"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class JSONGameLogger:
    """JSON结构化游戏日志记录器

    写入.jsonl文件（每行一个JSON事件），记录：
    1. 游戏初始化：12个人设→角色映射表
    2. 模型调用记录
    3. 决策事件
    4. 技能结算事件
    5. 游戏状态快照
    6. 游戏结局
    """

    def __init__(self, log_path: str):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.log_path, "w", encoding="utf-8")

    def _write_event(self, event: Dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False, default=str)
        self._file.write(line + "\n")
        self._file.flush()

    def close(self) -> None:
        if self._file and not self._file.closed:
            self._file.close()

    # --- 事件类型 ---

    def log_game_init(
        self,
        player_count: int,
        character_role_map: List[Dict[str, Any]],
        prompt_version: str = "v1",
        model_name: str = "qwen-max",
    ) -> None:
        """记录游戏初始化事件，包含完整人设-角色映射"""
        self._write_event({
            "event_type": "game_init",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "player_count": player_count,
            "prompt_version": prompt_version,
            "model_name": model_name,
            "character_role_map": character_role_map,
        })

    def log_model_call(
        self,
        player: str,
        role: str,
        phase: str,
        model_name: str,
        prompt_version: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        latency_ms: Optional[float] = None,
        seat: Optional[str] = None,
        output_content: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录模型调用，包含输出内容"""
        event = {
            "event_type": "model_call",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "player": player,
            "role": role,
            "phase": phase,
            "model_name": model_name,
            "prompt_version": prompt_version,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
        }
        if seat is not None:
            event["seat"] = seat
        if output_content is not None:
            event["output_content"] = output_content
        self._write_event(event)

    def log_decision(
        self,
        round_num: int,
        phase: str,
        player: str,
        role: str,
        action: str,
        target: Optional[str],
        reasoning_steps: Optional[List[str]],
        key_evidence: Optional[str],
        full_output: Optional[Dict[str, Any]],
        seat: Optional[str] = None,
    ) -> None:
        """记录决策事件"""
        event = {
            "event_type": "decision",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "round": round_num,
            "phase": phase,
            "player": player,
            "role": role,
            "action": action,
            "target": target,
            "reasoning_steps": reasoning_steps,
            "key_evidence": key_evidence,
            "full_output": full_output,
        }
        if seat is not None:
            event["seat"] = seat
        self._write_event(event)

    def log_skill_resolution(
        self,
        round_num: int,
        skill_type: str,
        source_player: str,
        target_player: Optional[str],
        result: str,
        rule_applied: Optional[str] = None,
        source_seat: Optional[str] = None,
        target_seat: Optional[str] = None,
    ) -> None:
        """记录技能结算事件"""
        event = {
            "event_type": "skill_resolution",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "round": round_num,
            "skill_type": skill_type,
            "source_player": source_player,
            "target_player": target_player,
            "result": result,
            "rule_applied": rule_applied,
        }
        if source_seat is not None:
            event["source_seat"] = source_seat
        if target_seat is not None:
            event["target_seat"] = target_seat
        self._write_event(event)

    def log_state_snapshot(
        self,
        round_num: int,
        phase: str,
        alive_players: List[str],
        witch_has_antidote: bool,
        witch_has_poison: bool,
        last_guarded: Optional[str],
        alive_characters: Optional[List[str]] = None,
    ) -> None:
        """记录游戏状态快照"""
        event = {
            "event_type": "state_snapshot",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "round": round_num,
            "phase": phase,
            "alive_players": alive_players,
            "witch_has_antidote": witch_has_antidote,
            "witch_has_poison": witch_has_poison,
            "last_guarded": last_guarded,
        }
        if alive_characters is not None:
            event["alive_characters"] = alive_characters
        self._write_event(event)

    def log_game_over(
        self,
        winner: str,
        total_rounds: int,
        survivors: List[Dict[str, str]],
        skills_injection: Optional[Dict] = None,
    ) -> None:
        """记录游戏结局"""
        event = {
            "event_type": "game_over",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "winner": winner,
            "total_rounds": total_rounds,
            "survivors": survivors,
        }
        if skills_injection:
            event["skills_injection"] = skills_injection
        self._write_event(event)

    def log_night_start(self, round_num: int) -> None:
        """记录夜晚开始"""
        self._write_event({
            "event_type": "night_start",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "round": round_num,
        })

    def log_day_start(self, round_num: int) -> None:
        """记录白天开始"""
        self._write_event({
            "event_type": "day_start",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "round": round_num,
        })

    def log_death(self, round_num: int, player: str, cause: str, seat: Optional[str] = None) -> None:
        """记录死亡事件"""
        event = {
            "event_type": "death",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "round": round_num,
            "player": player,
            "cause": cause,
        }
        if seat is not None:
            event["seat"] = seat
        self._write_event(event)

    def log_vote_result(
        self,
        round_num: int,
        votes: Dict[str, Optional[str]],
        voted_out: Optional[str],
        vote_count: int,
        seat_votes: Optional[Dict[str, Optional[str]]] = None,
    ) -> None:
        """记录投票结果"""
        event = {
            "event_type": "vote_result",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "round": round_num,
            "votes": votes,
            "voted_out": voted_out,
            "vote_count": vote_count,
        }
        if seat_votes is not None:
            event["seat_votes"] = seat_votes
        self._write_event(event)

    def log_error(
        self,
        error_message: str,
        phase: str = "unknown",
        round_num: Optional[int] = None,
        error_type: str = "unknown",
    ) -> None:
        """记录错误事件"""
        self._write_event({
            "event_type": "error",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "round": round_num,
            "phase": phase,
            "error_type": error_type,
            "error_message": error_message,
        })

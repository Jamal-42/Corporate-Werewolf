# -*- coding: utf-8 -*-
"""胜率追踪器 — 从JSONL记录统计胜率，支持分组对比

存储: winrate/history.jsonl
每行: {"jsonl_path", "winner", "total_rounds", "players", "skills_injection", "timestamp"}
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_log = logging.getLogger("werewolf.diag.winrate")

PROJECT_ROOT = Path(__file__).resolve().parent
WINRATE_DIR = PROJECT_ROOT / "winrate"
HISTORY_PATH = WINRATE_DIR / "history.jsonl"


def _ensure_dir():
    WINRATE_DIR.mkdir(parents=True, exist_ok=True)


def record_game(jsonl_path: str, winner: str, total_rounds: int,
                players: List[Dict], skills_injection: Optional[Dict] = None) -> None:
    """记录一局游戏结果到history.jsonl"""
    _ensure_dir()
    record = {
        "jsonl_path": str(jsonl_path),
        "winner": winner,
        "total_rounds": total_rounds,
        "players": players,
        "skills_injection": skills_injection or {},
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    _log.info(f"Recorded game: winner={winner}, rounds={total_rounds}")


def load_history() -> List[Dict]:
    """加载全部历史记录"""
    if not HISTORY_PATH.exists():
        return []
    records = []
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _is_werewolf(role: str) -> bool:
    return role in ("狼人", "间谍")


def stats(group_by: str = "faction") -> Dict[str, Dict]:
    """统计胜率，按指定维度分组

    group_by: "faction" | "role" | "skills" | "version"
    Returns: {group_key: {"wins": N, "total": N, "winrate": float}}
    """
    history = load_history()
    if not history:
        return {}

    result: Dict[str, Dict] = {}

    for rec in history:
        winner = rec.get("winner", "")
        players = rec.get("players", [])
        skills = rec.get("skills_injection", {})
        injected_seats = set(skills.get("injected_seats", []))

        if group_by == "faction":
            for p in players:
                role = p.get("role", "未知")
                faction = "间谍" if _is_werewolf(role) else "公司"
                if faction not in result:
                    result[faction] = {"wins": 0, "total": 0}
                result[faction]["total"] += 1
                if (winner == "狼人" and faction == "间谍") or \
                   (winner == "公司" and faction == "公司"):
                    result[faction]["wins"] += 1

        elif group_by == "role":
            for p in players:
                role = p.get("role", "未知")
                if role not in result:
                    result[role] = {"wins": 0, "total": 0}
                result[role]["total"] += 1
                player_faction = "间谍" if _is_werewolf(role) else "公司"
                if winner == player_faction:
                    result[role]["wins"] += 1

        elif group_by == "skills":
            skills_version = skills.get("skills_version", "none")
            for p in players:
                seat = p.get("seat_num", 0)
                group = f"skills_{skills_version}" if seat in injected_seats else "baseline"
                if group not in result:
                    result[group] = {"wins": 0, "total": 0}
                result[group]["total"] += 1
                role = p.get("role", "未知")
                player_faction = "间谍" if _is_werewolf(role) else "公司"
                if winner == player_faction:
                    result[group]["wins"] += 1

        elif group_by == "version":
            skills_version = skills.get("skills_version", "none")
            if skills_version not in result:
                result[skills_version] = {"wins": 0, "total": 0}
            result[skills_version]["total"] += 1
            if winner in ("公司", "狼人"):
                result[skills_version]["wins"] += 1

    # 计算胜率
    for key in result:
        total = result[key]["total"]
        wins = result[key]["wins"]
        result[key]["winrate"] = wins / total if total > 0 else 0.0

    return result


def skills_impact() -> Dict:
    """对比skills注入组 vs 基线组胜率"""
    s = stats(group_by="skills")
    if not s:
        return {"message": "无数据"}

    baseline = {k: v for k, v in s.items() if k.startswith("baseline")}
    skills_groups = {k: v for k, v in s.items() if k.startswith("skills_")}

    if not baseline or not skills_groups:
        return {"message": "需要同时有skills组和baseline组数据", "stats": s}

    baseline_wr = sum(v["wins"] for v in baseline.values()) / \
                  max(sum(v["total"] for v in baseline.values()), 1)
    skills_wr = sum(v["wins"] for v in skills_groups.values()) / \
                max(sum(v["total"] for v in skills_groups.values()), 1)

    return {
        "baseline_winrate": round(baseline_wr, 4),
        "skills_winrate": round(skills_wr, 4),
        "delta": round(skills_wr - baseline_wr, 4),
        "baseline_total": sum(v["total"] for v in baseline.values()),
        "skills_total": sum(v["total"] for v in skills_groups.values()),
        "detail": s,
    }


def compare_versions(v1: str, v2: str) -> Dict:
    """对比两个skills版本的胜率"""
    s = stats(group_by="skills")
    key1 = f"skills_{v1}"
    key2 = f"skills_{v2}"

    data1 = s.get(key1, {"wins": 0, "total": 0, "winrate": 0.0})
    data2 = s.get(key2, {"wins": 0, "total": 0, "winrate": 0.0})

    return {
        v1: data1,
        v2: data2,
        "delta": round(data2["winrate"] - data1["winrate"], 4),
    }


def print_stats(group_by: str = "faction"):
    """打印胜率统计"""
    s = stats(group_by=group_by)
    if not s:
        print("暂无数据")
        return

    print(f"\n=== 胜率统计（按{group_by}分组）===")
    for key, data in sorted(s.items()):
        wr = data.get("winrate", 0.0)
        print(f"  {key}: {data['wins']}/{data['total']} = {wr:.1%}")

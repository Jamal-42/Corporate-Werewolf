# -*- coding: utf-8 -*-
"""批量运行器 - 顺序执行多局游戏并聚合统计"""
import asyncio
import argparse
import json
import logging
import os
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger("werewolf.diag.batch")


async def run_single_game(game_idx: int, player_count: int, prompt_version: str,
                          log_dir: str, skills_version: Optional[str] = None,
                          skills_targets: str = "all") -> Dict[str, Any]:
    """运行单局游戏并返回结果摘要"""
    from main_cn import OfficeWerewolfGame
    from game_logger import JSONGameLogger

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path = f"{log_dir}/game_{game_idx:03d}_{player_count}p_{timestamp}.jsonl"
    logger = JSONGameLogger(jsonl_path)

    game = OfficeWerewolfGame(logger=logger, prompt_version=prompt_version,
                              skills_version=skills_version,
                              skills_targets=skills_targets)
    try:
        await game.run_game(player_count)
    finally:
        logger.close()

    result = {
        "game_idx": game_idx,
        "jsonl_path": jsonl_path,
        "player_count": player_count,
        "prompt_version": prompt_version,
        "skills_version": skills_version,
    }

    # 从jsonl文件中提取结局
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                event = json.loads(line.strip())
                if event.get("event_type") == "game_over":
                    result["winner"] = event.get("winner", "未知")
                    result["total_rounds"] = event.get("total_rounds", 0)
                    result["survivors"] = event.get("survivors", [])
    except Exception:
        pass

    return result


async def run_batch(num_games: int, player_count: int, prompt_version: str,
                    log_dir: str, skills_version: Optional[str] = None,
                    skills_targets: str = "all") -> List[Dict[str, Any]]:
    """顺序执行多局游戏（禁止并发）"""
    results = []
    for i in range(1, num_games + 1):
        _log.info(f"{'='*40}")
        _log.info(f"开始第 {i}/{num_games} 局游戏")
        _log.info(f"{'='*40}")
        result = await run_single_game(i, player_count, prompt_version, log_dir,
                                       skills_version, skills_targets)
        results.append(result)
        _log.info(f"第 {i} 局结束：{result.get('winner', '未知')}")
    return results


def aggregate_stats(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """聚合多局统计"""
    total = len(results)
    winners = [r.get("winner", "未知") for r in results]
    company_wins = sum(1 for w in winners if "公司" in w)
    spy_wins = sum(1 for w in winners if "间谍" in w)
    rounds = [r.get("total_rounds", 0) for r in results if r.get("total_rounds")]

    return {
        "total_games": total,
        "company_wins": company_wins,
        "spy_wins": spy_wins,
        "company_win_rate": round(company_wins / total, 4) if total else 0,
        "spy_win_rate": round(spy_wins / total, 4) if total else 0,
        "avg_rounds": round(statistics.mean(rounds), 2) if rounds else 0,
        "min_rounds": min(rounds) if rounds else 0,
        "max_rounds": max(rounds) if rounds else 0,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="批量运行职场狼人杀对局")
    parser.add_argument("--num-games", type=int, default=3, help="运行局数（顺序执行）")
    parser.add_argument("--players", type=int, default=12, choices=(6, 9, 12))
    parser.add_argument("--prompt-version", type=str, default="v2")
    parser.add_argument("--log-dir", type=str, default="exports/batch")
    parser.add_argument("--skills-version", type=str, default=None, help="Skills版本")
    parser.add_argument("--skills-targets", type=str, default="all", help="Skills注入目标")
    args = parser.parse_args()

    os.makedirs(args.log_dir, exist_ok=True)

    from logging_config import setup_tracing
    setup_tracing(trace_path=f"{args.log_dir}/batch_trace.jsonl")

    results = asyncio.run(run_batch(
        args.num_games, args.players, args.prompt_version, args.log_dir,
        args.skills_version, args.skills_targets,
    ))

    stats = aggregate_stats(results)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats_path = f"{args.log_dir}/batch_stats_{timestamp}.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    _log.info(f"{'='*40}")
    _log.info(f"批量统计结果（{stats['total_games']}局）")
    _log.info(f"公司阵营胜率：{stats['company_win_rate']:.2%}（{stats['company_wins']}胜）")
    _log.info(f"间谍阵营胜率：{stats['spy_win_rate']:.2%}（{stats['spy_wins']}胜）")
    _log.info(f"平均轮数：{stats['avg_rounds']}")
    _log.info(f"统计已保存：{stats_path}")


if __name__ == "__main__":
    main()

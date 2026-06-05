# -*- coding: utf-8 -*-
"""A/B实验框架 - 对比两个版本的游戏表现

支持三种A/B对比模式:
1. Prompt版本对比: version_a=v2 vs version_b=v3 (skills均为None)
2. Skills版本对比: --skills-version-a evo_1 vs --skills-version-b evo_2 (prompt相同)
3. 混合对比: prompt+skills同时不同

流程：A/B版本各跑N局（顺序执行，不并发） → LLM Judge评分 → t-test/chi-squared统计检验 → 对比报告
"""
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


def t_test(a: List[float], b: List[float]) -> Dict[str, Any]:
    """独立样本t检验（简化实现，不依赖scipy）"""
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return {"test": "t-test", "significant": False, "note": "样本量不足(需>=2)"}

    mean_a, mean_b = statistics.mean(a), statistics.mean(b)
    var_a = statistics.variance(a) if n1 >= 2 else 0
    var_b = statistics.variance(b) if n2 >= 2 else 0

    pooled_se = ((var_a / n1) + (var_b / n2)) ** 0.5
    if pooled_se == 0:
        return {"test": "t-test", "significant": mean_a != mean_b, "t_stat": 0}

    t_stat = (mean_a - mean_b) / pooled_se
    df = n1 + n2 - 2

    # 近似p值（使用简化的临界值表）
    critical_005 = {1: 12.71, 2: 4.30, 5: 2.57, 10: 2.23, 20: 2.09, 30: 2.04, 60: 2.00}
    closest_df = min(critical_005.keys(), key=lambda x: abs(x - df))
    critical = critical_005[closest_df]
    significant = abs(t_stat) > critical

    return {
        "test": "t-test",
        "t_stat": round(t_stat, 4),
        "df": df,
        "mean_a": round(mean_a, 2),
        "mean_b": round(mean_b, 2),
        "diff": round(mean_a - mean_b, 2),
        "significant_at_005": significant,
    }


def chi_squared(observed: List[int], expected: List[int]) -> Dict[str, Any]:
    """卡方检验（胜率对比）"""
    chi2 = sum((o - e) ** 2 / e for o, e in zip(observed, expected) if e > 0)
    # 简化：1自由度下 chi2 > 3.84 = p<0.05
    return {
        "test": "chi-squared",
        "chi2_stat": round(chi2, 4),
        "significant_at_005": chi2 > 3.84,
    }


async def run_version_games(
    version: str,
    num_games: int,
    player_count: int,
    log_dir: str,
    skills_version: Optional[str] = None,
    skills_targets: str = "all",
) -> List[Dict[str, Any]]:
    """运行某个版本的N局游戏"""
    from batch_runner import run_batch
    return await run_batch(num_games, player_count, version, log_dir,
                           skills_version, skills_targets)


def evaluate_version(
    log_dir: str,
    version: str,
    enable_llm_judge: bool = False,
) -> Dict[str, Any]:
    """评测某个版本的所有对局"""
    from evaluation_cn import evaluate_log

    reports = []
    scores = []
    company_wins = 0
    spy_wins = 0

    log_path = Path(log_dir)
    for jsonl_file in log_path.glob(f"*{version}*.jsonl"):
        try:
            report = evaluate_log(
                path=jsonl_file,
                agent_version=version,
                enable_llm_judge=enable_llm_judge,
            )
            reports.append(report)
            scores.append(report["summary"]["overall_score"])
            winner = report.get("source_file", "")
            if "公司" in winner:
                company_wins += 1
            elif "间谍" in winner:
                spy_wins += 1
        except Exception as e:
            _log.warning(f"评测文件 {jsonl_file} 失败: {e}")

    return {
        "version": version,
        "num_games": len(reports),
        "avg_score": round(statistics.mean(scores), 2) if scores else 0,
        "company_wins": company_wins,
        "spy_wins": spy_wins,
        "company_win_rate": round(company_wins / max(company_wins + spy_wins, 1), 4),
        "scores": scores,
        "reports": reports,
    }


def compare_versions(
    version_a_data: Dict[str, Any],
    version_b_data: Dict[str, Any],
) -> Dict[str, Any]:
    """对比两个版本的表现，进行统计检验"""
    scores_a = version_a_data.get("scores", [])
    scores_b = version_b_data.get("scores", [])

    # t检验：综合得分对比
    score_test = t_test(scores_a, scores_b)

    # 卡方检验：胜率对比
    total_a = version_a_data.get("company_wins", 0) + version_a_data.get("spy_wins", 0)
    total_b = version_b_data.get("company_wins", 0) + version_b_data.get("spy_wins", 0)
    if total_a > 0 and total_b > 0:
        expected_a = total_a * (version_a_data["company_wins"] + version_b_data["company_wins"]) / (total_a + total_b)
        expected_b = total_b * (version_a_data["company_wins"] + version_b_data["company_wins"]) / (total_a + total_b)
        win_test = chi_squared(
            [version_a_data["company_wins"], version_b_data["company_wins"]],
            [expected_a, expected_b],
        )
    else:
        win_test = {"test": "chi-squared", "note": "数据不足"}

    return {
        "version_a": version_a_data["version"],
        "version_b": version_b_data["version"],
        "score_comparison": score_test,
        "win_rate_comparison": win_test,
        "conclusion": _generate_conclusion(score_test, win_test, version_a_data, version_b_data),
    }


def _generate_conclusion(
    score_test: Dict, win_test: Dict,
    a: Dict[str, Any], b: Dict[str, Any],
) -> str:
    """生成对比结论"""
    a_ver, b_ver = a["version"], b["version"]
    diff = a.get("avg_score", 0) - b.get("avg_score", 0)

    if score_test.get("significant_at_005"):
        better = a_ver if diff > 0 else b_ver
        return f"统计显著：{better}版本综合得分更高（差异={diff:+.2f}，p<0.05）"
    else:
        return f"统计不显著：{a_ver}({a.get('avg_score', 0):.2f}) vs {b_ver}({b.get('avg_score', 0):.2f})，需更多对局"


async def run_ab_experiment(
    version_a: str,
    version_b: str,
    num_games: int,
    player_count: int = 12,
    enable_llm_judge: bool = False,
    skills_version_a: Optional[str] = None,
    skills_version_b: Optional[str] = None,
    skills_targets: str = "all",
) -> Dict[str, Any]:
    """运行A/B实验

    支持两种A/B对比模式:
    1. Prompt版本对比: version_a/v2 vs version_b/v3 (skills均为None)
    2. Skills版本对比: skills_version_a/evo_1 vs skills_version_b/evo_2 (prompt相同)
    3. 混合对比: prompt+skills同时不同
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = f"exports/ab_{version_a}_vs_{version_b}_{timestamp}"

    # 顺序执行A版本
    _log.info(f"运行 {version_a} 版本 {num_games} 局... (skills={skills_version_a or 'none'})")
    await run_version_games(version_a, num_games, player_count, log_dir,
                            skills_version_a, skills_targets)

    # 顺序执行B版本
    _log.info(f"运行 {version_b} 版本 {num_games} 局... (skills={skills_version_b or 'none'})")
    await run_version_games(version_b, num_games, player_count, log_dir,
                            skills_version_b, skills_targets)

    # 评测两个版本
    a_data = evaluate_version(log_dir, version_a, enable_llm_judge)
    b_data = evaluate_version(log_dir, version_b, enable_llm_judge)

    # 统计对比
    comparison = compare_versions(a_data, b_data)

    # 保存报告
    report_path = Path(log_dir) / f"ab_report_{timestamp}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)

    _log.info(f"A/B实验报告已保存：{report_path}")
    _log.info(f"结论：{comparison['conclusion']}")

    return comparison


def main():
    parser = argparse.ArgumentParser(description="职场狼人杀A/B实验")
    parser.add_argument("--version-a", type=str, default="v2", help="A版本")
    parser.add_argument("--version-b", type=str, default="v3", help="B版本")
    parser.add_argument("--num-games", type=int, default=3, help="每版本运行局数")
    parser.add_argument("--players", type=int, default=12, choices=(6, 9, 12))
    parser.add_argument("--enable-llm-judge", action="store_true", help="启用LLM Judge评分")
    parser.add_argument("--skills-version-a", type=str, default=None, help="A版本的Skills版本")
    parser.add_argument("--skills-version-b", type=str, default=None, help="B版本的Skills版本")
    parser.add_argument("--skills-targets", type=str, default="all", help="Skills注入目标")
    args = parser.parse_args()

    asyncio.run(run_ab_experiment(
        args.version_a, args.version_b,
        args.num_games, args.players,
        args.enable_llm_judge,
        skills_version_a=args.skills_version_a,
        skills_version_b=args.skills_version_b,
        skills_targets=args.skills_targets,
    ))


if __name__ == "__main__":
    main()

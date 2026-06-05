# -*- coding: utf-8 -*-
"""自进化循环 — 评测 → Skills生成 → 注入 → 再评测 → 循环

CLI:
  python evolution.py evolve --generations 5 --games-per-gen 3
  python evolution.py generate --from-report reports/xxx.json --version evo_2
  python evolution.py evaluate --version evo_3 --num-games 5
  python evolution.py history
  python evolution.py stats [--group-by faction|role|skills|version]
"""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from skills_agent.generator import SkillsGenerator
from skills_agent.skills_store import SkillsStore
from skills_agent.dispatcher import SkillsDispatcher
from winrate_tracker import (
    record_game, load_history, stats, skills_impact,
    compare_versions, print_stats,
)

_log = logging.getLogger("werewolf.diag.evolution")

PROJECT_ROOT = Path(__file__).resolve().parent
EVOLUTION_DIR = PROJECT_ROOT / "evolution"
EVOLUTION_HISTORY = EVOLUTION_DIR / "history.json"


def _ensure_dir():
    EVOLUTION_DIR.mkdir(parents=True, exist_ok=True)


def _load_evolution_history() -> List[Dict]:
    if not EVOLUTION_HISTORY.exists():
        return []
    with open(EVOLUTION_HISTORY, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save_evolution_history(history: List[Dict]):
    _ensure_dir()
    with open(EVOLUTION_HISTORY, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def generate_skills(report_path: str, version: str, use_llm: bool = True) -> Dict[str, str]:
    """从评测报告生成Skills

    Args:
        report_path: 评测报告JSON文件路径
        version: 新Skills版本号
        use_llm: 是否使用LLM精炼（默认True，LLM失败时自动降级为模板填充）
    """
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    store = SkillsStore()
    gen = SkillsGenerator(store=store, use_llm=use_llm)
    results = gen.generate_from_report(report, version, report_path)
    _log.info(f"Generated skills v{version}: {list(results.keys())}")
    return results


def _run_single_game(player_count: int, skills_version: Optional[str],
                     skills_targets: str) -> Dict:
    """运行单局游戏，返回结果摘要"""
    from main_cn import OfficeWerewolfGame
    from prompt_logger import CombinedLogger
    from logging_config import setup_logging, get_logger

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = f"exports/evo_game_{player_count}p_{timestamp}"
    txt_path = base + ".txt"
    log_path = base + ".log"
    jsonl_path = base + ".jsonl"

    setup_logging(narration_path=txt_path, diagnostic_path=log_path, level="WARNING")

    logger = CombinedLogger(jsonl_path)
    game = OfficeWerewolfGame(
        logger=logger,
        skills_version=skills_version,
        skills_targets=skills_targets,
    )

    try:
        asyncio.run(game.run_game(player_count))
    finally:
        logger.close()

    # 从JSONL解析结果
    winner = "未知"
    total_rounds = 0
    players = []
    skills_injection = {}

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if event.get("event_type") == "game_over":
                winner = event.get("winner", "未知")
                total_rounds = event.get("total_rounds", 0)
                survivors = event.get("survivors", [])
                skills_injection = event.get("skills_injection", {})
            elif event.get("event_type") == "game_init":
                players = event.get("players", [])

    # 记录到winrate
    record_game(jsonl_path, winner, total_rounds, players, skills_injection)

    return {
        "winner": winner,
        "total_rounds": total_rounds,
        "jsonl_path": jsonl_path,
        "skills_injection": skills_injection,
    }


def _evaluate_game(jsonl_path: str, enable_llm_judge: bool = True,
                   llm_sample_rate: float = 1.0) -> Optional[str]:
    """对单局游戏运行评测，返回报告JSON文件路径"""
    from evaluation_cn import evaluate_log, write_reports, REPORT_DIR
    report = evaluate_log(path=Path(jsonl_path), enable_llm_judge=enable_llm_judge,
                          llm_sample_rate=llm_sample_rate)
    if not report:
        return None
    json_path, md_path, html_path = write_reports(report, REPORT_DIR)
    _log.info(f"Evaluation report saved: {json_path}")
    return str(json_path)


def should_rollback(current_version: str, previous_version: str) -> bool:
    """判断是否应回滚：当前版本胜率未提升"""
    impact = skills_impact()
    if "message" in impact:
        return False

    s = stats(group_by="skills")
    cur_key = f"skills_{current_version}"
    prev_key = f"skills_{previous_version}"

    cur_wr = s.get(cur_key, {}).get("winrate", 0.0)
    prev_wr = s.get(prev_key, {}).get("winrate", 0.0)

    # 如果当前版本胜率低于前一版本超过0.5%，回滚
    return cur_wr < prev_wr - 0.005


class EvolutionLoop:
    """自进化循环"""

    def __init__(self, player_count: int = 12, games_per_gen: int = 3,
                 skills_targets: str = "all",
                 enable_llm_judge: bool = True,
                 use_llm: bool = True):
        self.player_count = player_count
        self.games_per_gen = games_per_gen
        self.skills_targets = skills_targets
        self.enable_llm_judge = enable_llm_judge
        self.use_llm = use_llm
        self.store = SkillsStore()

    def run(self, generations: int = 5) -> Dict:
        """运行进化循环

        每代：
        1. 用当前版本skills运行N局
        2. 评测
        3. 生成新版本skills
        4. 对比胜率，决定保留或回滚
        """
        _ensure_dir()
        evo_history = _load_evolution_history()

        # 确定起始版本
        current_version = evo_history[-1]["version"] if evo_history else None
        if not current_version:
            # 检查是否已有skills版本
            versions = self.store.list_versions()
            if versions:
                current_version = versions[-1]
            else:
                # 需要先从评测报告生成初始版本
                _log.info("无现有skills版本，需要先运行 generate 或提供评测报告")
                return {"error": "no existing skills version, run generate first"}

        results = {
            "generations": [],
            "final_version": current_version,
        }

        for gen in range(generations):
            gen_start = datetime.now().isoformat(timespec="seconds")
            _log.info(f"=== Generation {gen + 1}/{generations} (version: {current_version}) ===")

            # 1. 运行N局游戏
            game_results = []
            for i in range(self.games_per_gen):
                _log.info(f"  Game {i + 1}/{self.games_per_gen}")
                result = _run_single_game(
                    self.player_count, current_version, self.skills_targets)
                game_results.append(result)

            # 2. 评测最新一局
            latest_jsonl = game_results[-1]["jsonl_path"]
            report_path = _evaluate_game(latest_jsonl,
                                         enable_llm_judge=self.enable_llm_judge)

            # 3. 生成新版本skills
            prev_version = current_version
            new_version = self.store.get_next_version()

            if report_path:
                generate_skills(report_path, new_version, use_llm=self.use_llm)
            else:
                _log.warning(f"评测失败，跳过skills生成 (gen {gen + 1})")
                new_version = current_version

            # 4. 对比胜率
            if new_version != current_version:
                rollback = should_rollback(new_version, current_version)
                if rollback:
                    _log.info(f"  胜率未提升，回滚到 {current_version}")
                    self.store.delete_version(new_version)
                    final_version = current_version
                else:
                    _log.info(f"  胜率提升，采用 {new_version}")
                    final_version = new_version
                    current_version = new_version
            else:
                final_version = current_version

            gen_record = {
                "generation": gen + 1,
                "started_at": gen_start,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "prev_version": prev_version,
                "new_version": new_version,
                "final_version": final_version,
                "games_played": len(game_results),
                "game_results": game_results,
                "report_path": report_path,
            }
            evo_history.append(gen_record)
            _save_evolution_history(evo_history)
            results["generations"].append(gen_record)
            results["final_version"] = final_version

        return results


def cmd_generate(args):
    """从评测报告生成Skills"""
    use_llm = not args.no_llm
    results = generate_skills(args.from_report, args.version, use_llm=use_llm)
    print(f"Generated skills v{args.version} (LLM={'on' if use_llm else 'off'}): {list(results.keys())}")
    for role, content in results.items():
        print(f"  {role}: {len(content)} chars")


def cmd_evolve(args):
    """运行进化循环"""
    use_llm = not args.no_llm
    loop = EvolutionLoop(
        player_count=args.players,
        games_per_gen=args.games_per_gen,
        skills_targets=args.skills_targets,
        enable_llm_judge=args.enable_llm_judge,
        use_llm=use_llm,
    )
    print(f"进化配置: LLM评测={'on' if args.enable_llm_judge else 'off'}, "
          f"LLM精炼Skills={'on' if use_llm else 'off'}")
    results = loop.run(generations=args.generations)
    if "error" in results:
        print(f"Error: {results['error']}")
        sys.exit(1)

    print(f"\n=== 进化完成 ===")
    print(f"最终版本: {results['final_version']}")
    for gen in results["generations"]:
        print(f"  Gen {gen['generation']}: {gen['prev_version']} -> {gen['final_version']}")


def cmd_evaluate(args):
    """用指定skills版本运行评测局"""
    for i in range(args.num_games):
        print(f"Game {i + 1}/{args.num_games}")
        result = _run_single_game(args.players, args.version, args.targets)
        print(f"  Winner: {result['winner']}, Rounds: {result['total_rounds']}")


def cmd_history(args):
    """查看进化历史"""
    history = _load_evolution_history()
    if not history:
        print("暂无进化历史")
        return

    for rec in history:
        print(f"Gen {rec.get('generation', '?')}: "
              f"{rec.get('prev_version', '?')} -> {rec.get('final_version', '?')} "
              f"({rec.get('games_played', 0)} games)")


def cmd_stats(args):
    """查看胜率统计"""
    print_stats(group_by=args.group_by)
    if args.group_by == "skills" or args.all:
        impact = skills_impact()
        if "message" not in impact:
            print(f"\nSkills影响: baseline={impact['baseline_winrate']:.1%} "
                  f"skills={impact['skills_winrate']:.1%} "
                  f"delta={impact['delta']:+.1%}")


def main():
    parser = argparse.ArgumentParser(description="Skills自进化循环")
    sub = parser.add_subparsers(dest="command")

    # generate
    gen_p = sub.add_parser("generate", help="从评测报告生成Skills")
    gen_p.add_argument("--from-report", required=True, help="评测报告JSON路径")
    gen_p.add_argument("--version", required=True, help="版本号（如evo_2）")
    gen_p.add_argument("--no-llm", action="store_true", help="不使用LLM精炼Skills（仅模板填充）")

    # evolve
    evo_p = sub.add_parser("evolve", help="运行进化循环")
    evo_p.add_argument("--generations", type=int, default=5, help="进化代数")
    evo_p.add_argument("--games-per-gen", type=int, default=3, help="每代游戏数")
    evo_p.add_argument("--players", type=int, default=12, help="玩家数")
    evo_p.add_argument("--skills-targets", type=str, default="all", help="Skills注入目标")
    evo_p.add_argument("--enable-llm-judge", action="store_true", help="评测时启用LLM Judge深度评分")
    evo_p.add_argument("--no-llm", action="store_true", help="Skills生成时不使用LLM精炼")

    # evaluate
    eval_p = sub.add_parser("evaluate", help="用指定skills版本运行评测局")
    eval_p.add_argument("--version", required=True, help="Skills版本号")
    eval_p.add_argument("--num-games", type=int, default=3, help="游戏数")
    eval_p.add_argument("--players", type=int, default=12, help="玩家数")
    eval_p.add_argument("--targets", type=str, default="all", help="Skills注入目标")

    # history
    sub.add_parser("history", help="查看进化历史")

    # stats
    stats_p = sub.add_parser("stats", help="查看胜率统计")
    stats_p.add_argument("--group-by", type=str, default="faction",
                         choices=["faction", "role", "skills", "version"])
    stats_p.add_argument("--all", action="store_true", help="显示所有统计")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from dotenv import load_dotenv
    load_dotenv()

    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "evolve":
        cmd_evolve(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()

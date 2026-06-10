# -*- coding: utf-8 -*-
"""多维评测与复盘：评价发言、投票、技能决策，并定位 bad case。"""

from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.role_mapping import ROLE_ALIASES, VILLAGER_TEAM, normalize_role
from shared.data_models import DecisionEvent, Finding
from shared.parsing_utils import read_text_auto
from logging_config import setup_logging

_log = logging.getLogger("werewolf.diag.eval")

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_LOG = PROJECT_ROOT / "game_log.txt"
REPORT_DIR = PROJECT_ROOT / "reports"

EVIDENCE_WORDS = ["因为", "所以", "证据", "逻辑", "矛盾", "投票", "发言", "查验", "身份", "行为", "推断", "怀疑"]
HEDGE_WORDS = ["可能", "也许", "感觉", "不确定", "随便", "盲投"]


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def mean(values: list[float], default: float = 0.0) -> float:
    return round(statistics.mean(values), 2) if values else default


def split_names(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[、,，\s]+", text) if item.strip()]


def should_skip_plain_line(line: str) -> bool:
    return (
        line.startswith("欢迎来到")
        or line.startswith("可选局数")
        or line.startswith("请选择人数")
        or line.startswith("游戏设置完成")
        or line.startswith("开始设置")
        or line.startswith("===")
        or line.startswith("Traceback")
        or line.startswith("File ")
    )


def extract_json_from_text(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    json_text = text[start : end + 1].replace("\\\n", "\n").replace("\\    ", "    ").replace("\\}", "}")
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        return None


def detect_category(payload: dict[str, Any]) -> tuple[str, str, str | None, str]:
    if "vote" in payload:
        return "vote", "投票", payload.get("vote"), payload.get("reason") or ""
    if "target" in payload and "kill_strategy" in payload:
        return "skill", "间谍窃取", payload.get("target"), payload.get("kill_strategy") or ""
    if "target" in payload and "check_reason" in payload:
        return "skill", "HR总监背调", payload.get("target"), payload.get("check_reason") or ""
    if "target" in payload and "guard_reason" in payload:
        return "skill", "安保主管加密保护", payload.get("target"), payload.get("guard_reason") or ""
    if "use_antidote" in payload or "use_poison" in payload:
        action = "CEO挽留" if payload.get("use_antidote") else "CEO辞退" if payload.get("use_poison") else "CEO用权"
        return "skill", action, payload.get("target_name"), payload.get("action_reason") or ""
    if "shoot" in payload:
        return "skill", "法务总监诉讼", payload.get("target"), payload.get("shoot_reason") or ""
    if "reach_agreement" in payload:
        return "speech", "讨论结论", None, payload.get("key_evidence") or ""
    return "other", "结构化输出", payload.get("target"), ""


def parse_log_text(text: str) -> tuple[dict[str, str], list[str], list[DecisionEvent]]:
    roles: dict[str, str] = {}
    player_order: list[str] = []
    events: list[DecisionEvent] = []
    current_round: int | None = None
    phase = "开局"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    i = 0
    while i < len(lines):
        line = lines[i].replace("\ufeff", "").strip()
        if (
            not line
            or should_skip_plain_line(line)
            or line[0] in {'"', "'", "{", "}", "[", "]"}
            or "arguments validation error" in line.lower()
            or "validation error" in line.lower()
        ):
            i += 1
            continue
        round_match = re.search(r"第\s*(\d+)\s*(?:轮|夜|天)", line)
        if round_match:
            current_round = int(round_match.group(1))
        if any(word in line for word in ["夜降临", "天黑", "夜晚", "狼人请睁眼", "间谍请睁眼"]):
            phase = "夜晚"
        elif any(word in line for word in ["天亮", "例会", "发言", "讨论"]):
            phase = "白天讨论"
        elif "投票" in line:
            phase = "白天投票"

        for match in re.finditer(r"【(?P<name>[^】]+)】.*?(?:扮演|身份是|角色是)(?P<role>狼人|间谍|预言家|HR总监|女巫|CEO|猎人|法务总监|守护者|安保主管|村民)", line):
            name = match.group("name").strip()
            roles[name] = normalize_role(match.group("role"))
            if name not in player_order:
                player_order.append(name)
        # Also match seat-number format: 【1号】身份是间谍
        for match in re.finditer(r"【(?P<name>\d+号)】.*?(?:扮演|身份是|角色是)(?P<role>狼人|间谍|预言家|HR总监|女巫|CEO|猎人|法务总监|守护者|安保主管|村民)", line):
            name = match.group("name").strip()
            roles[name] = normalize_role(match.group("role"))
            if name not in player_order:
                player_order.append(name)
        if "参与者" in line:
            for name in split_names(re.split(r"参与者[：:]", line, maxsplit=1)[-1]):
                if name not in player_order:
                    player_order.append(name)

        speaker_match = re.match(r"^(?P<speaker>[^:：]{1,24})[:：]\s*(?P<content>.*)$", line)
        if not speaker_match:
            i += 1
            continue
        speaker = speaker_match.group("speaker").strip()
        content = speaker_match.group("content").strip()
        if (
            speaker in {"system", "系统", "游戏主持人"}
            or speaker.lower().startswith("system")
            or speaker.startswith(('"', "'"))
            or "存活玩家" in speaker
            or "存活员工" in speaker
        ):
            i += 1
            continue
        if speaker not in player_order:
            player_order.append(speaker)

        raw_content = content
        if content.startswith("{"):
            depth = content.count("{") - content.count("}")
            while depth > 0 and i + 1 < len(lines):
                i += 1
                raw_content += "\n" + lines[i]
                depth += lines[i].count("{") - lines[i].count("}")
        payload = extract_json_from_text(raw_content)
        if payload:
            category, action, target, reason = detect_category(payload)
            raw = json.dumps(payload, ensure_ascii=False)
        else:
            category, action, target, reason, raw = "speech", "公开发言", None, content, content
        events.append(DecisionEvent(len(events) + 1, current_round, phase, speaker, roles.get(speaker, "未知"), category, action, target, reason or "", raw, payload or {}))
        i += 1
    return roles, player_order, events


def score_speech(event: DecisionEvent, repeated_counter: Counter[str]) -> tuple[float, dict[str, float], list[tuple[str, str, str, float]]]:
    text = event.reason or event.raw
    length = len(text)
    evidence_hits = sum(text.count(word) for word in EVIDENCE_WORDS)
    hedge_hits = sum(text.count(word) for word in HEDGE_WORDS)
    score = 45 + min(length / 3, 25) + min(evidence_hits * 6, 24) - min(hedge_hits * 4, 16)
    if event.action == "讨论结论":
        score += min(float(event.metadata.get("confidence_level") or 0) * 2, 16)
    issues: list[tuple[str, str, str, float]] = []
    if length < 12:
        score -= 20
        issues.append(("发言过短", "发言缺少可追溯推理，评委难以判断决策原因。", "补充身份判断、证据来源和下一步策略。", -20))
    if repeated_counter[text] >= 3:
        score -= 35
        issues.append(("重复输出", "同一段内容重复出现，疑似结构化调用失败或上下文失控。", "收紧结构化输出 schema，并设置重试上限。", -35))
    if evidence_hits == 0 and length >= 20:
        issues.append(("缺少证据链", "发言有观点但没有引用发言、投票或技能信息。", "要求 Agent 使用“观点-证据-风险-行动”模板。", -12))
    return clamp(score), {"length": length, "evidence_hits": evidence_hits, "hedge_hits": hedge_hits}, issues


def score_vote(event: DecisionEvent, roles: dict[str, str]) -> tuple[float, dict[str, float], list[tuple[str, str, str, float]]]:
    voter_role, target_role = normalize_role(roles.get(event.player)), normalize_role(roles.get(event.target))
    reason_len = len(event.reason or "")
    suspicion = float(event.metadata.get("suspicion_level") or 0)
    score = 45 + min(reason_len / 2, 20) + min(suspicion * 2, 20)
    issues: list[tuple[str, str, str, float]] = []
    if not event.target:
        score -= 40
        issues.append(("无效投票", "投票没有给出目标。", "限制投票目标为存活玩家枚举，并为空值做兜底。", -40))
    if reason_len < 8:
        score -= 18
        issues.append(("投票理由不足", "投票没有解释关键依据。", "投票输出必须包含至少一个可验证证据。", -18))
    if voter_role in VILLAGER_TEAM and target_role in VILLAGER_TEAM:
        score -= 28
        issues.append(("好人误投好人", f"{event.player}（{voter_role}）投向 {event.target}（{target_role}）。", "优先交叉验证查验、发言矛盾和狼队收益，不要只凭情绪投票。", -28))
    if voter_role in VILLAGER_TEAM and target_role == "狼人":
        score += 18
    if voter_role == "狼人" and target_role == "狼人":
        score -= 20
        issues.append(("狼人内投风险", "狼人投向狼队友，若无明确倒钩收益会损害阵营胜率。", "只有在能换取长期身份收益时才倒钩。", -20))
    return clamp(score), {"reason_len": reason_len, "suspicion_level": suspicion}, issues


def score_skill(event: DecisionEvent, roles: dict[str, str], state: dict[str, Any]) -> tuple[float, dict[str, float], list[tuple[str, str, str, float]]]:
    target_role = normalize_role(roles.get(event.target))
    reason_len = len(event.reason or "")
    score = 55 + min(reason_len / 2, 20)
    issues: list[tuple[str, str, str, float]] = []
    if event.action == "间谍窃取":
        if target_role == "狼人":
            score -= 70
            issues.append(("间谍误窃队友", f"间谍目标是 {event.target}（间谍）。", "夜间目标应排除间谍队友，并优先窃取HR总监/CEO等高价值好人。", -70))
        elif target_role in {"预言家", "女巫", "猎人", "守护者"}:
            score += 15
    elif event.action == "HR总监背调":
        seen = state.setdefault("seer_targets", set())
        if event.target == event.player:
            score -= 60
            issues.append(("HR总监自背调", "HR总监浪费背调在自己身上。", "优先背调发言强势、票型异常或被多人争议的玩家。", -60))
        if event.target in seen:
            score -= 35
            issues.append(("重复背调", f"重复背调 {event.target}，信息增量不足。", "维护私有背调历史，下一轮避开已背调目标。", -35))
        seen.add(event.target)
    elif event.action == "安保主管加密保护":
        if event.target and event.target == state.get("last_guarded"):
            score -= 55
            issues.append(("安保主管连续保护同一人", f"连续保护 {event.target}，违反常见保护规则/收益很低。", "记录上一夜保护目标，并从候选列表中剔除。", -55))
        state["last_guarded"] = event.target
    elif event.action in {"CEO辞退", "CEO用权"} and event.metadata.get("use_poison") and target_role in VILLAGER_TEAM:
        score -= 45
        issues.append(("CEO辞退错好人", f"CEO辞退 {event.target}（{target_role}）。", "辞退信应保留给强间谍嫌疑或关键轮次，使用前结合票型和背调。", -45))
    elif event.action == "法务总监诉讼" and event.metadata.get("shoot") and target_role in VILLAGER_TEAM:
        score -= 50
        issues.append(("法务总监诉讼错好人", f"法务总监诉讼带走 {event.target}（{target_role}）。", "临终技能应优先带走背调查实、身份对质失败或票型最可疑的目标。", -50))
    if event.target == event.player and event.action not in {"CEO挽留", "CEO用权"}:
        score -= 20
        issues.append(("技能目标异常", "技能目标指向自己，通常信息增量或收益较低。", "为每个技能设置合法目标过滤器。", -20))
    if reason_len < 8:
        score -= 15
        issues.append(("技能理由不足", "技能决策缺少解释，无法复盘。", "每个技能输出 action_reason/check_reason/guard_reason。", -15))
    return clamp(score), {"reason_len": reason_len}, issues


def build_counterfactual(event: DecisionEvent, title: str, roles: dict[str, str]) -> str:
    wolves = [name for name, role in roles.items() if normalize_role(role) == "狼人"]
    specials = [name for name, role in roles.items() if normalize_role(role) in {"预言家", "女巫", "猎人", "守护者"}]
    if "误投" in title and wolves:
        return f"若 {event.player} 改投嫌疑更高的 {wolves[0]}，公司阵营可减少一次误出并提高下一轮信息密度。"
    if "自背调" in title and wolves:
        return f"若改查 {wolves[0]}，HR总监可产出背调查实信息，白天归票成功率显著提升。"
    if "误窃队友" in title and specials:
        return f"若间谍队改窃 {specials[0]}，可削弱公司技能链，而不是自损间谍坑。"
    if "辞退错" in title and wolves:
        return f"若CEO保留辞退信或辞退 {wolves[0]}，公司阵营可避免关键轮次减员。"
    if "诉讼错" in title and wolves:
        return f"若法务总监诉讼目标改为 {wolves[0]}，可用临终技能换掉间谍坑。"
    if "内投" in title:
        return f"若 {event.player} 改投非队友目标，可避免暴露间谍身份关联；倒钩需提前铺垫、收益需大于暴露风险。"
    if "投票理由不足" in title:
        return f"若 {event.player} 补充'因为X号第N轮发言与投票矛盾'等具体证据，可增强说服力并为后续复盘留据。"
    if "技能理由不足" in title:
        return f"若 {event.player} 输出完整的决策理由（如背调优先级排序、保护收益分析），评测系统可追溯决策质量。"
    if "发言过短" in title:
        return f"若 {event.player} 补充身份判断、证据来源和下一步策略，可提升发言信息密度和可追溯性。"
    if "重复输出" in title:
        return f"若收紧结构化输出 schema 并加入重试上限，可避免 {event.player} 陷入复读循环。"
    if "缺少证据链" in title:
        return f"若 {event.player} 引用具体发言序号或投票记录作为论据，可从'直觉判断'升级为'逻辑推断'。"
    if "目标异常" in title:
        return f"若 {event.player} 选择非自身目标，技能可产出更高信息增量或阵营收益。"
    return f"建议 {event.player} 在该决策中补充可追溯的证据链或选择信息增量更高的目标。"


def evaluate_events(roles: dict[str, str], events: list[DecisionEvent],
                     agent_version: str = "baseline",
                     enable_llm_judge: bool = False,
                     llm_sample_rate: float = 1.0,
                     jsonl_path: Path | None = None,
                     player_order: list[str] | None = None) -> dict[str, Any]:
    repeated_counter = Counter(event.reason or event.raw for event in events if event.category == "speech")
    state: dict[str, Any] = {}
    findings: list[Finding] = []
    dimension_scores: dict[str, list[float]] = defaultdict(list)
    player_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for event in events:
        if event.category == "speech":
            score, metrics, issues = score_speech(event, repeated_counter)
        elif event.category == "vote":
            score, metrics, issues = score_vote(event, roles)
        elif event.category == "skill":
            score, metrics, issues = score_skill(event, roles, state)
        else:
            score, metrics, issues = 55.0, {}, []
        event.score, event.metrics = score, metrics
        dimension_scores[event.category].append(score)
        player_scores[event.player][event.category].append(score)
        for title, evidence, recommendation, delta in issues:
            severity = "high" if delta <= -40 else "medium" if delta <= -20 else "low"
            findings.append(Finding(len(findings) + 1, severity, event.player, normalize_role(roles.get(event.player, event.role)), event.category, title, evidence, recommendation, build_counterfactual(event, title, roles), delta, event.round))
    leaderboard = []
    for player, by_dim in player_scores.items():
        # Skip non-seat identifiers (e.g. "间谍团队") in leaderboard
        if not (len(player) >= 2 and player[-1] == "号" and player[:-1].isdigit()):
            continue
        all_scores = [score for scores in by_dim.values() for score in scores]
        leaderboard.append({
            "player": player,
            "role": normalize_role(roles.get(player)),
            "agent_version": agent_version,
            "overall_score": mean(all_scores),
            "speech_score": mean(by_dim.get("speech", []), 0),
            "vote_score": mean(by_dim.get("vote", []), 0),
            "skill_score": mean(by_dim.get("skill", []), 0),
            "decision_count": len(all_scores),
            "critical_mistakes": sum(1 for f in findings if f.player == player and f.severity == "high"),
        })
    leaderboard.sort(key=lambda item: (item["overall_score"], -item["critical_mistakes"]), reverse=True)
    all_scores = [event.score for event in events]
    sorted_findings = sorted(
        (asdict(f) for f in findings),
        key=lambda item: {"high": 0, "medium": 1, "low": 2}[item["severity"]],
    )

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "agent_version": agent_version,
        "summary": {
            "overall_score": mean(all_scores),
            "decision_count": len(events),
            "player_count": len(player_order) if player_order else len(roles) or len({e.player for e in events}),
            "high_severity_mistakes": sum(1 for f in findings if f.severity == "high"),
            "medium_severity_mistakes": sum(1 for f in findings if f.severity == "medium"),
            "coverage": {key: len(values) for key, values in dimension_scores.items()},
        },
        "dimension_scores": {key: mean(values) for key, values in dimension_scores.items()},
        "roles": {k: v for k, v in roles.items() if len(k) >= 2 and k[-1] == "号" and k[:-1].isdigit()},
        "seat_characters": {k: v for k, v in roles.items() if not (len(k) >= 2 and k[-1] == "号" and k[:-1].isdigit())},
        "leaderboard": leaderboard,
        "findings": sorted_findings,
        "counterfactuals": [item["counterfactual"] for item in sorted_findings[:8]],
        "events": [asdict(event) for event in events],
    }

    # LLM Judge集成 — 使用新的eval_agent模块
    if enable_llm_judge:
        try:
            import asyncio
            from eval_agent import EvalJudge
            from eval_agent.score_integrator import integrate_scores
            if jsonl_path and jsonl_path.exists():
                judge = EvalJudge()
                llm_result = asyncio.run(judge.judge_game(
                    jsonl_path=str(jsonl_path),
                    sample_rate=llm_sample_rate,
                ))
                result = integrate_scores(result, llm_result)
            else:
                result["llm_judge_scores"] = {"error": "需要jsonl_path才能使用LLM Judge"}
        except Exception as e:
            result["llm_judge_scores"] = {"error": str(e)}

    return result


def _extract_jsonl_meta(jsonl_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """从 jsonl 的 game_init 事件中提取人设名和模型名"""
    personas: dict[str, str] = {}
    models: dict[str, str] = {}
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") == "game_init":
                for entry in event.get("character_role_map", []):
                    seat = entry.get("seat_num")
                    if not seat:
                        continue
                    key = f"{seat}号"
                    char_name = entry.get("character_name", "")
                    model_name = entry.get("model_name", "")
                    if char_name:
                        personas[key] = char_name
                    if model_name:
                        models[key] = model_name
                break
    return personas, models


def evaluate_log(path: Path | None = None, text: str | None = None,
                  agent_version: str = "baseline",
                  enable_llm_judge: bool = False,
                  llm_sample_rate: float = 1.0) -> dict[str, Any]:
    jsonl_path = None
    if text is None:
        path = path or DEFAULT_LOG
        if isinstance(path, str):
            path = Path(path)

        # 路径验证：不存在时尝试智能解析
        if not path.exists():
            # 尝试将纯数字解析为 exports/*.jsonl
            if path.suffix == "" and path.name.isdigit():
                candidate = PROJECT_ROOT / "exports" / f"{path.name}.jsonl"
                if candidate.exists():
                    _log.info(f"已将 '{path}' 解析为 {candidate}")
                    path = candidate
                else:
                    # 尝试模糊匹配
                    matches = list(PROJECT_ROOT.glob(f"exports/*{path.name}*.jsonl"))
                    if len(matches) == 1:
                        _log.info(f"已将 '{path}' 解析为 {matches[0]}")
                        path = matches[0]
                    elif len(matches) > 1:
                        print(f"错误：'{path}' 不存在，但找到多个匹配的日志文件：")
                        for m in matches:
                            print(f"  {m}")
                        print("请指定完整路径。")
                        sys.exit(1)
                    else:
                        print(f"错误：日志文件不存在：{path}")
                        print(f"提示：请使用完整路径，如 exports/game_12p_20260601_120000.jsonl")
                        print(f"      或使用 --demo-bad-case 运行内置示例")
                        sys.exit(1)
            else:
                print(f"错误：日志文件不存在：{path}")
                print(f"提示：请使用完整路径，如 exports/game_12p_20260601_120000.jsonl")
                print(f"      或使用 --demo-bad-case 运行内置示例")
                sys.exit(1)

        if path.is_dir():
            print(f"错误：'{path}' 是目录，不是文件。请指定具体的日志文件。")
            sys.exit(1)

        # 优先尝试 .jsonl 结构化解析
        if path.suffix == ".jsonl":
            jsonl_path = path
            try:
                from jsonl_parser import parse_log_jsonl
                roles, player_order, events = parse_log_jsonl(path)
                report = evaluate_events(roles, events, agent_version=agent_version,
                                      enable_llm_judge=enable_llm_judge,
                                      llm_sample_rate=llm_sample_rate,
                                      jsonl_path=jsonl_path,
                                      player_order=player_order)
                # 从 game_init 提取人设名和模型信息
                personas, models = _extract_jsonl_meta(path)
                if personas:
                    report["personas"] = personas
                if models:
                    report["models"] = models
                report["source_file"] = str(path)
                return report
            except Exception:
                pass  # 回退到 .txt 解析
        text = read_text_auto(path)
    roles, _players, events = parse_log_text(text)
    # 提取人设名
    personas: dict[str, str] = {}
    for line in text.splitlines():
        m = re.search(r"【(?P<seat>\d+号)】.*?职场人设是(?P<persona>[^。\s]+)", line)
        if m:
            personas[m.group("seat")] = m.group("persona")
    report = evaluate_events(roles, events, agent_version=agent_version,
                              enable_llm_judge=enable_llm_judge,
                              llm_sample_rate=llm_sample_rate,
                              jsonl_path=jsonl_path)
    if personas:
        report["personas"] = personas
    report["source_file"] = str(path) if path else "demo_bad_case"
    return report


def report_to_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 职场狼人杀 Agent 多维评测与复盘报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 来源日志：{report.get('source_file', 'unknown')}",
        f"- 综合得分：{summary['overall_score']}/100",
        f"- 决策数：{summary['decision_count']}，高危失误：{summary['high_severity_mistakes']}，中危失误：{summary['medium_severity_mistakes']}",
        "",
        "## 维度评分",
    ]
    for key, value in report.get("dimension_scores", {}).items():
        lines.append(f"- { {'speech': '发言', 'vote': '投票', 'skill': '技能', 'other': '其他'}.get(key, key) }：{value}/100")
    lines += ["", "## Leaderboard"]
    for idx, row in enumerate(report["leaderboard"], 1):
        lines.append(f"{idx}. {row['player']}（{row['role']}）：{row['overall_score']}分；发言 {row['speech_score']} / 投票 {row['vote_score']} / 技能 {row['skill_score']}；高危 {row['critical_mistakes']}")
    lines += ["", "## 关键失误复盘"]
    if not report["findings"]:
        lines.append("- 未发现明显失误；建议增加更多结构化决策日志以提升评测覆盖率。")
    for item in report["findings"][:12]:
        lines.append(f"- [{item['severity']}] 第{item.get('round') or '-'}轮 {item['player']}：{item['title']}。{item['evidence']} 建议：{item['recommendation']}")
        lines.append(f"  - 反事实：{item['counterfactual']}")
    return "\n".join(lines) + "\n"


def write_reports(report: dict[str, Any], output_dir: Path = REPORT_DIR) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    json_path = output_dir / f"evaluation_report_{stamp}.json"
    md_path = output_dir / f"evaluation_report_{stamp}.md"
    html_path = output_dir / f"dashboard_{stamp}.html"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(report_to_markdown(report), encoding="utf-8")
    try:
        from evaluation_dashboard import create_dashboard
        create_dashboard(report, str(html_path))
    except Exception as e:
        _log.warning(f"HTML dashboard generation failed: {e}")
        html_path = None
    return json_path, md_path, html_path


def demo_bad_case_log() -> str:
    return """
游戏主持人: 📢 【1号】你在这场职场狼人杀中扮演商业间谍，你的身份是间谍。你的职场人设是铁头哥。
游戏主持人: 📢 【2号】你在这场职场狼人杀中扮演HR总监，你的身份是预言家。你的职场人设是卷王。
游戏主持人: 📢 【3号】你在这场职场狼人杀中扮演CEO，你的身份是女巫。你的职场人设是PUA总裁。
游戏主持人: 📢 【4号】你在这场职场狼人杀中扮演法务总监，你的身份是猎人。你的职场人设是暴躁哥。
游戏主持人: 📢 【5号】你在这场职场狼人杀中扮演普通员工，你的身份是村民。你的职场人设是老油条。
游戏主持人: 📢 【6号】你在这场职场狼人杀中扮演普通员工，你的身份是村民。你的职场人设是小透明。
游戏主持人: 📢 职场狼人杀游戏开始！参与者：1号、2号、3号、4号、5号、6号
游戏主持人: 📢 🌙 第1夜降临，天黑请闭眼...
游戏主持人: 📢 间谍请睁眼，讨论窃取目标...
1号: {"target":"1号","kill_strategy":"随便窃取一个，先隐藏自己","team_coordination":"无"}
游戏主持人: 📢 HR总监请睁眼，选择背调目标...
2号: {"target":"2号","check_reason":"我想先确认自己是不是好人","priority_level":10}
游戏主持人: 📢 CEO请睁眼，决定是否使用技能...
3号: {"use_antidote":false,"use_poison":true,"target_name":"5号","action_reason":"感觉他话多"}
游戏主持人: 📢 法务总监被窃取出局，是否发起诉讼...
4号: {"shoot":true,"target":"6号","shoot_reason":"盲狙一下"}
游戏主持人: 📢 ☀️ 第1天天亮了，请大家睁眼...
游戏主持人: 📢 昨夜，4号领了大礼包离职，5号被CEO辞退。
游戏主持人: 📢 例会开始，请各位发言。存活员工：1号、2号、3号、6号
1号: 我觉得局势还不明朗，大家先观察观察吧。没什么好说的。
2号: 我是HR总监，昨晚背调了自己...呃...确认自己是好人。我建议大家先不要急着投票，等更多信息。
5号: 我觉得1号像好人。
6号: 随便吧。
游戏主持人: 📢 请投票选择要淘汰的员工
2号: {"vote":"3号","reason":"没有证据，感觉像间谍","suspicion_level":5}
5号: {"vote":"6号","reason":"他沉默","suspicion_level":4}
6号: {"vote":"5号","reason":"他说我沉默","suspicion_level":4}
1号: {"vote":"2号","reason":"HR总监背调自己太可疑了","suspicion_level":6}
3号: {"vote":"6号","reason":"小透明话最少，优先淘汰","suspicion_level":3}
游戏主持人: 📢 投票结果：6号以2票被投出，领大礼包走人。
游戏主持人: 📢 [游戏结束] 间谍阵营胜利！好人数量不足。
""".strip()


def _validate_log_path(value: str) -> Path:
    """Argparse type validator for --log: 已存在的路径直接通过，纯数字放行（由 evaluate_log 解析）"""
    p = Path(value)
    if p.exists():
        return p
    # 纯数字可能对应 exports/ 下的文件，放行让 evaluate_log 处理
    if p.suffix == "" and p.name.isdigit():
        return p
    raise argparse.ArgumentTypeError(f"日志文件不存在：{value}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="职场狼人杀 Agent 多维评测与复盘")
    parser.add_argument("--log", type=_validate_log_path, default=DEFAULT_LOG, help="要评测的对局日志")
    parser.add_argument("--output-dir", type=Path, default=REPORT_DIR, help="报告输出目录")
    parser.add_argument("--demo-bad-case", action="store_true", help="使用内置明显失误对局验证失误定位能力")
    parser.add_argument("--no-write", action="store_true", help="只打印摘要，不写报告文件")
    parser.add_argument("--agent-version", type=str, default="baseline", help="评测报告标记的agent版本号")
    parser.add_argument("--compare-versions", nargs=2, metavar=("V1", "V2"), help="对比两个版本的排行榜（需分别提供日志）")
    parser.add_argument("--enable-llm-judge", action="store_true", help="启用LLM Judge深度评分")
    parser.add_argument("--llm-sample-rate", type=float, default=1.0, help="LLM Judge采样率(0-1)，默认1.0=全量评分")
    parser.add_argument("--eval-model", type=str, default=None, help="覆盖评测模型名")
    parser.add_argument("--eval-sample-strategy", type=str, default="uniform", choices=["uniform", "critical_first", "role_balanced"], help="LLM Judge采样策略")
    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    setup_logging()

    # 加载.env文件确保API Key可用
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # 覆盖评测模型名
    if args.eval_model:
        import os
        os.environ["EVAL_MODEL_MODEL_NAME"] = args.eval_model

    report = evaluate_log(
        text=demo_bad_case_log() if args.demo_bad_case else None,
        path=None if args.demo_bad_case else args.log,
        agent_version=args.agent_version,
        enable_llm_judge=args.enable_llm_judge,
        llm_sample_rate=args.llm_sample_rate,
    )

    if args.compare_versions:
        v1_dir, v2_dir = args.compare_versions
        _log.info(f"对比模式：{v1_dir} vs {v2_dir}")
        v1_reports = []
        v2_reports = []
        for p in Path(v1_dir).glob("*.jsonl"):
            try:
                r = evaluate_log(path=p, agent_version=v1_dir)
                v1_reports.append(r)
            except Exception:
                pass
        for p in Path(v2_dir).glob("*.jsonl"):
            try:
                r = evaluate_log(path=p, agent_version=v2_dir)
                v2_reports.append(r)
            except Exception:
                pass
        if v1_reports and v2_reports:
            v1_avg = mean([r["summary"]["overall_score"] for r in v1_reports])
            v2_avg = mean([r["summary"]["overall_score"] for r in v2_reports])
            _log.info(f"{v1_dir} 平均分：{v1_avg} ({len(v1_reports)}局)")
            _log.info(f"{v2_dir} 平均分：{v2_avg} ({len(v2_reports)}局)")
            _log.info(f"差异：{v2_avg - v1_avg:+.2f}")
        else:
            _log.warning(f"未找到评测数据：{v1_dir}={len(v1_reports)}局, {v2_dir}={len(v2_reports)}局")

    if not args.no_write:
        json_path, md_path, html_path = write_reports(report, args.output_dir)
        _log.info(f"报告已生成：{json_path}")
        _log.info(f"报告已生成：{md_path}")
        if html_path:
            _log.info(f"Dashboard已生成：{html_path}")
    print(report_to_markdown(report))


if __name__ == "__main__":
    main()

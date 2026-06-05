# -*- coding: utf-8 -*-
"""Skills生成器 — 从评测报告提取弱点，生成多颗粒度角色Skills

处理流程：
1. 从 findings 提取每个角色的高/中危失误 + 反事实建议
2. 从 llm_judge_scores 按 game_stage × event_type 分组提取阶段化策略
3. 从 llm_judge_scores 提取 dimension_reasons（维度具体诊断）
4. 从 llm_aggregate 取维度弱项 + 策略分布 + 常见错误
5. 用模板填充（或LLM优化）生成角色Skills文件
6. 生成子文件（角色.阶段.事件类型.md）用于细粒度阶段注入
"""
import asyncio
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shared.role_mapping import normalize_role as _normalize_role
from skills_agent.skills_store import SkillsStore, ROLE_WORKPLACE, WORKPLACE_ROLE, ALL_ROLES
from skills_agent.templates import get_template

_log = logging.getLogger("werewolf.diag.skills")

TRAD_TO_WORK = ROLE_WORKPLACE
WORK_TO_TRAD = WORKPLACE_ROLE

STAGE_ORDER = {"early": 0, "mid": 1, "late": 2}


def _extract_player_findings(report: dict, player: str) -> List[dict]:
    findings = report.get("findings", [])
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    player_findings = [f for f in findings if f.get("player") == player]
    player_findings.sort(key=lambda f: severity_rank.get(f.get("severity", "low"), 2))
    return player_findings


def _extract_player_llm_scores(report: dict, player: str) -> List[dict]:
    llm = report.get("llm_judge_scores", [])
    if isinstance(llm, dict) and "error" in llm:
        return []
    return [s for s in llm if s.get("player") == player]


def _extract_role_weak_dims(report: dict, role_workplace: str) -> Dict[str, Dict]:
    agg = report.get("llm_aggregate", {}).get("comparison_units", {})
    weak = {}
    for key, unit in agg.items():
        if unit.get("role") != role_workplace:
            continue
        for dim_name, dim_stats in unit.get("dimension_scores", {}).items():
            mean = dim_stats.get("mean", 0)
            if mean < 55:
                weak[dim_name] = dim_stats
    return weak


def _extract_dimension_reasons(report: dict, player: str) -> Dict[str, str]:
    """从 llm_judge_scores 提取维度理由，取每个维度最具体的理由（最长的）"""
    llm = report.get("llm_judge_scores", [])
    if isinstance(llm, dict):
        return {}
    dim_reasons: Dict[str, List[str]] = defaultdict(list)
    for s in llm:
        if s.get("player") != player:
            continue
        reasons = s.get("dimension_reasons", {})
        if isinstance(reasons, dict):
            for dim, reason in reasons.items():
                if reason:
                    dim_reasons[dim].append(reason)
    # 每个维度取最长的理由（最具体）
    return {dim: max(reasons, key=len) for dim, reasons in dim_reasons.items() if reasons}


def _extract_event_type_scores(report: dict, player: str) -> Dict[str, Dict[str, List[float]]]:
    """按 event_type 分组提取 LLM 评分"""
    llm = report.get("llm_judge_scores", [])
    if isinstance(llm, dict):
        return {}
    result: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for s in llm:
        if s.get("player") != player:
            continue
        event_type = s.get("event_type", "speech")
        scores = s.get("llm_scores", {})
        if isinstance(scores, dict):
            for dim, score in scores.items():
                if isinstance(score, (int, float)):
                    result[event_type][dim].append(float(score))
    return dict(result)


def _extract_counterfactuals(report: dict, player: str) -> List[str]:
    """从 findings 提取反事实建议"""
    findings = report.get("findings", [])
    cfs = []
    for f in findings:
        if f.get("player") != player:
            continue
        cf = f.get("counterfactual", "")
        if cf:
            cfs.append(cf)
    return cfs


def _extract_game_impacts(report: dict, player: str) -> List[str]:
    """从 decision_tags 提取 game_impact 标签"""
    llm = report.get("llm_judge_scores", [])
    if isinstance(llm, dict):
        return []
    impacts = []
    for s in llm:
        if s.get("player") != player:
            continue
        tags = s.get("decision_tags", {})
        impact = tags.get("game_impact", "")
        if impact and impact != "中性":
            impacts.append(impact)
    return impacts


def _extract_strategy_distribution(report: dict, role_workplace: str) -> Dict[str, int]:
    """从 llm_aggregate.comparison_units 提取策略分布"""
    agg = report.get("llm_aggregate", {}).get("comparison_units", {})
    merged: Dict[str, int] = defaultdict(int)
    for key, unit in agg.items():
        if unit.get("role") != role_workplace:
            continue
        for strategy, count in unit.get("strategy_distribution", {}).items():
            if strategy:
                merged[strategy] += count
    return dict(merged)


def _extract_common_mistakes_agg(report: dict, role_workplace: str) -> List[str]:
    """从 llm_aggregate.comparison_units 提取常见错误"""
    agg = report.get("llm_aggregate", {}).get("comparison_units", {})
    all_mistakes: Dict[str, int] = defaultdict(int)
    for key, unit in agg.items():
        if unit.get("role") != role_workplace:
            continue
        for m in unit.get("common_mistakes", []):
            if m:
                all_mistakes[m] += 1
    return sorted(all_mistakes.keys(), key=lambda x: all_mistakes[x], reverse=True)[:5]


def _group_by_stage(llm_scores: List[dict]) -> Dict[str, List[dict]]:
    stages = defaultdict(list)
    for s in llm_scores:
        stage = s.get("game_stage", "mid")
        stages[stage].append(s)
    return dict(stages)


def _group_by_stage_and_event(llm_scores: List[dict]) -> Dict[str, Dict[str, List[dict]]]:
    """按 game_stage × event_type 双层分组"""
    result: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
    for s in llm_scores:
        stage = s.get("game_stage", "mid")
        event_type = s.get("event_type", "speech")
        result[stage][event_type].append(s)
    return {k: dict(v) for k, v in result.items()}


def _build_event_type_actions(stage: str, event_type: str, scores: List[dict], role: str) -> str:
    """按阶段×事件类型生成行动建议（含维度诊断、策略、反事实）"""
    lines = []
    seen = set()
    for s in scores:
        # 维度诊断
        dims = s.get("llm_scores", {})
        reasons = s.get("dimension_reasons", {})
        weak_dims = {k: v for k, v in dims.items() if isinstance(v, (int, float)) and v < 50}
        if weak_dims:
            for dim, score in sorted(weak_dims.items(), key=lambda x: x[1]):
                reason = reasons.get(dim, "")
                line = f"- {dim}({score:.0f}分)：{reason}" if reason else f"- {dim}({score:.0f}分)需提升"
                if line not in seen:
                    seen.add(line)
                    lines.append(line)
        # 策略与失误
        tags = s.get("decision_tags", {})
        if isinstance(tags, dict):
            if tags.get("strategy_used"):
                line = f"- 策略：{tags['strategy_used']}"
                if line not in seen:
                    seen.add(line)
                    lines.append(line)
            if tags.get("mistake_type"):
                line = f"- 规避：{tags['mistake_type']}"
                if line not in seen:
                    seen.add(line)
                    lines.append(line)
            impact = tags.get("game_impact", "")
            if impact and impact != "中性":
                line = f"- 影响：{impact}"
                if line not in seen:
                    seen.add(line)
                    lines.append(line)
        # 关键洞察
        if s.get("key_insight"):
            insight = s["key_insight"][:150]
            line = f"- 洞察：{insight}"
            if line not in seen:
                seen.add(line)
                lines.append(line)
        # 反事实
        if s.get("counterfactual"):
            cf = s["counterfactual"][:150]
            line = f"- 替代方案：{cf}"
            if line not in seen:
                seen.add(line)
                lines.append(line)
    if not lines:
        lines.append(f"- {stage}阶段{event_type}无特定问题记录，保持基本策略")
    return "\n".join(lines)


def _build_mistakes(findings: List[dict]) -> str:
    if not findings:
        return "- 暂无特定失误记录"
    lines = []
    seen = set()
    for f in findings[:8]:
        sev = f.get("severity", "low")
        title = f.get("title", "未知")
        rec = f.get("recommendation", "")
        line = f"- [{sev}] {title}。{rec}"
        if line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)


def _build_counterfactuals(findings: List[dict], counterfactuals: List[str]) -> str:
    """生成反事实建议文本"""
    lines = []
    seen = set()
    # 从 findings 提取
    for f in findings[:8]:
        cf = f.get("counterfactual", "")
        if cf and cf not in seen:
            seen.add(cf)
            lines.append(f"- {cf[:200]}")
    # 从额外提取的 counterfactuals
    for cf in counterfactuals:
        if cf and cf not in seen:
            seen.add(cf)
            lines.append(f"- {cf[:200]}")
    if not lines:
        return "- 暂无反事实建议"
    return "\n".join(lines)


def _build_weak_dims(weak: Dict[str, Dict], dimension_reasons: Dict[str, str] = None) -> str:
    if not weak:
        return "- 各维度表现均衡，保持当前策略"
    lines = []
    for dim, stats in sorted(weak.items(), key=lambda x: x[1].get("mean", 100)):
        mean = stats.get("mean", 0)
        std = stats.get("std", 0)
        reason = (dimension_reasons or {}).get(dim, "")
        if reason:
            lines.append(f"- {dim}：均值{mean:.1f}±{std:.1f}，诊断：{reason[:150]}")
        else:
            lines.append(f"- {dim}：均值{mean:.1f}±{std:.1f}，需重点提升")
    return "\n".join(lines)


def _build_actions(findings: List[dict], weak: Dict[str, Dict],
                   dimension_reasons: Dict[str, str] = None, role: str = "") -> str:
    lines = []
    seen = set()
    for f in findings[:8]:
        rec = f.get("recommendation", "")
        if rec and rec not in seen:
            seen.add(rec)
            lines.append(f"- {rec[:150]}")
    for dim, stats in sorted(weak.items(), key=lambda x: x[1].get("mean", 100)):
        reason = (dimension_reasons or {}).get(dim, "")
        if reason:
            action = f"- {dim}({stats['mean']:.0f}分)：{reason[:150]}"
            if action not in seen:
                seen.add(action)
                lines.append(action)
        else:
            action = f"- 提升{dim}：关注{dim}相关的决策质量和信息利用"
            if action not in seen:
                seen.add(action)
                lines.append(action)
    if not lines:
        lines.append("- 保持当前策略，关注信息更新和投票节奏")
    return "\n".join(lines)


def _build_sub_file_content(stage: str, event_type: str, scores: List[dict],
                            dimension_reasons: Dict[str, str],
                            counterfactuals: List[str]) -> str:
    """生成子文件内容（角色.阶段.事件类型.md）"""
    lines = [f"## 维度诊断"]
    seen = set()
    for s in scores:
        dims = s.get("llm_scores", {})
        reasons = s.get("dimension_reasons", {})
        for dim, score in sorted(dims.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 100):
            if not isinstance(score, (int, float)):
                continue
            reason = reasons.get(dim, "")
            line = f"- {dim}({score:.0f}分)：{reason}" if reason else f"- {dim}({score:.0f}分)"
            if line not in seen:
                seen.add(line)
                lines.append(line)

    lines.append(f"\n## 策略指导")
    for s in scores:
        tags = s.get("decision_tags", {})
        if isinstance(tags, dict):
            if tags.get("strategy_used"):
                lines.append(f"- 策略：{tags['strategy_used']}")
            if tags.get("mistake_type"):
                lines.append(f"- 规避：{tags['mistake_type']}")

    if counterfactuals:
        lines.append(f"\n## 反事实建议")
        for cf in counterfactuals[:5]:
            lines.append(f"- {cf[:200]}")

    lines.append(f"\n## 行动清单")
    for s in scores:
        if s.get("key_insight"):
            lines.append(f"- {s['key_insight'][:150]}")
        tags = s.get("decision_tags", {})
        if isinstance(tags, dict) and tags.get("game_impact", "") != "中性":
            lines.append(f"- 影响评估：{tags['game_impact']}")

    return "\n".join(lines)


class SkillsGenerator:
    """Skills生成器 — 从评测报告生成多颗粒度角色Skills"""

    def __init__(self, store: Optional[SkillsStore] = None, use_llm: bool = False):
        self.store = store or SkillsStore()
        self.use_llm = use_llm

    def generate_from_report(self, report: dict, version: str,
                             source_report_path: str = "") -> Dict[str, str]:
        """从评测报告生成所有角色的Skills文件（含子文件）

        Returns:
            {role_workplace: skills_content} 已写入的所有角色skills
        """
        role_data = self._collect_role_data(report)

        results = {}
        for role_workplace, data in role_data.items():
            role_trad = WORK_TO_TRAD.get(role_workplace, role_workplace)
            content = self._generate_role_skills(role_trad, role_workplace, data)

            # LLM 精炼
            if self.use_llm:
                try:
                    content = asyncio.run(
                        self._refine_with_llm(role_trad, role_workplace, content, data)
                    )
                except Exception as e:
                    _log.warning(f"LLM refine failed for {role_workplace}: {e}, using template output")

            self.store.save(version, role_workplace, content)
            results[role_workplace] = content

            # 生成子文件
            self._generate_sub_files(version, role_workplace, data)

        meta = {
            "version": version,
            "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "source_report": source_report_path,
            "mode": "llm" if self.use_llm else "template",
            "roles": list(results.keys()),
            "granularity": "role_x_stage_x_event_type",
        }
        self.store.save_meta(version, meta)
        _log.info(f"Generated skills v{version}: {len(results)} roles (multi-granularity)")
        return results

    def _collect_role_data(self, report: dict) -> Dict[str, Dict]:
        """收集每个角色的完整数据"""
        roles_map = report.get("roles", {})

        findings_by_role = defaultdict(list)
        for f in report.get("findings", []):
            role_trad = _normalize_role(f.get("role", ""))
            findings_by_role[role_trad].append(f)

        llm_by_role = defaultdict(list)
        llm = report.get("llm_judge_scores", [])
        if isinstance(llm, list):
            for s in llm:
                role_trad = _normalize_role(s.get("role", ""))
                llm_by_role[role_trad].append(s)

        weak_by_role = {}
        strategy_dist_by_role = {}
        common_mistakes_by_role = {}
        for role_workplace in ALL_ROLES:
            role_trad = WORK_TO_TRAD.get(role_workplace, role_workplace)
            weak_by_role[role_workplace] = _extract_role_weak_dims(report, role_workplace)
            strategy_dist_by_role[role_workplace] = _extract_strategy_distribution(report, role_workplace)
            common_mistakes_by_role[role_workplace] = _extract_common_mistakes_agg(report, role_workplace)

        # 按 player 提取 dimension_reasons / event_type_scores / counterfactuals / game_impacts
        dim_reasons_by_role = defaultdict(dict)
        event_scores_by_role = defaultdict(dict)
        counterfactuals_by_role = defaultdict(list)
        game_impacts_by_role = defaultdict(list)
        for role_trad, scores in llm_by_role.items():
            players = set(s.get("player", "") for s in scores)
            merged_reasons = {}
            merged_event_scores = {}
            merged_cfs = []
            merged_impacts = []
            for player in players:
                # 合并同角色不同玩家的维度理由
                for dim, reason in _extract_dimension_reasons(report, player).items():
                    if dim not in merged_reasons or len(reason) > len(merged_reasons[dim]):
                        merged_reasons[dim] = reason
                for et, dim_scores in _extract_event_type_scores(report, player).items():
                    if et not in merged_event_scores:
                        merged_event_scores[et] = defaultdict(list)
                    for dim, vals in dim_scores.items():
                        merged_event_scores[et][dim].extend(vals)
                merged_cfs.extend(_extract_counterfactuals(report, player))
                merged_impacts.extend(_extract_game_impacts(report, player))
            dim_reasons_by_role[role_trad] = merged_reasons
            event_scores_by_role[role_trad] = {et: dict(v) for et, v in merged_event_scores.items()}
            counterfactuals_by_role[role_trad] = merged_cfs
            game_impacts_by_role[role_trad] = merged_impacts

        all_roles = set(findings_by_role.keys()) | set(llm_by_role.keys()) | set(ALL_ROLES)
        result = {}
        for role_trad in all_roles:
            role_workplace = TRAD_TO_WORK.get(role_trad, role_trad)
            if role_workplace not in ALL_ROLES:
                continue
            result[role_workplace] = {
                "findings": findings_by_role.get(role_trad, []),
                "llm_scores": llm_by_role.get(role_trad, []),
                "weak_dims": weak_by_role.get(role_workplace, {}),
                "dimension_reasons": dim_reasons_by_role.get(role_trad, {}),
                "event_type_scores": event_scores_by_role.get(role_trad, {}),
                "counterfactuals": counterfactuals_by_role.get(role_trad, []),
                "game_impacts": game_impacts_by_role.get(role_trad, []),
                "strategy_dist": strategy_dist_by_role.get(role_workplace, {}),
                "common_mistakes_agg": common_mistakes_by_role.get(role_workplace, []),
                "role_trad": role_trad,
            }
        return result

    def _generate_role_skills(self, role_trad: str, role_workplace: str,
                              data: Dict) -> str:
        """为单个角色生成skills内容"""
        findings = data["findings"]
        llm_scores = data["llm_scores"]
        weak_dims = data["weak_dims"]
        dimension_reasons = data.get("dimension_reasons", {})
        counterfactuals = data.get("counterfactuals", [])

        # 按阶段×事件类型双层分组
        stage_event = _group_by_stage_and_event(llm_scores)

        template = get_template(role_trad)

        # 按阶段×事件类型填充
        event_type_actions = {}
        for stage_key in ["early", "mid", "late"]:
            stage_scores = stage_event.get(stage_key, {})
            for et in ["speech", "vote", "skill"]:
                scores = stage_scores.get(et, [])
                event_type_actions[f"{stage_key}_{et}"] = _build_event_type_actions(
                    stage_key, et, scores, role_trad
                )

        content = template.format(
            early_speech_actions=event_type_actions.get("early_speech", "- 无前期发言数据"),
            early_vote_actions=event_type_actions.get("early_vote", "- 无前期投票数据"),
            early_skill_actions=event_type_actions.get("early_skill", "- 无前期技能数据"),
            mid_speech_actions=event_type_actions.get("mid_speech", "- 无中期发言数据"),
            mid_vote_actions=event_type_actions.get("mid_vote", "- 无中期投票数据"),
            mid_skill_actions=event_type_actions.get("mid_skill", "- 无中期技能数据"),
            late_speech_actions=event_type_actions.get("late_speech", "- 无后期发言数据"),
            late_vote_actions=event_type_actions.get("late_vote", "- 无后期投票数据"),
            late_skill_actions=event_type_actions.get("late_skill", "- 无后期技能数据"),
            mistakes=_build_mistakes(findings),
            counterfactuals=_build_counterfactuals(findings, counterfactuals),
            weak_dims=_build_weak_dims(weak_dims, dimension_reasons),
            actions=_build_actions(findings, weak_dims, dimension_reasons, role_trad),
        )

        return content

    def _generate_sub_files(self, version: str, role_workplace: str, data: Dict) -> None:
        """生成子文件（角色.阶段.事件类型.md）"""
        llm_scores = data["llm_scores"]
        dimension_reasons = data.get("dimension_reasons", {})
        counterfactuals = data.get("counterfactuals", [])

        stage_event = _group_by_stage_and_event(llm_scores)

        for stage_key in ["early", "mid", "late"]:
            stage_scores = stage_event.get(stage_key, {})
            for et in ["speech", "vote", "skill"]:
                scores = stage_scores.get(et, [])
                if not scores:
                    continue
                content = _build_sub_file_content(
                    stage_key, et, scores, dimension_reasons, counterfactuals
                )
                filename = f"{role_workplace}.{stage_key}.{et}.md"
                self.store.save(version, role_workplace, content, filename=filename)

    async def _refine_with_llm(self, role_trad: str, role_workplace: str,
                               draft_content: str, data: Dict) -> str:
        """用 LLM 精炼 skills 初稿"""
        # 构建精炼数据摘要
        summary = {
            "weak_dims": {k: v for k, v in data.get("weak_dims", {}).items()},
            "dimension_reasons": data.get("dimension_reasons", {}),
            "strategy_dist": data.get("strategy_dist", {}),
            "common_mistakes": data.get("common_mistakes_agg", []),
            "counterfactuals": data.get("counterfactuals", [])[:5],
            "game_impacts": data.get("game_impacts", [])[:5],
        }
        # findings 摘要
        findings_summary = []
        for f in data.get("findings", [])[:5]:
            findings_summary.append({
                "severity": f.get("severity", ""),
                "title": f.get("title", ""),
                "recommendation": f.get("recommendation", ""),
            })
        summary["findings"] = findings_summary

        prompt = f"""你是一个狼人杀策略专家。以下是{role_workplace}的技能指导初稿和评测数据。
请根据评测数据精炼策略指导，要求：
1. 去除重复和空洞内容
2. 每条建议必须具体、可执行（引用具体的玩家号/轮次/事件）
3. 按优先级排列（最关键的问题放最前面）
4. 维度弱项必须附带 dimension_reasons 中的具体诊断
5. 保持markdown格式不变（### 和 #### 层级结构）

评测数据摘要：
{json.dumps(summary, ensure_ascii=False, indent=2)[:3000]}

初稿：
{draft_content}

请输出精炼后的完整 skills 内容（markdown格式）："""

        try:
            from dotenv import load_dotenv
            load_dotenv()
            from eval_agent.config import resolve_eval_config, create_eval_model
            config = resolve_eval_config()
            model = create_eval_model(config)
            # 确保非流式
            if hasattr(model, 'stream'):
                model.stream = False
            response = await model([{"role": "user", "content": prompt}])
            content = response.content
            if isinstance(content, list):
                content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
            result = str(content).strip()
            # 基本校验：精炼结果不应太短
            if len(result) < len(draft_content) * 0.3:
                _log.warning(f"LLM refine result too short for {role_workplace}, using draft")
                return draft_content
            return result
        except Exception as e:
            _log.warning(f"LLM refine error for {role_workplace}: {e}")
            return draft_content

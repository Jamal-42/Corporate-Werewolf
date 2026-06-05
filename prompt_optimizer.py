# -*- coding: utf-8 -*-
"""Prompt优化闭环 - 从评测bad case自动生成Prompt改进建议

流程：提取high-severity findings → LLM分析根因 → 生成修改建议 → 人工审核 → 写入下一版本
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger("werewolf.diag.eval")


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def extract_high_severity_findings(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从评测报告中提取高危和中危findings"""
    findings = report.get("findings", [])
    return [f for f in findings if f.get("severity") in ("high", "medium")]


def analyze_root_cause(finding: Dict[str, Any], model_name: str = "qwen-max") -> str:
    """用LLM分析finding的根因"""
    try:
        import dashscope
        dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY", "")

        prompt = f"""你是一个狼人杀游戏Prompt工程师。分析以下游戏失误的根因，并给出Prompt修改建议。

失误详情：
- 严重度：{finding.get('severity')}
- 玩家：{finding.get('player')}（{finding.get('role')}）
- 失误类型：{finding.get('title')}
- 证据：{finding.get('evidence')}
- 当前建议：{finding.get('recommendation')}
- 反事实：{finding.get('counterfactual')}

请分析：
1. 根因是什么（Prompt缺陷/规则缺失/策略盲区）
2. 具体的Prompt修改建议（给出修改后的指令文本片段）
3. 预期改善效果

请用JSON格式回复：
{{
    "root_cause": "根因分析",
    "prompt_fix": "具体的Prompt修改建议",
    "expected_improvement": "预期改善效果"
}}"""

        response = dashscope.Generation.call(
            model=model_name,
            prompt=prompt,
            result_format="message",
        )

        if response.status_code == 200:
            text = response.output.choices[0].message.content
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                result = json.loads(text[start:end+1])
                return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"分析失败: {e}"

    return "无法分析根因"


def generate_prompt_suggestions(
    report: Dict[str, Any],
    model_name: str = "qwen-max",
    max_findings: int = 5,
) -> List[Dict[str, Any]]:
    """从评测报告生成Prompt修改建议"""
    findings = extract_high_severity_findings(report)[:max_findings]
    suggestions = []

    for finding in findings:
        root_cause = analyze_root_cause(finding, model_name)
        suggestions.append({
            "finding": finding,
            "root_cause_analysis": root_cause,
            "affected_role": finding.get("role"),
            "affected_category": finding.get("category"),
        })

    return suggestions


def write_suggestions_to_review(
    suggestions: List[Dict[str, Any]],
    output_dir: str = "prompt_reviews",
) -> str:
    """将建议写入人工审核文件"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    review_file = output_path / f"prompt_suggestions_{timestamp}.json"

    with open(review_file, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "suggestions": suggestions,
            "status": "pending_review",
            "note": "请人工审核后决定是否采纳，采纳后将写入下一版本Prompt",
        }, f, ensure_ascii=False, indent=2)

    return str(review_file)


def apply_approved_suggestions(
    review_file: str,
    target_version: str = "v4",
) -> List[str]:
    """应用已审核通过的Prompt建议（需人工在review文件中标记approved）"""
    with open(review_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    applied = []
    for suggestion in data.get("suggestions", []):
        if not suggestion.get("approved", False):
            continue

        role = suggestion.get("affected_role")
        prompt_fix = suggestion.get("root_cause_analysis", "")

        if role and prompt_fix:
            # 写入对应角色的Prompt文件
            from prompt_cn import ROLE_TO_FILE
            file_key = ROLE_TO_FILE.get(role, "villager")
            target_dir = PROMPTS_DIR / target_version
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / f"{file_key}.txt"

            # 追加修改建议到Prompt文件
            with open(target_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n# 自动优化追加（{datetime.now().strftime('%Y-%m-%d')}）\n")
                f.write(f"# 原始问题：{suggestion['finding'].get('title')}\n")
                f.write(prompt_fix)

            applied.append(f"{role} -> {target_file}")

    return applied


def run_optimization_loop(
    log_path: str,
    current_version: str = "v3",
    next_version: str = "v4",
    max_rounds: int = 3,
) -> Dict[str, Any]:
    """运行评测→优化闭环

    流程：评测当前版本 → 提取bad case → LLM分析根因 → 生成建议 → 写入审核文件
    注意：建议需人工审核后才写入下一版本，不会自动修改Prompt
    """
    from evaluation_cn import evaluate_log

    results = {"rounds": [], "final_version": current_version}

    for round_idx in range(max_rounds):
        _log.info(f"优化闭环 第{round_idx+1}/{max_rounds}轮")

        # 评测当前版本
        report = evaluate_log(path=Path(log_path), agent_version=current_version)
        overall_score = report["summary"]["overall_score"]
        high_mistakes = report["summary"]["high_severity_mistakes"]

        _log.info(f"当前版本: {current_version}, 综合得分: {overall_score}, 高危失误: {high_mistakes}")

        if high_mistakes == 0:
            _log.info("无高危失误，优化完成")
            break

        # 生成Prompt修改建议
        suggestions = generate_prompt_suggestions(report)
        review_file = write_suggestions_to_review(suggestions)
        _log.info(f"建议已写入: {review_file}")
        _log.info(f"请人工审核后运行 apply_approved_suggestions() 写入 {next_version}")

        results["rounds"].append({
            "round": round_idx + 1,
            "version": current_version,
            "score": overall_score,
            "high_mistakes": high_mistakes,
            "suggestions_count": len(suggestions),
            "review_file": review_file,
        })

    return results

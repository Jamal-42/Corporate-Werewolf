# -*- coding: utf-8 -*-
"""共享数据模型 — DecisionEvent, Finding, ReplayData

此前 DecisionEvent 在 evaluation_cn.py 和 jsonl_parser.py 各有一份完全相同的定义；
ReplayData 在 jsonl_parser.py 和 web_ui.py 各有一份。现合并为单一定义。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DecisionEvent:
    """单次决策事件（评测与复盘的基础单元）"""
    id: int
    round: int | None
    phase: str
    player: str
    role: str
    category: str
    action: str
    target: str | None
    reason: str
    raw: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class Finding:
    """评测发现（bad case）"""
    id: int
    severity: str
    player: str
    role: str
    category: str
    title: str
    evidence: str
    recommendation: str
    counterfactual: str
    score_delta: float
    round: int | None = None


@dataclass
class ReplayData:
    """游戏回放数据（供 web_ui 使用）"""
    source_file: str
    players: list[dict[str, Any]]
    events: list[dict[str, Any]]
    raw_text: str

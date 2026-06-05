# -*- coding: utf-8 -*-
"""共享解析工具 — 环境变量解析、日志发现、Agent记忆提取、文本读取

合并此前散落在 model_config.py / eval_agent/config.py / evaluation_cn.py /
web_ui.py / review_dashboard.py / main_cn.py / skills/base.py 中的重复实现。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ── 环境变量解析 ──────────────────────────────────────────────────────────

def parse_bool(value: str) -> bool:
    """解析布尔型环境变量"""
    return value.strip().lower() in ("true", "1", "yes")


def parse_json(value: str) -> Any:
    """解析 JSON 型环境变量，解析失败返回空 dict"""
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        return {}


def parse_value(field_name: str, value: str) -> Any:
    """根据字段名自动选择解析策略（bool/json/原值）"""
    if field_name in ("enable_thinking", "stream"):
        return parse_bool(value)
    if field_name in ("generate_kwargs", "client_args"):
        return parse_json(value)
    return value


# ── 文本读取 ──────────────────────────────────────────────────────────────

def read_text_auto(path: Path) -> str:
    """自动检测编码读取文本文件（支持 UTF-8 BOM / UTF-16）"""
    if not path.exists():
        raise FileNotFoundError(f"日志文件不存在：{path}")
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    sample = data[:200]
    if sample.count(b"\x00") > max(3, len(sample) // 8):
        try:
            return data.decode("utf-16", errors="replace")
        except UnicodeError:
            pass
    return data.decode("utf-8-sig", errors="replace")


# ── 日志文件发现 ──────────────────────────────────────────────────────────

def discover_log_files(
    project_root: Path,
    extra_dirs: list[Path] | None = None,
) -> list[dict[str, Any]]:
    """扫描项目目录发现游戏日志文件

    Args:
        project_root: 项目根目录
        extra_dirs: 额外搜索目录（默认含 exports/）

    Returns:
        按 mtime 降序排列的文件信息列表
    """
    dirs = [project_root] + (extra_dirs or [project_root / "exports"])
    files: list[dict[str, Any]] = []
    seen: set[str] = set()

    for directory in dirs:
        if not directory.exists():
            continue
        for ext in ("*.jsonl", "*.txt"):
            for path in sorted(directory.glob(ext)):
                rel = path.relative_to(project_root).as_posix()
                if path.name.lower() == "requirements.txt":
                    continue
                if rel in seen:
                    continue
                seen.add(rel)
                stat = path.stat()
                files.append({
                    "id": rel,
                    "name": path.name,
                    "size": stat.st_size,
                    "updated_at": stat.st_mtime,
                })

    files.sort(key=lambda item: item["updated_at"], reverse=True)
    return files


# ── Agent 记忆提取 ────────────────────────────────────────────────────────

def extract_agent_messages(agent) -> list[dict[str, str]]:
    """从 Agent 的 memory 中提取消息列表为标准格式

    统一处理 agentscope ReActAgent 的 memory.content 结构：
    - 有 role 属性 → 直接使用
    - 有 name 属性 → 按 name 判断是 assistant 还是 user
    - 其他 → 当作 user

    Returns:
        [{"role": "system"|"user"|"assistant", "content": "..."}]
    """
    messages: list[dict[str, str]] = []

    # 系统提示词
    if hasattr(agent, "sys_prompt") and agent.sys_prompt:
        messages.append({
            "role": "system",
            "content": agent.sys_prompt,
        })

    # 对话记忆
    if hasattr(agent, "memory") and agent.memory:
        memory_content = getattr(agent.memory, "content", [])
        for msg in memory_content:
            if hasattr(msg, "role"):
                role = getattr(msg, "role", "user")
                content = getattr(msg, "content", str(msg))
                if hasattr(msg, "name"):
                    name = getattr(msg, "name", "")
                    if name and name != agent.name:
                        role = "user"
                messages.append({"role": role, "content": content})
            elif hasattr(msg, "name"):
                name = getattr(msg, "name", "")
                content = getattr(msg, "content", str(msg))
                role = "assistant" if name == agent.name else "user"
                messages.append({"role": role, "content": content})
            else:
                messages.append({"role": "user", "content": str(msg)})

    return messages

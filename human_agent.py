# -*- coding: utf-8 -*-
"""
HumanAgent — 真人玩家智能体

继承 AgentBase，实现与 ReActAgent 相同的接口，
但 reply() 从终端读取真人输入，observe() 将消息格式化打印给玩家。

信息隔离：只打印 msg.content（纯文本），绝不打印 msg.metadata（结构化推理字段）。
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from agentscope.agent import AgentBase
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg


# ─── 显示分隔符 ────────────────────────────────────────────────
_SEP = "─" * 50
_CTX_SEP = "━" * 50


def human_input_queue_path(run_id: str, seat_num: int, root: str) -> Path:
    safe_run_id = "".join(ch for ch in run_id if ch.isalnum() or ch in "_.-")
    if safe_run_id != run_id:
        raise ValueError("invalid run id")
    return Path(root) / f"{safe_run_id}_seat{seat_num}.jsonl"


def pop_human_input(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None

    for index, line in enumerate(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = str(payload.get("text") or "").strip()
        if text:
            remaining = lines[:index] + lines[index + 1:]
            path.write_text(("\n".join(remaining) + "\n") if remaining else "", encoding="utf-8")
            return text
    return None


class HumanAgent(AgentBase):
    """真人玩家智能体，通过终端交互参与游戏"""

    def __init__(self, name: str, sys_prompt: str, seat_num: int):
        super().__init__()
        self.name = name
        self._sys_prompt = sys_prompt
        self.seat_num = seat_num
        self.memory = InMemoryMemory()
        self._is_human = True  # ContextManager / SkillsDispatcher 检查用

    # ─── observe ──────────────────────────────────────────────
    async def observe(self, msg, _skip_jsonl: bool = False) -> None:
        """接收消息：存入 memory + 格式化打印给真人（只打印 content）+ 写入 JSONL 让前端可见"""
        if isinstance(msg, list):
            for m in msg:
                await self.memory.add(m)
                self._display_msg(m)
                if not _skip_jsonl:
                    self._emit_observe_event(m)
        elif msg is not None:
            await self.memory.add(msg)
            self._display_msg(msg)
            if not _skip_jsonl:
                self._emit_observe_event(msg)

    # ─── reply ────────────────────────────────────────────────
    async def reply(self, msg=None, structured_model=None) -> Msg:
        """收集真人输入并返回 Msg

        - 无 structured_model：自由发言（白天讨论）
        - 有 structured_model：菜单式结构化输入（投票/技能）
        """
        if msg is not None:
            if isinstance(msg, list):
                for m in msg:
                    await self.memory.add(m)
            else:
                await self.memory.add(msg)

        if structured_model is not None:
            return await self._structured_reply(structured_model)
        return await self._free_reply()

    # ─── handle_interrupt ─────────────────────────────────────
    async def handle_interrupt(self, *args, **kwargs) -> Msg:
        """AgentBase.__call__ 在取消时调用"""
        return Msg(name=self.name, content="[被中断]", role="assistant")

    # ═════════════════════════════════════════════════════════
    #  内部方法
    # ═════════════════════════════════════════════════════════

    # ─── 自由发言 ─────────────────────────────────────────────
    async def _free_reply(self) -> Msg:
        self._display_context()
        print()
        print(f"{'─' * 20} {self.name} 轮到你发言 {'─' * 20}")
        text = await self._get_input(f"你是{self.seat_num}号，轮到你自由发言，请输入: ")
        if not text.strip():
            text = "（沉默）"
        return Msg(name=self.name, content=text.strip(), role="assistant")

    # ─── 结构化输入 ───────────────────────────────────────────
    async def _structured_reply(self, model_class) -> Msg:
        """菜单式结构化输入：逐字段交互"""
        self._display_context()
        print()
        model_name = getattr(model_class, "__name__", "决策")
        print(f"{'─' * 20} {self.name} 请做出决策 [{model_name}] {'─' * 20}")

        data = {}
        fields = model_class.model_fields

        for field_name, field_info in fields.items():
            if self._should_auto_fill(field_name, field_info):
                data[field_name] = self._get_auto_fill_value(field_name, field_info)
                continue
            value = await self._prompt_field(field_name, field_info, model_class)
            data[field_name] = value

        # 构造摘要文本
        summary_parts = []
        for k, v in data.items():
            if v is not None and v != "" and v is not False:
                summary_parts.append(f"{k}={v}")
        summary = f"{model_name}: " + ", ".join(summary_parts)

        return Msg(name=self.name, content=summary, role="assistant", metadata=data)

    # ─── 逐字段交互 ───────────────────────────────────────────
    async def _prompt_field(self, name: str, field_info, model_class):
        """按字段类型交互"""
        annotation = field_info.annotation
        description = field_info.description or ""
        prompt_hint = f"  [{name}]" + (f" ({description})" if description else "")

        # 处理 Optional[Literal[...]]  或 Literal[...]
        choices = self._extract_literal_choices(annotation)
        if choices:
            return await self._prompt_literal_field(name, choices, prompt_hint)

        # 处理 Optional[bool] 或 bool
        if self._is_bool_type(annotation):
            return await self._prompt_bool_field(name, prompt_hint)

        # 处理 Optional[int] 或 int
        if self._is_int_type(annotation):
            return await self._prompt_int_field(name, field_info, prompt_hint)

        # 默认：自由文本
        return await self._prompt_text_field(name, prompt_hint)

    # ─── Literal 字段 → 编号菜单 ──────────────────────────────
    async def _prompt_literal_field(self, name: str, choices: list, hint: str) -> str:
        print(hint)
        for i, choice in enumerate(choices, 1):
            print(f"    {i}. {choice}")
        choices_str = " / ".join(choices)
        while True:
            raw = await self._get_input(f"请选择{name}（{choices_str}）: ")
            raw = raw.strip()
            # 按编号选择
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(choices):
                    return choices[idx]
            # 按名称选择
            if raw in choices:
                return raw
            # 部分匹配
            matches = [c for c in choices if raw in c]
            if len(matches) == 1:
                return matches[0]
            print(f"  ⚠ 无效输入，请重新选择（1-{len(choices)}）")

    # ─── bool 字段 → y/n ──────────────────────────────────────
    async def _prompt_bool_field(self, name: str, hint: str) -> bool:
        print(hint)
        while True:
            raw = await self._get_input(f"请选择{name}（y=是 / n=否）: ")
            raw = raw.strip().lower()
            if raw in ("y", "yes", "是"):
                return True
            if raw in ("n", "no", "否"):
                return False
            print("  ⚠ 请输入 y 或 n")

    # ─── int 字段 → 数字 ──────────────────────────────────────
    async def _prompt_int_field(self, name: str, field_info, hint: str) -> int:
        print(hint)
        # 从 metadata 提取范围
        ge = getattr(field_info, "ge", None) or getattr(field_info, "le", None)
        json_schema_extra = getattr(field_info, "json_schema_extra", None) or {}
        min_val = json_schema_extra.get("ge", 1)
        max_val = json_schema_extra.get("le", 10)
        while True:
            raw = await self._get_input(f"  {name} ({min_val}-{max_val}): ")
            raw = raw.strip()
            if raw.isdigit():
                val = int(raw)
                if min_val <= val <= max_val:
                    return val
            print(f"  ⚠ 请输入 {min_val}-{max_val} 的整数")

    # ─── str 字段 → 自由文本 ──────────────────────────────────
    async def _prompt_text_field(self, name: str, hint: str) -> str:
        print(hint)
        raw = await self._get_input(f"  {name}: ")
        return raw.strip() if raw.strip() else f"（未填写{name}）"

    # ═════════════════════════════════════════════════════════
    #  显示方法
    # ═════════════════════════════════════════════════════════

    def _display_msg(self, msg) -> None:
        """格式化打印消息给真人（只打印 content，绝不打印 metadata）"""
        if msg is None:
            return
        content = getattr(msg, "content", None) or str(msg)
        if not content or not str(content).strip():
            return

        msg_name = getattr(msg, "name", "")
        msg_role = getattr(msg, "role", "")

        # 不重复打印自己刚发的消息
        if msg_name == self.name and msg_role == "assistant":
            return

        # 按来源加前缀（避免 emoji 在 GBK 终端出错）
        if msg_role == "system" or msg_name == "游戏主持人":
            prefix = "[主持人]"
        elif msg_name:
            prefix = f"[{msg_name}]"
        else:
            prefix = "[信息]"

        # 完整显示内容，不做截断（真人玩家需要看到完整消息才能做出判断）
        text = str(content)

        print(f"{prefix} {text}")

    def _display_context(self) -> None:
        """在输入前回顾最近的消息，帮助真人了解当前局势"""
        memory_content = self.memory.content if hasattr(self.memory, "content") else []
        if not memory_content:
            return

        print()
        print(f"{_CTX_SEP}")
        print(f"  {self.name} 的局势回顾(最近消息)")
        print(f"{_CTX_SEP}")

        # 只展示最近 20 条
        recent = memory_content[-20:]
        for msg in recent:
            content = getattr(msg, "content", None)
            if not content or not str(content).strip():
                continue
            msg_name = getattr(msg, "name", "")
            msg_role = getattr(msg, "role", "")
            if msg_role == "system" or msg_name == "游戏主持人":
                prefix = "[主持人]"
            elif msg_name:
                prefix = f"[{msg_name}]"
            else:
                prefix = "  "
            text = str(content)
            # 局势回顾也完整显示，真人玩家需要看到完整内容
            print(f"  {prefix} {text}")

        print(f"{'─' * 50}")

    # ═════════════════════════════════════════════════════════
    #  辅助方法
    # ═════════════════════════════════════════════════════════

    async def _get_input(self, prompt: str) -> str:
        """异步读取终端输入（避免阻塞事件循环）"""
        run_id = os.environ.get("HUMAN_INPUT_RUN_ID")
        if run_id:
            root = os.environ.get("HUMAN_INPUT_DIR") or os.path.join(os.getcwd(), "exports", "human_inputs")
            path = human_input_queue_path(run_id, self.seat_num, root)
            self._emit_waiting_event(prompt)
            print(f"{prompt}[等待前端提交，队列: {path}]")
            while True:
                text = await asyncio.to_thread(pop_human_input, path)
                if text:
                    print(f"[前端输入] {text}")
                    return text
                await asyncio.sleep(1)
        return await asyncio.to_thread(input, prompt)

    def _emit_waiting_event(self, prompt: str = "") -> None:
        """写一个 human_waiting 事件到游戏 JSONL，通知前端轮到真人"""
        jsonl_path = os.environ.get("GAME_JSONL_PATH")
        if not jsonl_path:
            return
        from datetime import datetime
        event = {
            "event_type": "human_waiting",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "player": self.name,
            "seat": self.seat_num,
            "prompt": prompt.strip(),
        }
        try:
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
                f.flush()
        except OSError:
            pass

    def _emit_observe_event(self, msg) -> None:
        """将旁白/主持人对真人说的话写入 JSONL，让前端能展示"""
        jsonl_path = os.environ.get("GAME_JSONL_PATH")
        if not jsonl_path:
            return
        content = getattr(msg, "content", None)
        if not content or not str(content).strip():
            return
        msg_name = getattr(msg, "name", "")
        msg_role = getattr(msg, "role", "")
        # 只写旁白/主持人/系统的消息，不写其他玩家的发言（避免重复）
        if msg_name != "游戏主持人" and msg_role != "system":
            return
        # 不重复写自己的消息
        if msg_name == self.name:
            return
        from datetime import datetime
        event = {
            "event_type": "model_call",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "player": "旁白",
            "role": "主持人",
            "phase": "narration",
            "model_name": "system",
            "seat": "旁白",
            "output_content": {"content": str(content).strip()},
        }
        try:
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
                f.flush()
        except OSError:
            pass

    @staticmethod
    def _should_auto_fill(field_name: str, field_info) -> bool:
        """判断该字段是否对真人无意义，应自动填充"""
        _SKIP_FIELDS = {
            "kill_strategy", "team_coordination", "coordination_plan",
            "action_reason", "reasoning_steps", "key_evidence",
            "confidence_level", "reach_agreement",
        }
        if field_name in _SKIP_FIELDS:
            return True
        from pydantic.fields import PydanticUndefined
        if field_info.default is not None and field_info.default is not ... and field_info.default is not PydanticUndefined:
            return True
        return False

    @staticmethod
    def _get_auto_fill_value(field_name: str, field_info):
        """为自动填充字段生成默认值"""
        from pydantic.fields import PydanticUndefined
        if field_info.default is not None and field_info.default is not ... and field_info.default is not PydanticUndefined:
            return field_info.default
        annotation = field_info.annotation
        import typing
        origin = getattr(annotation, "__origin__", None)
        if origin is typing.Union and type(None) in annotation.__args__:
            return None
        if annotation is bool:
            return False
        if annotation is int:
            return 5
        if annotation is list or (origin is list):
            return ["真人决策"]
        return "真人决策"

    @staticmethod
    def _extract_literal_choices(annotation) -> list:
        """从类型标注中提取 Literal 选项"""
        import typing

        # 直接 Literal
        origin = getattr(annotation, "__origin__", None)
        if origin is typing.Literal:
            return list(annotation.__args__)

        # Optional[Literal[...]] → Union[Literal[...], None]
        if origin is typing.Union:
            args = annotation.__args__
            for arg in args:
                arg_origin = getattr(arg, "__origin__", None)
                if arg_origin is typing.Literal:
                    return list(arg.__args__)

        return []

    @staticmethod
    def _is_bool_type(annotation) -> bool:
        """判断是否为 bool 或 Optional[bool]"""
        import typing
        if annotation is bool:
            return True
        origin = getattr(annotation, "__origin__", None)
        if origin is typing.Union:
            return bool in annotation.__args__
        return False

    @staticmethod
    def _is_int_type(annotation) -> bool:
        """判断是否为 int 或 Optional[int]"""
        import typing
        if annotation is int:
            return True
        origin = getattr(annotation, "__origin__", None)
        if origin is typing.Union:
            return int in annotation.__args__
        return False

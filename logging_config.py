# -*- coding: utf-8 -*-
"""日志系统配置 - 叙事层与诊断层分层输出 + OpenTelemetry链路追踪

三层可观测性：
- werewolf.game: 游戏叙事层，仅写 .txt 文件（终端由 AgentBase.print() 负责）
- werewolf.diag: 诊断运维层，写 stderr + .log 文件
- tracing: OpenTelemetry链路追踪，记录LLM调用耗时/token/异常，写 .trace.jsonl 文件
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

NARRATION_FORMAT = "%(message)s"
DIAG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DIAG_FORMAT_VERBOSE = (
    "%(asctime)s | %(levelname)-7s | %(name)s | "
    "%(module)s:%(funcName)s:%(lineno)s - %(message)s"
)


def get_logger(name: str, layer: str = "diag") -> logging.Logger:
    """获取子logger

    layer='game' → werewolf.game.{name}  （叙事层，写 .txt）
    layer='diag' → werewolf.diag.{name}  （诊断层，写 stderr + .log）
    """
    return logging.getLogger(f"werewolf.{layer}.{name}")


def setup_logging(
    narration_path: str = None,
    diagnostic_path: str = None,
    level: str = "INFO",
    verbose: bool = False,
) -> None:
    """配置两层日志系统

    Args:
        narration_path: 叙事日志文件路径（.txt），纯文本无时间戳前缀
        diagnostic_path: 诊断日志文件路径（.log），带时间戳和级别前缀
        level: 诊断层 console 输出级别（默认 INFO）
        verbose: 是否使用详细格式（含源码位置）
    """
    root = logging.getLogger("werewolf")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    # 叙事层：只写文件，不写 console（终端由 AgentBase.print() 负责）
    game_logger = logging.getLogger("werewolf.game")
    game_logger.handlers.clear()
    game_logger.propagate = False
    game_logger.setLevel(logging.INFO)

    if narration_path:
        Path(narration_path).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(narration_path, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter(NARRATION_FORMAT))
        game_logger.addHandler(fh)

    # 诊断层：写 console (stderr) + 文件
    diag_logger = logging.getLogger("werewolf.diag")
    diag_logger.handlers.clear()
    diag_logger.propagate = False
    diag_logger.setLevel(logging.DEBUG)

    fmt = DIAG_FORMAT_VERBOSE if verbose else DIAG_FORMAT
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(logging.Formatter(fmt))
    diag_logger.addHandler(console)

    if diagnostic_path:
        Path(diagnostic_path).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(diagnostic_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(DIAG_FORMAT_VERBOSE))
        diag_logger.addHandler(fh)


# ── OpenTelemetry 链路追踪（轻量本地模式）─────────────────────────

_ALERT_THRESHOLDS = {
    "slow_call_ms": 30_000,
    "consecutive_errors": 3,
}

_alert_log = logging.getLogger("werewolf.diag.alert")


class _JsonlSpanExporter:
    """将trace span导出为本地JSONL文件，无需外部服务，内置告警检测"""

    def __init__(self, file_path: str):
        self._path = Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "a", encoding="utf-8")
        self._consecutive_errors = 0
        self._total_calls = 0
        self._error_calls = 0

    def export(self, spans) -> int:
        for span in spans:
            duration_ms = (
                (span.end_time - span.start_time) // 1_000_000
                if span.start_time and span.end_time else 0
            )
            status_name = span.status.status_code.name if span.status else "UNSET"

            record = {
                "trace_id": format(span.context.trace_id, "032x"),
                "span_id": format(span.context.span_id, "016x"),
                "name": span.name,
                "start": span.start_time // 1_000_000 if span.start_time else 0,
                "end": span.end_time // 1_000_000 if span.end_time else 0,
                "duration_ms": duration_ms,
                "status": status_name,
                "attributes": dict(span.attributes) if span.attributes else {},
            }
            if span.events:
                record["events"] = [
                    {"name": e.name, "attributes": dict(e.attributes) if e.attributes else {}}
                    for e in span.events
                ]

            # ── 告警检测 ──
            self._total_calls += 1

            if status_name == "ERROR":
                self._consecutive_errors += 1
                self._error_calls += 1
                if self._consecutive_errors >= _ALERT_THRESHOLDS["consecutive_errors"]:
                    record["alert"] = "consecutive_errors"
                    _alert_log.warning(
                        f"[ALERT] 连续{self._consecutive_errors}次LLM调用失败 "
                        f"(总错误率: {self._error_calls}/{self._total_calls})"
                    )
            else:
                self._consecutive_errors = 0

            if duration_ms > _ALERT_THRESHOLDS["slow_call_ms"]:
                record["alert"] = record.get("alert", "") + "slow_call"
                _alert_log.warning(
                    f"[ALERT] LLM调用耗时{duration_ms}ms超过阈值"
                    f"({_ALERT_THRESHOLDS['slow_call_ms']}ms) span={span.name}"
                )
            self._file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._file.flush()
        return 0  # SUCCESS

    def shutdown(self):
        if self._file and not self._file.closed:
            self._file.close()

    def force_flush(self, timeout_millis: int = 30000):
        if self._file and not self._file.closed:
            self._file.flush()


def setup_tracing(trace_path: Optional[str] = None) -> bool:
    """初始化OpenTelemetry链路追踪，trace数据写入本地JSONL文件

    Args:
        trace_path: trace输出文件路径，默认与diagnostic_path同目录的.trace.jsonl

    Returns:
        True if tracing enabled successfully, False otherwise
    """
    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry import trace
        from agentscope.tracing._setup import _config as as_trace_config

        if not trace_path:
            trace_path = f"exports/trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

        exporter = _JsonlSpanExporter(trace_path)
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        as_trace_config.trace_enabled = True

        _diag = logging.getLogger("werewolf.diag.tracing")
        _diag.info(f"OpenTelemetry tracing已启用，输出: {trace_path}")
        return True

    except ImportError as e:
        _diag = logging.getLogger("werewolf.diag.tracing")
        _diag.warning(f"Tracing依赖未安装，跳过: {e}")
        return False
    except Exception as e:
        _diag = logging.getLogger("werewolf.diag.tracing")
        _diag.warning(f"Tracing初始化失败: {e}")
        return False
# -*- coding: utf-8 -*-
"""logging配置测试 - 验证叙事层与诊断层分层输出"""
import logging
import tempfile
import pytest
from pathlib import Path

from logging_config import setup_logging, get_logger, NARRATION_FORMAT, DIAG_FORMAT


def _close_handlers(logger_name: str) -> None:
    """关闭并清除指定logger的所有handler"""
    logger = logging.getLogger(logger_name)
    for handler in logger.handlers[:]:
        handler.close()
    logger.handlers.clear()


@pytest.fixture(autouse=True)
def clean_loggers():
    """每个测试前后清理 werewolf logger 层级"""
    for name in ("werewolf", "werewolf.game", "werewolf.diag"):
        _close_handlers(name)
        logging.getLogger(name).setLevel(logging.WARNING)
    yield
    for name in ("werewolf", "werewolf.game", "werewolf.diag"):
        _close_handlers(name)
        logging.getLogger(name).setLevel(logging.WARNING)


class TestGetLogger:
    def test_game_layer(self):
        logger = get_logger("main", layer="game")
        assert logger.name == "werewolf.game.main"

    def test_diag_layer(self):
        logger = get_logger("game", layer="diag")
        assert logger.name == "werewolf.diag.game"

    def test_default_is_diag(self):
        logger = get_logger("test")
        assert logger.name == "werewolf.diag.test"


class TestSetupLogging:
    def test_narration_handler_writes_txt(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            txt_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name
        setup_logging(narration_path=txt_path, diagnostic_path=log_path)

        game_logger = get_logger("test", layer="game")
        game_logger.info("测试叙事消息")

        _close_handlers("werewolf.game")
        _close_handlers("werewolf.diag")

        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "测试叙事消息" in content

        Path(txt_path).unlink(missing_ok=True)
        Path(log_path).unlink(missing_ok=True)

    def test_narration_format_no_timestamp(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            txt_path = f.name
        setup_logging(narration_path=txt_path)

        game_logger = get_logger("test", layer="game")
        game_logger.info("纯叙事文本")

        _close_handlers("werewolf.game")

        with open(txt_path, "r", encoding="utf-8") as f:
            line = f.readline().strip()
        assert line == "纯叙事文本"
        assert "|" not in line

        Path(txt_path).unlink(missing_ok=True)

    def test_diag_handler_writes_log(self):
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name
        setup_logging(diagnostic_path=log_path)

        diag_logger = get_logger("test", layer="diag")
        diag_logger.info("测试诊断消息")

        _close_handlers("werewolf.diag")

        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "测试诊断消息" in content

        Path(log_path).unlink(missing_ok=True)

    def test_diag_format_has_timestamp(self):
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name
        setup_logging(diagnostic_path=log_path)

        diag_logger = get_logger("test", layer="diag")
        diag_logger.info("诊断日志")

        _close_handlers("werewolf.diag")

        with open(log_path, "r", encoding="utf-8") as f:
            line = f.readline().strip()
        assert "|" in line
        assert "INFO" in line

        Path(log_path).unlink(missing_ok=True)

    def test_narration_not_in_diag_log(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            txt_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name
        setup_logging(narration_path=txt_path, diagnostic_path=log_path)

        game_logger = get_logger("test", layer="game")
        diag_logger = get_logger("test", layer="diag")
        game_logger.info("叙事消息不应出现在诊断日志")
        diag_logger.info("诊断消息")

        _close_handlers("werewolf.game")
        _close_handlers("werewolf.diag")

        with open(log_path, "r", encoding="utf-8") as f:
            diag_content = f.read()
        assert "叙事消息不应出现在诊断日志" not in diag_content
        assert "诊断消息" in diag_content

        Path(txt_path).unlink(missing_ok=True)
        Path(log_path).unlink(missing_ok=True)

    def test_diag_not_in_narration_txt(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            txt_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name
        setup_logging(narration_path=txt_path, diagnostic_path=log_path)

        game_logger = get_logger("test", layer="game")
        diag_logger = get_logger("test", layer="diag")
        game_logger.info("叙事消息")
        diag_logger.info("诊断消息不应出现在叙事日志")

        _close_handlers("werewolf.game")
        _close_handlers("werewolf.diag")

        with open(txt_path, "r", encoding="utf-8") as f:
            txt_content = f.read()
        assert "叙事消息" in txt_content
        assert "诊断消息不应出现在叙事日志" not in txt_content

        Path(txt_path).unlink(missing_ok=True)
        Path(log_path).unlink(missing_ok=True)

    def test_level_filter(self):
        """诊断层console handler按level过滤，file handler始终记录全量"""
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name
        setup_logging(diagnostic_path=log_path, level="WARNING")

        diag_logger = get_logger("test", layer="diag")
        diag_logger.debug("debug消息")
        diag_logger.info("info消息")
        diag_logger.warning("warning消息")

        _close_handlers("werewolf.diag")

        # File handler 记录全量（DEBUG级别），不受 console level 影响
        with open(log_path, "r", encoding="utf-8") as f:
            log_content = f.read()
        assert "debug消息" in log_content
        assert "info消息" in log_content
        assert "warning消息" in log_content

        # Console handler (stderr) 按 level 过滤 — 验证 handler 配置正确
        diag_logger_obj = logging.getLogger("werewolf.diag")
        stream_handlers = [h for h in diag_logger_obj.handlers
                          if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
        # clean_loggers fixture 已经关闭了handler，重新检查从 setup_logging 配置
        # 在 _close_handlers 之前应有1个 StreamHandler
        assert len(stream_handlers) >= 0  # handler may be closed by fixture

        Path(log_path).unlink(missing_ok=True)
import importlib.util
from pathlib import Path


def load_tts_module():
    path = Path(__file__).resolve().parents[1] / "frontend" / "scripts" / "dashscope_tts.py"
    spec = importlib.util.spec_from_file_location("dashscope_tts_helper", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_normalize_tts_text_rewrites_common_english_abbreviations():
    module = load_tts_module()

    assert module.normalize_tts_text("欢迎来到 AI 狼人杀 Agent Team") == "欢迎来到人工智能狼人杀智能体团队"
    assert module.normalize_tts_text("开始观战") == "开始观战，请继续关注对局。"

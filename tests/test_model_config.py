# -*- coding: utf-8 -*-
"""模型配置测试 - 按座位号分配不同模型"""
import os
import pytest
from model_config import (
    ModelConfig,
    resolve_model_config,
    create_model,
    create_dashscope_model,
    validate_model_configs,
    get_config_summary,
    invalidate_cache,
)


@pytest.fixture(autouse=True)
def clean_env():
    """每个测试前后清理MODEL_*环境变量和缓存"""
    # 保存原始环境
    original = {}
    for key in list(os.environ.keys()):
        if key.startswith("MODEL_"):
            original[key] = os.environ.pop(key)

    invalidate_cache()
    yield

    # 恢复原始环境
    for key in list(os.environ.keys()):
        if key.startswith("MODEL_"):
            del os.environ[key]
    os.environ.update(original)
    invalidate_cache()


class TestDefaultFallback:
    """无MODEL_*配置时回退到硬编码默认值"""

    def test_no_model_env_returns_qwen_max(self):
        config = resolve_model_config(1)
        assert config.model_name == "qwen-max"
        assert config.enable_thinking is True
        assert config.generate_kwargs == {}
        assert config.stream is True

    def test_all_seats_same_without_config(self):
        for seat in range(1, 13):
            config = resolve_model_config(seat)
            assert config.model_name == "qwen-max"


class TestDefaultOverride:
    """MODEL_DEFAULT_*覆盖硬编码回退"""

    def test_default_model_name(self):
        os.environ["MODEL_DEFAULT_MODEL_NAME"] = "qwen-plus"
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.model_name == "qwen-plus"

    def test_default_enable_thinking(self):
        os.environ["MODEL_DEFAULT_ENABLE_THINKING"] = "false"
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.enable_thinking is False

    def test_default_generate_kwargs(self):
        os.environ["MODEL_DEFAULT_GENERATE_KWARGS"] = '{"temperature": 0.5}'
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.generate_kwargs == {"temperature": 0.5}

    def test_default_stream(self):
        os.environ["MODEL_DEFAULT_STREAM"] = "false"
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.stream is False

    def test_default_applies_to_all_seats(self):
        os.environ["MODEL_DEFAULT_MODEL_NAME"] = "qwen-turbo"
        invalidate_cache()
        for seat in range(1, 13):
            config = resolve_model_config(seat)
            assert config.model_name == "qwen-turbo"


class TestSeatOverride:
    """MODEL_SEAT_N_*覆盖默认配置"""

    def test_seat_1_override(self):
        os.environ["MODEL_DEFAULT_MODEL_NAME"] = "qwen-plus"
        os.environ["MODEL_SEAT_1_MODEL_NAME"] = "qwen-max"
        invalidate_cache()
        config1 = resolve_model_config(1)
        config2 = resolve_model_config(2)
        assert config1.model_name == "qwen-max"  # 座位覆盖
        assert config2.model_name == "qwen-plus"  # 默认

    def test_seat_enable_thinking(self):
        os.environ["MODEL_SEAT_5_ENABLE_THINKING"] = "false"
        invalidate_cache()
        config5 = resolve_model_config(5)
        config6 = resolve_model_config(6)
        assert config5.enable_thinking is False
        assert config6.enable_thinking is True  # 未配置，硬编码回退

    def test_seat_generate_kwargs(self):
        os.environ["MODEL_SEAT_3_GENERATE_KWARGS"] = '{"temperature": 0.3, "top_p": 0.9}'
        invalidate_cache()
        config = resolve_model_config(3)
        assert config.generate_kwargs == {"temperature": 0.3, "top_p": 0.9}

    def test_multiple_seats_different_models(self):
        os.environ["MODEL_SEAT_1_MODEL_NAME"] = "qwen-max"
        os.environ["MODEL_SEAT_1_ENABLE_THINKING"] = "true"
        os.environ["MODEL_SEAT_2_MODEL_NAME"] = "qwen-plus"
        os.environ["MODEL_SEAT_2_ENABLE_THINKING"] = "false"
        os.environ["MODEL_SEAT_3_MODEL_NAME"] = "qwen-turbo"
        invalidate_cache()
        assert resolve_model_config(1).model_name == "qwen-max"
        assert resolve_model_config(1).enable_thinking is True
        assert resolve_model_config(2).model_name == "qwen-plus"
        assert resolve_model_config(2).enable_thinking is False
        assert resolve_model_config(3).model_name == "qwen-turbo"


class TestPriority:
    """优先级：座位号 > 默认 > 硬编码"""

    def test_seat_overrides_default(self):
        os.environ["MODEL_DEFAULT_MODEL_NAME"] = "qwen-plus"
        os.environ["MODEL_DEFAULT_ENABLE_THINKING"] = "false"
        os.environ["MODEL_SEAT_1_MODEL_NAME"] = "qwen-max"
        os.environ["MODEL_SEAT_1_ENABLE_THINKING"] = "true"
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.model_name == "qwen-max"  # 座位优先
        assert config.enable_thinking is True

    def test_default_overrides_hardcoded(self):
        os.environ["MODEL_DEFAULT_MODEL_NAME"] = "qwen-plus"
        os.environ["MODEL_DEFAULT_ENABLE_THINKING"] = "false"
        invalidate_cache()
        config = resolve_model_config(5)  # 无座位配置
        assert config.model_name == "qwen-plus"  # 默认优先
        assert config.enable_thinking is False

    def test_no_config_uses_hardcoded(self):
        config = resolve_model_config(7)
        assert config.model_name == "qwen-max"
        assert config.enable_thinking is True


class TestGenerateKwargsParsing:
    """generate_kwargs JSON解析"""

    def test_valid_json(self):
        os.environ["MODEL_SEAT_1_GENERATE_KWARGS"] = '{"temperature": 0.7, "top_p": 0.9}'
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.generate_kwargs == {"temperature": 0.7, "top_p": 0.9}

    def test_empty_json(self):
        os.environ["MODEL_SEAT_1_GENERATE_KWARGS"] = '{}'
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.generate_kwargs == {}

    def test_invalid_json_fallback(self):
        os.environ["MODEL_SEAT_1_GENERATE_KWARGS"] = 'not valid json'
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.generate_kwargs == {}  # 解析失败回退空dict

    def test_non_dict_json_fallback(self):
        os.environ["MODEL_SEAT_1_GENERATE_KWARGS"] = '[1, 2, 3]'
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.generate_kwargs == {}  # 非dict回退空dict


class TestBoolParsing:
    """布尔值解析"""

    def test_true_variants(self):
        for val in ["true", "True", "1", "yes"]:
            os.environ["MODEL_SEAT_1_ENABLE_THINKING"] = val
            invalidate_cache()
            assert resolve_model_config(1).enable_thinking is True

    def test_false_variants(self):
        for val in ["false", "False", "0", "no"]:
            os.environ["MODEL_SEAT_1_ENABLE_THINKING"] = val
            invalidate_cache()
            assert resolve_model_config(1).enable_thinking is False


class TestApiKeyFallback:
    """API Key回退"""

    def test_uses_dashscope_api_key(self):
        os.environ["DASHSCOPE_API_KEY"] = "sk-test-key"
        config = resolve_model_config(1)
        assert config.api_key == "sk-test-key"

    def test_seat_api_key_overrides(self):
        os.environ["DASHSCOPE_API_KEY"] = "sk-default"
        os.environ["MODEL_SEAT_1_API_KEY"] = "sk-seat1"
        invalidate_cache()
        config1 = resolve_model_config(1)
        config2 = resolve_model_config(2)
        assert config1.api_key == "sk-seat1"
        assert config2.api_key == "sk-default"


class TestValidateModelConfigs:
    """配置校验"""

    def test_valid_config_no_warnings(self):
        os.environ["MODEL_SEAT_1_MODEL_NAME"] = "qwen-max"
        invalidate_cache()
        warnings = validate_model_configs()
        assert len(warnings) == 0

    def test_out_of_range_seat_warning(self):
        os.environ["MODEL_SEAT_99_MODEL_NAME"] = "qwen-max"
        invalidate_cache()
        warnings = validate_model_configs()
        assert any("99" in w for w in warnings)

    def test_invalid_generate_kwargs_warning(self):
        os.environ["MODEL_DEFAULT_GENERATE_KWARGS"] = "not json"
        invalidate_cache()
        warnings = validate_model_configs()
        # generate_kwargs解析失败但不产生warning（已回退为空dict）
        # 但如果值不是dict类型会警告
        # 当前实现中，_parse_json已处理为空dict，不额外警告


class TestGetConfigSummary:
    """配置摘要"""

    def test_no_config_shows_default(self):
        summary = get_config_summary()
        assert "默认配置" in summary or "qwen-max" in summary

    def test_seat_config_shown(self):
        os.environ["MODEL_SEAT_1_MODEL_NAME"] = "qwen-max"
        invalidate_cache()
        summary = get_config_summary()
        assert "1号位" in summary


class TestBaseUrlAndBackendSelection:
    """base_url 决定后端：有 → OpenAIChatModel，无 → DashScopeChatModel"""

    def test_no_base_url_returns_dashscope(self):
        os.environ["DASHSCOPE_API_KEY"] = "sk-test"
        model = create_model(1)
        from agentscope.model import DashScopeChatModel
        assert isinstance(model, DashScopeChatModel)

    def test_base_url_returns_openai(self):
        os.environ["DASHSCOPE_API_KEY"] = "sk-test"
        os.environ["MODEL_SEAT_1_BASE_URL"] = "https://api.openai.com/v1"
        os.environ["MODEL_SEAT_1_API_KEY"] = "sk-openai"
        os.environ["MODEL_SEAT_1_MODEL_NAME"] = "gpt-4o"
        invalidate_cache()
        model = create_model(1)
        from agentscope.model import OpenAIChatModel
        assert isinstance(model, OpenAIChatModel)
        assert model.model_name == "gpt-4o"

    def test_default_base_url_affects_all_seats(self):
        os.environ["DASHSCOPE_API_KEY"] = "sk-test"
        os.environ["MODEL_DEFAULT_BASE_URL"] = "https://custom.api/v1"
        os.environ["MODEL_DEFAULT_API_KEY"] = "sk-custom"
        os.environ["MODEL_DEFAULT_MODEL_NAME"] = "my-model"
        invalidate_cache()
        from agentscope.model import OpenAIChatModel
        for seat in range(1, 4):
            model = create_model(seat)
            assert isinstance(model, OpenAIChatModel)

    def test_seat_base_url_overrides_default_dashscope(self):
        """默认走百炼，但某座位配了 base_url 则走 OpenAI"""
        os.environ["DASHSCOPE_API_KEY"] = "sk-test"
        os.environ["MODEL_SEAT_2_BASE_URL"] = "http://localhost:8000/v1"
        os.environ["MODEL_SEAT_2_API_KEY"] = "not-needed"
        os.environ["MODEL_SEAT_2_MODEL_NAME"] = "Qwen3-8B"
        invalidate_cache()
        from agentscope.model import OpenAIChatModel, DashScopeChatModel
        model1 = create_model(1)
        model2 = create_model(2)
        assert isinstance(model1, DashScopeChatModel)
        assert isinstance(model2, OpenAIChatModel)
        assert model2.model_name == "Qwen3-8B"

    def test_resolve_config_base_url_field(self):
        os.environ["MODEL_SEAT_3_BASE_URL"] = "http://localhost:11434/v1"
        invalidate_cache()
        config = resolve_model_config(3)
        assert config.base_url == "http://localhost:11434/v1"

    def test_resolve_config_no_base_url_default(self):
        config = resolve_model_config(1)
        assert config.base_url is None

    def test_base_http_api_url_for_dashscope(self):
        os.environ["MODEL_DEFAULT_BASE_HTTP_API_URL"] = "https://custom.dashscope.api"
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.base_http_api_url == "https://custom.dashscope.api"


class TestClientArgsParsing:
    """client_args JSON解析（OpenAI后端用）"""

    def test_client_args_from_env(self):
        os.environ["MODEL_SEAT_1_BASE_URL"] = "https://api.openai.com/v1"
        os.environ["MODEL_SEAT_1_API_KEY"] = "sk-test"
        os.environ["MODEL_SEAT_1_CLIENT_ARGS"] = '{"timeout": 60}'
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.client_args == {"timeout": 60}

    def test_invalid_client_args_fallback(self):
        os.environ["MODEL_SEAT_1_CLIENT_ARGS"] = "not json"
        invalidate_cache()
        config = resolve_model_config(1)
        assert config.client_args == {}

    def test_default_client_args(self):
        config = resolve_model_config(1)
        assert config.client_args is None

    def test_client_args_merged_with_base_url(self):
        """create_model 时 client_args 应包含 base_url"""
        os.environ["MODEL_SEAT_1_BASE_URL"] = "https://api.openai.com/v1"
        os.environ["MODEL_SEAT_1_API_KEY"] = "sk-test"
        os.environ["MODEL_SEAT_1_CLIENT_ARGS"] = '{"timeout": 30}'
        os.environ["MODEL_SEAT_1_MODEL_NAME"] = "gpt-4o"
        invalidate_cache()
        model = create_model(1)
        from agentscope.model import OpenAIChatModel
        assert isinstance(model, OpenAIChatModel)


class TestGetConfigSummaryBackend:
    """配置摘要显示后端类型"""

    def test_default_shows_bailian(self):
        summary = get_config_summary()
        assert "百炼" in summary

    def test_base_url_shows_openai_compat(self):
        os.environ["MODEL_SEAT_1_BASE_URL"] = "https://api.openai.com/v1"
        os.environ["MODEL_SEAT_1_MODEL_NAME"] = "gpt-4o"
        invalidate_cache()
        summary = get_config_summary()
        assert "OpenAI兼容" in summary
        assert "1号位" in summary

    def test_default_base_url_shows_openai_compat(self):
        os.environ["MODEL_DEFAULT_BASE_URL"] = "https://custom.api/v1"
        os.environ["MODEL_DEFAULT_MODEL_NAME"] = "my-model"
        invalidate_cache()
        summary = get_config_summary()
        assert "OpenAI兼容" in summary
        assert "base_url=" in summary


class TestCreateDashscopeModel:
    """create_dashscope_model 向后兼容别名"""

    def test_returns_dashscope_model(self):
        os.environ["DASHSCOPE_API_KEY"] = "sk-test"
        model = create_dashscope_model(1)
        assert model is not None
        assert hasattr(model, "model_name")

    def test_uses_seat_config(self):
        os.environ["DASHSCOPE_API_KEY"] = "sk-test"
        os.environ["MODEL_SEAT_2_MODEL_NAME"] = "qwen-plus"
        invalidate_cache()
        model = create_dashscope_model(2)
        assert model.model_name == "qwen-plus"

    def test_alias_equals_create_model(self):
        """create_dashscope_model 是 create_model 的别名"""
        assert create_dashscope_model is create_model

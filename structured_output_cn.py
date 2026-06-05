"""职场狼人杀游戏的结构化输出模型"""
import json
import re
import logging
from typing import Literal, Optional, List, Any, Dict
from pydantic import BaseModel, Field, ValidationError
from agentscope.agent import AgentBase

_logger = logging.getLogger(__name__)

def safe_parse_metadata(msg: Any, expected_fields: List[str] = None) -> Optional[Dict[str, Any]]:
    """安全解析Agent响应的metadata，处理流式输出截断问题
    
    流式响应可能出现：
    1. arguments被分散到多个chunk，需要拼接
    2. JSON格式不完整或损坏
    3. thinking标签污染正文
    4. Pydantic验证错误（LLM返回空dict导致必填字段缺失）
    
    Args:
        msg: Agent返回的消息对象
        expected_fields: 期望的字段列表，用于验证完整性
        
    Returns:
        解析成功的metadata字典，失败返回None
    """
    if msg is None:
        return None
    
    if hasattr(msg, 'content') and msg.content:
        content = msg.content
        if isinstance(content, str):
            if "Validation Error" in content or "Field required" in content:
                _logger.warning(f"LLM返回验证错误: {content[:200]}")
                return None
            content = _clean_thinking_tags(content)
            if not content or content.strip() == "{}":
                _logger.warning("LLM返回空内容")
                return None
    
    metadata = None
    
    if hasattr(msg, 'metadata') and msg.metadata is not None:
        metadata = msg.metadata
        if isinstance(metadata, dict) and len(metadata) == 0:
            _logger.warning("metadata为空dict")
            return None
    elif hasattr(msg, 'content') and msg.content:
        content = msg.content
        if isinstance(content, str):
            metadata = _try_parse_json_from_content(content)
        elif isinstance(content, dict):
            metadata = content
    
    if metadata and expected_fields:
        for field in expected_fields:
            if field not in metadata:
                _logger.warning(f"metadata缺少字段: {field}")
                return None
    
    return metadata

def _clean_thinking_tags(content: str) -> str:
    """清理思考标签，提取纯净的业务内容"""
    thinking_patterns = [
        r'<thought>.*?</thought>',
        r'<think>.*?</think>',
        r'<\|think\|>.*?<\|/think\|>',
        r'<reasoning>.*?</reasoning>',
    ]
    
    cleaned = content
    for pattern in thinking_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    
    cleaned = cleaned.strip()
    return cleaned

def _try_parse_json_from_content(content: str) -> Optional[Dict[str, Any]]:
    """尝试从文本内容中解析JSON"""
    if not content:
        return None
    
    json_patterns = [
        r'\{[^{}]*\}',
        r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}',
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            try:
                result = json.loads(match)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue
    
    return None

def validate_structured_response(response: Any, model_class: type[BaseModel]) -> Optional[BaseModel]:
    """验证并解析结构化响应
    
    Args:
        response: Agent响应
        model_class: 期望的Pydantic模型类
        
    Returns:
        解析成功的模型实例，失败返回None
    """
    if response is None:
        return None
    
    if isinstance(response, model_class):
        return response
    
    if isinstance(response, dict):
        try:
            return model_class(**response)
        except ValidationError as e:
            _logger.warning(f"结构化响应验证失败: {e}")
            return None
    
    if hasattr(response, 'metadata'):
        metadata = safe_parse_metadata(response)
        if metadata:
            try:
                return model_class(**metadata)
            except ValidationError as e:
                _logger.warning(f"metadata验证失败: {e}")
                return None
    
    return None

class DiscussionModelCN(BaseModel):
    """中文版讨论输出格式"""

    reasoning_steps: List[str] = Field(
        description="分步推理过程：1.梳理已知线索 2.分析当前局势 3.制定策略理由 4.得出结论",
        min_length=1,
    )
    key_evidence: str = Field(
        description="支持你观点的关键证据或推理依据",
    )
    reach_agreement: bool = Field(
        description="是否已达成一致意见",
    )
    confidence_level: int = Field(
        description="对当前推理的信心程度(1-10)",
        ge=1, le=10
    )
    
def get_vote_model_cn(agents: list[AgentBase]) -> type[BaseModel]:
    """获取中文版投票模型"""
    
    class VoteModelCN(BaseModel):
        """中文版投票输出格式"""
        
        vote: Literal[tuple(_.name for _ in agents)] = Field(
            description="你要投票淘汰的玩家座位号（如3号）",
        )
        reason: str = Field(
            description="投票理由，简要说明为什么选择此人",
        )
        suspicion_level: int = Field(
            description="对被投票者的怀疑程度(1-10)",
            ge=1, le=10
        )
    
    return VoteModelCN

class WitchActionModelCN(BaseModel):
    """中文版女巫行动模型"""
    
    use_antidote: bool = Field(
        description="是否使用留人offer挽留",
        default=False
    )
    use_poison: bool = Field(
        description="是否使用辞退信开除",
        default=False
    )
    target_name: Optional[str] = Field(
        description="目标玩家座位号（如4号，挽留或辞退的对象）",
        default=None
    )
    action_reason: Optional[str] = Field(
        description="行动理由",
        default=None
    )
    

def get_seer_model_cn(agents: list[AgentBase]) -> type[BaseModel]:
    """获取中文版预言家模型"""
    
    class SeerModelCN(BaseModel):
        """中文版预言家背调格式"""
    
        target: Literal[tuple(_.name for _ in agents)] = Field(
            description="要背调的玩家座位号（如5号）",
        )
        check_reason: str = Field(
            description="背调此人的原因",
        )
        priority_level: int = Field(
            description="背调优先级(1-10)",
            ge=1, le=10
        )
    
    return SeerModelCN

def get_hunter_model_cn(agents: list[AgentBase]) -> type[BaseModel]:
    """获取中文版猎人模型"""

    class HunterModelCN(BaseModel):
        """你已被投票/窃取出局，作为法务总监，你现在必须决定是否发起诉讼带走一名员工。如果你认为是间谍，强烈建议发起诉讼（shoot=true）。"""

        shoot: bool = Field(
            description="是否发起诉讼。你已出局，作为法务总监应积极发起诉讼带走可疑员工（shoot=true）。",
        )
        target: Optional[Literal[tuple(_.name for _ in agents)]] = Field(
            description="诉讼目标玩家座位号（如7号），选择你最认为是商业间谍的存活员工",
            default=None
        )
        shoot_reason: Optional[str] = Field(
            description="诉讼理由，解释为什么选择带走此人",
            default=None
        )

    return HunterModelCN


def get_guard_model_cn(agents: list[AgentBase]) -> type[BaseModel]:
    """获取中文版守护者模型"""

    class GuardModelCN(BaseModel):
        """中文版安保主管保护格式"""

        target: Literal[tuple(_.name for _ in agents)] = Field(
            description="要加密保护的玩家座位号（如2号）",
        )
        guard_reason: str = Field(
            description="加密保护此人的原因",
        )

    return GuardModelCN

class WerewolfKillModelCN(BaseModel):
    """中文版间谍窃取模型"""

    target: str = Field(
        description="要窃取信息的目标玩家座位号（如6号）",
    )
    kill_strategy: str = Field(
        description="窃取策略说明",
    )
    team_coordination: Optional[str] = Field(
        description="与间谍队友的配合计划",
        default=None
    )
    
    
class SpyStrategyModelCN(BaseModel):
    """间谍战术角色与协作计划模型"""

    tactical_role: str = Field(
        description="战术角色：冲锋型/深潜型/低调型/煽动型",
    )
    coordination_plan: Optional[str] = Field(
        description="与间谍队友的协作计划（统一投票方向、伪装目标等）",
        default=None,
    )


def get_literal_choices(model_class: type, field_name: str) -> list[str]:
    """从 Pydantic model 的 Literal 字段提取可选值列表

    用于 HumanAgent 菜单式交互时生成编号选项。

    Args:
        model_class: Pydantic BaseModel 子类
        field_name: 字段名

    Returns:
        Literal 选项列表，非 Literal 字段返回空列表
    """
    if field_name not in model_class.model_fields:
        return []

    field_info = model_class.model_fields[field_name]
    annotation = field_info.annotation

    import typing

    # 直接 Literal
    origin = getattr(annotation, "__origin__", None)
    if origin is typing.Literal:
        return list(annotation.__args__)

    # Optional[Literal[...]] → Union[Literal[...], None]
    if origin is typing.Union:
        for arg in annotation.__args__:
            arg_origin = getattr(arg, "__origin__", None)
            if arg_origin is typing.Literal:
                return list(arg.__args__)

    return []



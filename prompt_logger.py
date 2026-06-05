# -*- coding: utf-8 -*-
"""Prompt日志系统 - 保存每次给LLM的完整prompt"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class PromptLogger:
    """Prompt日志记录器
    
    与游戏日志同步，保存每次LLM调用的完整prompt到txt文件
    文件命名格式：round_{round_num}_phase_{phase}_seq_{seq}.txt
    """
    
    def __init__(self, log_path: str):
        self.log_path = Path(log_path)
        self.prompt_dir = self.log_path.parent / self.log_path.stem
        self.prompt_dir.mkdir(parents=True, exist_ok=True)
        self.call_counter = 0
        
    def _get_filename(self, round_num: int, phase: str, seat: str) -> str:
        """生成prompt文件名"""
        self.call_counter += 1
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"round_{round_num}_phase_{phase}_seat_{seat}_seq_{self.call_counter}_{timestamp}.txt"
        return filename
    
    def save_prompt(
        self,
        messages: List[Dict[str, Any]],
        round_num: int,
        phase: str,
        seat: str,
        model_name: str = "unknown",
        tools: Optional[List[Dict]] = None,
        parameters: Optional[Dict] = None,
    ) -> str:
        """保存完整的prompt到txt文件
        
        Args:
            messages: LLM调用的messages列表
            round_num: 当前轮次
            phase: 当前阶段
            seat: 座位号
            model_name: 模型名称
            tools: Function calling tools
            parameters: 其他参数
            
        Returns:
            保存的文件路径
        """
        filename = self._get_filename(round_num, phase, seat)
        filepath = self.prompt_dir / filename
        
        content_lines = []
        content_lines.append(f"=" * 60)
        content_lines.append(f"PROMPT LOG")
        content_lines.append(f"=" * 60)
        content_lines.append(f"时间: {datetime.now().isoformat()}")
        content_lines.append(f"轮次: {round_num}")
        content_lines.append(f"阶段: {phase}")
        content_lines.append(f"座位: {seat}")
        content_lines.append(f"模型: {model_name}")
        content_lines.append(f"序号: {self.call_counter}")
        content_lines.append(f"=" * 60)
        content_lines.append("")
        
        content_lines.append("【MESSAGES】")
        content_lines.append("-" * 40)
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            msg_content = msg.get("content", "")
            content_lines.append(f"\n--- Message {i+1} [{role}] ---")
            if isinstance(msg_content, str):
                content_lines.append(msg_content)
            elif isinstance(msg_content, list):
                for item in msg_content:
                    if isinstance(item, dict):
                        item_type = item.get("type", "unknown")
                        if item_type == "text":
                            content_lines.append(f"[text]: {item.get('text', '')}")
                        else:
                            content_lines.append(f"[{item_type}]: {json.dumps(item, ensure_ascii=False, indent=2)}")
                    else:
                        content_lines.append(str(item))
            else:
                content_lines.append(json.dumps(msg_content, ensure_ascii=False, indent=2))
        
        if tools:
            content_lines.append("")
            content_lines.append("【TOOLS (Function Calling)】")
            content_lines.append("-" * 40)
            content_lines.append(json.dumps(tools, ensure_ascii=False, indent=2))
        
        if parameters:
            content_lines.append("")
            content_lines.append("【PARAMETERS】")
            content_lines.append("-" * 40)
            content_lines.append(json.dumps(parameters, ensure_ascii=False, indent=2))
        
        content_lines.append("")
        content_lines.append("=" * 60)
        content_lines.append("END OF PROMPT")
        content_lines.append("=" * 60)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(content_lines))
        
        return str(filepath)
    
    def close(self) -> None:
        pass


class CombinedLogger:
    """组合日志记录器 - 同时记录游戏事件和Prompt"""
    
    def __init__(self, log_path: str):
        from game_logger import JSONGameLogger
        self.game_logger = JSONGameLogger(log_path)
        self.prompt_logger = PromptLogger(log_path)
        self.log_path = log_path
        
    def log_game_init(self, *args, **kwargs) -> None:
        self.game_logger.log_game_init(*args, **kwargs)
        
    def log_model_call(self, *args, output_content=None, **kwargs) -> None:
        self.game_logger.log_model_call(*args, output_content=output_content, **kwargs)
        
    def log_decision(self, *args, **kwargs) -> None:
        self.game_logger.log_decision(*args, **kwargs)
        
    def log_skill_resolution(self, *args, **kwargs) -> None:
        self.game_logger.log_skill_resolution(*args, **kwargs)
        
    def log_state_snapshot(self, *args, **kwargs) -> None:
        self.game_logger.log_state_snapshot(*args, **kwargs)
        
    def log_game_over(self, *args, **kwargs) -> None:
        self.game_logger.log_game_over(*args, **kwargs)
        
    def log_night_start(self, *args, **kwargs) -> None:
        self.game_logger.log_night_start(*args, **kwargs)
        
    def log_day_start(self, *args, **kwargs) -> None:
        self.game_logger.log_day_start(*args, **kwargs)
        
    def log_death(self, *args, **kwargs) -> None:
        self.game_logger.log_death(*args, **kwargs)
        
    def log_vote_result(self, *args, **kwargs) -> None:
        self.game_logger.log_vote_result(*args, **kwargs)
        
    def log_error(self, *args, **kwargs) -> None:
        self.game_logger.log_error(*args, **kwargs)
        
    def save_prompt(self, *args, **kwargs) -> str:
        # 真人玩家无需保存 prompt
        model_name = kwargs.get("model_name", "")
        if model_name == "human":
            return ""
        return self.prompt_logger.save_prompt(*args, **kwargs)
        
    def close(self) -> None:
        self.game_logger.close()
        self.prompt_logger.close()
"""职场狼人杀游戏工具函数"""
import asyncio
import functools
import logging
import random
import traceback
from typing import List, Dict, Optional, Any, Callable
from collections import Counter

from agentscope.agent import AgentBase
from agentscope.message import Msg

# 游戏常量
MAX_GAME_ROUND = 10
MAX_DISCUSSION_ROUND = 3
MAX_RETRIES = 3

# 自定义异常
class GameError(Exception):
    """游戏逻辑错误基类"""
    pass

class APIError(GameError):
    """DashScope API调用错误"""
    pass

class ValidationError(GameError):
    """LLM输出校验错误（目标不在存活列表等）"""
    pass


def retry_on_failure(max_retries: int = MAX_RETRIES, retry_delay: float = 1.0):
    """异步重试装饰器，仅在APIError时重试"""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except APIError as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))
                except (ValidationError, GameError):
                    raise
            raise last_error
        return wrapper
    return decorator
def format_player_list(players: List[AgentBase], show_roles: bool = False) -> str:
    """格式化玩家列表为中文显示"""
    if not players:
        return "无玩家"
    
    if show_roles:
        return "、".join([f"{p.name}({getattr(p, 'role', '未知')})" for p in players])
    else:
        return "、".join([p.name for p in players])
    
def majority_vote_cn(votes: Dict[str, str]) -> tuple[str, str]:
    """中文版多数投票统计，支持平票处理和空票过滤"""
    if not votes:
        return "无人", 0

    # 过滤None和空值
    valid_votes = {voter: target for voter, target in votes.items() if target}
    if not valid_votes:
        return "无人", 0

    vote_counts = Counter(valid_votes.values())
    top_two = vote_counts.most_common(2)
    most_voted_name, most_voted_count = top_two[0]

    # 平票处理：如果最高票数有多个候选人并列，则无人出局
    if len(top_two) > 1 and top_two[1][1] == most_voted_count:
        return "平票无人出局", 0

    return most_voted_name, most_voted_count

def check_winning_cn(alive_players: List[AgentBase], roles: Dict[str, str]) -> Optional[str]:
    """检查中文版游戏胜利条件
    
    胜负判定规则（按优先级排序）：
    1. 间谍全部出局 → 公司阵营胜利
    2. 间谍人数 >= 好人人数 → 间谍阵营胜利（人数优势，优先级高于屠神屠民）
    3. 神职角色全部出局 → 间谍阵营胜利（屠神）
    4. 平民全部出局 → 间谍阵营胜利（屠民）
    
    Args:
        alive_players: 存活的玩家列表
        roles: 玩家座位号→角色映射
        
    Returns:
        胜利信息字符串，未满足条件返回None
    """
    if not alive_players:
        return "间谍阵营胜利！公司全员出局！"
    
    alive_roles = [roles.get(p.name, "村民") for p in alive_players]
    
    werewolf_count = alive_roles.count("狼人")
    
    god_roles = ["预言家", "女巫", "猎人", "守护者"]
    god_count = sum(1 for r in alive_roles if r in god_roles)
    
    villager_count = alive_roles.count("村民")
    
    good_count = god_count + villager_count
    
    if werewolf_count == 0:
        return "公司阵营胜利！所有间谍已被清除！"
    
    if werewolf_count >= good_count:
        return "间谍阵营胜利！间谍已经控制了公司（人数优势）！"
    
    if god_count == 0 and werewolf_count > 0:
        return "间谍阵营胜利！所有神职角色已被淘汰（屠神成功）！"
    
    if villager_count == 0 and werewolf_count > 0:
        return "间谍阵营胜利！所有平民已被淘汰（屠民成功）！"
    
    return None

class GameModerator(AgentBase):
    """中文版游戏主持人"""

    def __init__(self) -> None:
        super().__init__()
        self.name = "游戏主持人"
        self._narration_logger = logging.getLogger("werewolf.game.moderator")

    async def announce(self, content: str) -> Msg:
        """发布游戏公告"""
        msg = Msg(
            name=self.name,
            content=content,
            role="system"
        )
        await self.print(msg)
        self._narration_logger.info(content)
        return msg

    def log_player_speech(self, player_name: str, content: str, round_num: int = 0, phase: str = "") -> None:
        """记录玩家发言到叙事日志"""
        self._narration_logger.info(f"{player_name}: {content}")

    async def night_announcement(self, round_num: int) -> Msg:
        """夜晚阶段公告"""
        content = f"[夜晚] 第{round_num}夜降临，天黑请闭眼..."
        return await self.announce(content)

    async def day_announcement(self, round_num: int) -> Msg:
        """白天阶段公告"""
        content = f"[白天] 第{round_num}天天亮了，请大家睁眼..."
        return await self.announce(content)

    async def death_announcement(self, dead_players: List[str]) -> Msg:
        """死亡公告"""
        if not dead_players:
            content = "昨夜平安无事，无人领大礼包。"
        else:
            content = f"昨夜，{format_player_list_str(dead_players)}领了大礼包，正式离职。"
        return await self.announce(content)

    async def vote_result_announcement(self, vote_out: str, vote_count: int) -> Msg:
        """投票结果公告"""
        content = f"投票结果：{vote_out}以{vote_count}票被全员投出，领大礼包走人。"
        return await self.announce(content)

    async def game_over_announcement(self, winner: str) -> Msg:
        """游戏结束公告"""
        content = f"[游戏结束] {winner}"
        return await self.announce(content)

def format_player_list_str(players: List[str]) -> str:
    """格式化玩家姓名列表"""
    if not players:
        return "无人"
    return "、".join(players)


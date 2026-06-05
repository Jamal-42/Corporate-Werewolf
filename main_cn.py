# -*- coding: utf-8 -*-
"""
职场狼人杀 - 基于AgentScope的多智能体狼人杀游戏
融合现代职场角色和传统狼人杀玩法
"""
import asyncio
import argparse
import logging
import os
import random
import sys
from datetime import datetime
from typing import List, Dict, Optional, Any

from agentscope.agent import ReActAgent, AgentBase
from agentscope.model import DashScopeChatModel
from agentscope.pipeline import MsgHub, sequential_pipeline, fanout_pipeline
from agentscope.formatter import DashScopeMultiAgentFormatter
from agentscope.message import Msg

from prompt_cn import PromptManager
from game_roles import GameRoles
from structured_output_cn import (
    DiscussionModelCN,
    get_vote_model_cn,
    WitchActionModelCN,
    get_seer_model_cn,
    get_hunter_model_cn,
    get_guard_model_cn,
    WerewolfKillModelCN,
    SpyStrategyModelCN,
    safe_parse_metadata,
    validate_structured_response,
)
from shared.parsing_utils import extract_agent_messages
from utils_cn import (
    check_winning_cn,
    majority_vote_cn,
    format_player_list,
    GameModerator,
    MAX_GAME_ROUND,
    MAX_RETRIES,
    GameError,
    APIError,
    ValidationError,
    retry_on_failure,
)
from game_logger import JSONGameLogger
from skills import init_skills
from skills.registry import get_global_registry
from context_manager import ContextManager
from model_config import create_model, validate_model_configs, get_config_summary
from logging_config import setup_logging, setup_tracing, get_logger
from skills_agent.dispatcher import SkillsDispatcher


class OfficeWerewolfGame:
    """职场狼人杀游戏主类"""

    def __init__(self, logger: Optional[JSONGameLogger] = None, prompt_version: str = "v2",
                 witch_can_self_save_first_night: bool = True,
                 allow_werewolf_self_kill: bool = True,
                 context_window: int = 80,
                 skills_version: Optional[str] = None,
                 skills_targets: str = "all",
                 human_seats: Optional[set] = None):
        self.players: Dict[str, AgentBase] = {}
        self.roles: Dict[str, str] = {}
        self.moderator = GameModerator()
        self.alive_players: List[AgentBase] = []
        self.werewolves: List[AgentBase] = []
        self.villagers: List[AgentBase] = []
        self.seer: List[AgentBase] = []
        self.witch: List[AgentBase] = []
        self.hunter: List[AgentBase] = []
        self.guard: List[AgentBase] = []

        self.witch_has_antidote = True
        self.witch_has_poison = True
        self.last_guarded: Optional[str] = None
        self.logger = logger
        self.prompt_manager = PromptManager(prompt_version)
        self.witch_can_self_save_first_night = witch_can_self_save_first_night
        self.allow_werewolf_self_kill = allow_werewolf_self_kill
        self.round_num = 0

        self._game_log = get_logger("main", layer="game")
        self._diag_log = get_logger("game", layer="diag")
        self._model_log = get_logger("model", layer="diag")
        self._context_log = get_logger("context", layer="diag")

        self.skill_registry = init_skills()

        self.seat_characters: Dict[str, str] = {}

        self.context_manager = ContextManager(max_messages=context_window)

        self.seat_model_info: Dict[int, Dict[str, Any]] = {}

        self.agent_by_seat: Dict[int, AgentBase] = {}

        # Skills调度器
        self.skills_dispatcher: Optional[SkillsDispatcher] = None
        if skills_version:
            self.skills_dispatcher = SkillsDispatcher(skills_version, skills_targets)

        # 真人玩家座位号
        self.human_seats: set = human_seats or set()

    def get_seat_num(self, agent: AgentBase) -> int:
        """从Agent对象获取座位号，避免字符串解析"""
        for seat_num, a in self.agent_by_seat.items():
            if a is agent or a.name == agent.name:
                return seat_num
        return 0

    def get_agent_by_seat(self, seat_num: int) -> Optional[AgentBase]:
        """通过座位号获取Agent"""
        return self.agent_by_seat.get(seat_num)

    def get_seat_name(self, seat_num: int) -> str:
        """获取座位号标准名（如1号）"""
        return f"{seat_num}号"

    def get_role_by_seat(self, seat_num: int) -> str:
        """通过座位号获取游戏角色"""
        return self.seat_model_info.get(seat_num, {}).get("role", "未知")

    @property
    def alive_player_names(self) -> list[str]:
        """存活玩家名列表（避免反复写 [p.name for p in self.alive_players]）"""
        return [p.name for p in self.alive_players]

    def _build_game_state(self, seat: int, **overrides) -> dict[str, Any]:
        """构建技能游戏状态字典的通用基础

        所有 phase 的 game_state 都包含 logger / round_num / model_info，
        各 phase 通过 overrides 添加额外字段。
        """
        base = {
            "logger": self.logger,
            "round_num": self.round_num,
            "model_info": self.seat_model_info.get(seat, {}),
        }
        base.update(overrides)
        return base

    def _check_and_log_game_over(self, round_num: int) -> bool:
        """检查胜利条件并记录游戏结束，返回 True 表示游戏结束"""
        winner = check_winning_cn(self.alive_players, self.roles)
        if not winner:
            return False
        self._game_log.info(f"游戏结束: {winner}")
        return True

    async def _handle_game_over(self, winner: str, round_num: int):
        """处理游戏结束：公告 + 日志"""
        await self.moderator.game_over_announcement(winner)
        if self.logger:
            skills_meta = self.skills_dispatcher.get_meta() if self.skills_dispatcher else {}
            self.logger.log_game_over(
                winner=winner,
                total_rounds=round_num,
                survivors=[{"name": self.seat_characters.get(p.name, p.name), "seat": p.name, "role": self.roles.get(p.name, "未知")} for p in self.alive_players],
                skills_injection=skills_meta,
            )

    async def create_player(self, role: str, character: str, seat_num: int = 1) -> AgentBase:
        """创建职场角色玩家"""
        name = f"{seat_num}号"
        self.roles[name] = role
        self.seat_characters[name] = character

        role_prompt = self.prompt_manager.get_role_prompt(role, character, seat_num)

        if seat_num in self.human_seats:
            # 真人玩家：使用 HumanAgent
            from human_agent import HumanAgent
            agent = HumanAgent(
                name=name,
                sys_prompt=role_prompt,
                seat_num=seat_num,
            )
            self._model_log.info(f"  {seat_num}号位 {character}({role}): 🧑 人类玩家")
        else:
            # AI 玩家：使用 ReActAgent
            model = create_model(seat_num)
            agent = ReActAgent(
                name=name,
                sys_prompt=role_prompt,
                model=model,
                formatter=DashScopeMultiAgentFormatter(),
            )

        await agent.observe(
            await self.moderator.announce(
                f"【{name}】你在这场职场狼人杀中扮演{GameRoles.get_role_desc(role)}，"
                f"你的身份是{role}。你的职场人设是{character}。{GameRoles.get_role_ability(role)}"
            )
        )

        self.players[name] = agent
        self.agent_by_seat[seat_num] = agent

        # Skills初始注入（跳过真人玩家）
        if self.skills_dispatcher and seat_num not in self.human_seats:
            faction = "间谍" if role == "狼人" else "公司"
            self.skills_dispatcher.inject_initial(agent, seat_num, role, faction, character)

        # 记录模型/座位信息
        if seat_num in self.human_seats:
            self.seat_model_info[seat_num] = {
                "character_name": character,
                "role": role,
                "model_name": "human",
                "is_human": True,
            }
        else:
            from model_config import resolve_model_config
            cfg = resolve_model_config(seat_num)
            self.seat_model_info[seat_num] = {
                "character_name": character,
                "role": role,
                "model_name": cfg.model_name,
                "enable_thinking": cfg.enable_thinking,
                "generate_kwargs": cfg.generate_kwargs,
            }
            self._model_log.info(f"  {seat_num}号位 {character}({role}): model={cfg.model_name}, thinking={cfg.enable_thinking}")

        return agent

    async def setup_game(self, player_count: int = 9):
        """设置游戏"""
        self._game_log.info("开始设置职场狼人杀游戏...")

        roles = GameRoles.get_standard_setup(player_count)
        random.shuffle(roles)
        characters = random.sample(GameRoles.get_all_characters(), player_count)

        for seat_num, (role, character) in enumerate(zip(roles, characters), 1):
            agent = await self.create_player(role, character, seat_num)
            self.alive_players.append(agent)

            if role == "狼人":
                self.werewolves.append(agent)
            elif role == "预言家":
                self.seer.append(agent)
            elif role == "女巫":
                self.witch.append(agent)
            elif role == "猎人":
                self.hunter.append(agent)
            elif role == "守护者":
                self.guard.append(agent)
            else:
                self.villagers.append(agent)

        await self.moderator.announce(
            f"职场狼人杀游戏开始！参与者：{format_player_list(self.alive_players)}"
        )
        
        game_rules = """
【职场狼人杀游戏规则】

[术语映射]
- 商业间谍 = 狼人：窃取公司核心信息，淘汰员工
- HR总监 = 预言家：背调查验员工身份，应尽早亮明身份公布信息
- CEO = 女巫：手握留人offer和辞退信，关键时刻拍板决策
- 法务总监 = 猎人：离职时可发起诉讼带走一人
- 安保主管 = 守护者：每晚加密保护一人，不能连续保护同一人
- 普通员工 = 村民：靠推理投票找出商业间谍
- 背调 = 查验：HR总监每晚查验一名员工身份
- 窃取信息 = 淘汰：商业间谍每晚淘汰一名员工
- 亮明身份 = 自曝：公开自己的角色身份
- 冒充HR总监 = 悍跳：商业间谍假装自己是HR总监
- 背调查出间谍 = 查杀：公布某人是商业间谍
- 背调查出好人 = 金水：公布某人是好人员工

[游戏目标]
- 商业间谍阵营：淘汰足够多的好人员工，或让间谍人数>=好人人数
- 公司阵营：推理找出所有商业间谍，通过投票让他们离职

[角色技能]
- 商业间谍：每晚协商窃取一名员工信息；白天可冒充HR总监混淆信息
- HR总监：每晚背调一人查验身份；应尽早亮明身份公布背调信息引导投票
- CEO：手握留人offer和辞退信，各只能用一次，一晚只能用一份
- 法务总监：被投票/窃取离职时可发起诉讼带走一人
- 安保主管：每晚加密保护一人，不能连续两晚保护同一人
- 普通员工：无特殊技能，靠观察推理投票找出商业间谍

[核心玩法：HR总监与商业间谍博弈]
- HR总监：应主动亮明身份，公布背调信息（查杀商业间谍或验证好人）
- 商业间谍冒充：可假装是HR总监，给好人发"背调查出间谍"或给队友发"背调查出好人"
- 对质机制：当两人都声称是HR总监时，用背调结果证明身份

[游戏流程]
- 每晚：商业间谍协商窃取 -> HR总监背调 -> 安保主管保护 -> CEO决策 -> 结算离职
- 每天：例会讨论（HR总监亮明身份/商业间谍冒充） -> 归票发言 -> 公开投票 -> 员工离职

[策略建议]
- HR总监策略：第一晚查出商业间谍后，第二天立即亮明身份公布查杀信息
- 商业间谍策略：可选冒充HR总监抢先亮明身份，或等真HR总监亮明后对质质疑
- 好人策略：注意两个"HR总监"的信息矛盾，用投票结果验证谁更可信
- 发言建议：HR总监亮明身份时说"我是HR总监，背调X号发现是商业间谍"

[重要提醒]
- 所有玩家以座位号相称（如1号、3号），不使用职场人设名
- 发言要符合人设风格，论述要有逻辑，观点要清晰
- 亮明身份时需提供可信证据（如背调结果）
"""
        rules_msg = await self.moderator.announce(game_rules)
        for agent in self.alive_players:
            await agent.observe(rules_msg)
        
        self._game_log.info(f"游戏设置完成，共{len(self.alive_players)}名玩家")

        if self.logger:
            character_role_map = []
            for seat_num in range(1, player_count + 1):
                model_info = self.seat_model_info.get(seat_num, {})
                character = model_info.get("character_name", "未知")
                role = model_info.get("role", "未知")
                traits = GameRoles.CHARACTER_TRAITS.get(character, {})
                character_role_map.append({
                    "character_name": character,
                    "role": role,
                    "seat_num": seat_num,
                    "workplace_title": traits.get("title", "未知"),
                    "personality": traits.get("personality", ""),
                    "speaking_style": traits.get("speaking_style", ""),
                    "game_strategy": traits.get("game_strategy", ""),
                    "model_name": model_info.get("model_name", "qwen-max"),
                    "enable_thinking": model_info.get("enable_thinking", True),
                })
            self.logger.log_game_init(
                player_count=player_count,
                character_role_map=character_role_map,
            )

    def _log_agent_response(self, agent, response_msg: Msg, phase: str = "unknown") -> None:
        """记录单个Agent的响应到日志
        
        Args:
            agent: 发言的Agent
            response_msg: Agent返回的消息对象
            phase: 当前阶段
        """
        if not response_msg:
            return
            
        seat = self.get_seat_num(agent)
        model_info = self.seat_model_info.get(seat, {})
        
        content = getattr(response_msg, 'content', None)
        metadata = getattr(response_msg, 'metadata', None)
        
        if content and isinstance(content, str):
            self.moderator.log_player_speech(
                player_name=agent.name,
                content=content,
                round_num=self.round_num,
                phase=phase,
            )
        
        if self.logger and hasattr(self.logger, 'save_prompt'):
            messages = extract_agent_messages(agent)

            try:
                self.logger.save_prompt(
                    messages=messages,
                    round_num=self.round_num,
                    phase=phase,
                    seat=agent.name,
                    model_name=model_info.get("model_name", "unknown"),
                )
            except Exception as e:
                self._diag_log.warning(f"保存prompt失败: {e}")
        
        if self.logger:
            output_dict = {
                "content": content if isinstance(content, str) else str(content) if content else None,
                "metadata": metadata,
            }
            self.logger.log_model_call(
                player=f"{seat}号",
                role=self.get_role_by_seat(seat),
                phase=phase,
                model_name=model_info.get("model_name", "qwen-max"),
                prompt_version=self.prompt_manager.version,
                seat=agent.name,
                output_content=output_dict,
            )

    async def _logged_sequential_pipeline(self, agents, msg=None, phase: str = "discussion"):
        """带日志记录的顺序发言pipeline
        
        sequential_pipeline 返回单个 Msg（最后一个 agent 的输出）
        需要在每个 agent 发言后立即记录
        """
        last_result = None
        for agent in agents:
            if msg:
                result = await agent(msg=msg)
            else:
                result = await agent()
            self._log_agent_response(agent, result, phase=phase)
            last_result = result
        return last_result

    async def _logged_fanout_pipeline(self, agents, msg=None, structured_model=None, phase: str = "vote", enable_gather: bool = False) -> List[Msg]:
        """带日志记录的并行发言pipeline
        
        fanout_pipeline 返回 List[Msg]
        """
        results = await fanout_pipeline(agents, msg=msg, structured_model=structured_model, enable_gather=enable_gather)
        if results:
            for agent, result in zip(agents, results):
                self._log_agent_response(agent, result, phase=phase)
        return results

    async def _safe_agent_call(self, agent, structured_model=None, max_retries=MAX_RETRIES, phase="unknown"):
        """带重试的安全Agent调用，同时记录模型输出"""
        seat = self.get_seat_num(agent)
        model_info = self.seat_model_info.get(seat, {})
        is_human = model_info.get("is_human", False)

        messages = extract_agent_messages(agent)

        tools = None
        if structured_model:
            from pydantic import BaseModel
            if isinstance(structured_model, type) and issubclass(structured_model, BaseModel):
                schema = structured_model.model_json_schema()
                tools = [{
                    "type": "function",
                    "function": {
                        "name": structured_model.__name__,
                        "description": getattr(structured_model, '__doc__', ''),
                        "parameters": schema
                    }
                }]

        if self.logger and hasattr(self.logger, 'save_prompt') and not is_human:
            try:
                self.logger.save_prompt(
                    messages=messages,
                    round_num=self.round_num,
                    phase=phase,
                    seat=agent.name,
                    model_name=model_info.get("model_name", "unknown"),
                    tools=tools,
                )
            except Exception as e:
                self._diag_log.warning(f"保存prompt失败: {e}")
        
        last_output_content = None
        last_metadata = None
        
        for attempt in range(max_retries):
            try:
                if structured_model:
                    result = await agent(structured_model=structured_model)
                else:
                    result = await agent()
                
                if result:
                    if hasattr(result, 'content') and result.content:
                        content = result.content
                        if isinstance(content, str) and ("Validation Error" in content or "Field required" in content):
                            self._diag_log.warning(f"LLM返回验证错误响应: {content[:200]}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            return None
                    
                    last_output_content = getattr(result, 'content', None)
                    if hasattr(result, 'metadata') and result.metadata:
                        last_metadata = result.metadata
                    
                    if self.logger:
                        output_dict = {
                            "content": last_output_content if isinstance(last_output_content, str) else str(last_output_content) if last_output_content else None,
                            "metadata": last_metadata,
                        }
                        self.logger.log_model_call(
                            player=f"{seat}号",
                            role=self.get_role_by_seat(seat),
                            phase=phase,
                            model_name=model_info.get("model_name", "qwen-max"),
                            prompt_version=self.prompt_manager.version,
                            seat=agent.name,
                            output_content=output_dict,
                        )
                        
                        if last_output_content and isinstance(last_output_content, str):
                            self.moderator.log_player_speech(
                                player_name=agent.name,
                                content=last_output_content,
                                round_num=self.round_num,
                                phase=phase,
                            )
                return result
            except Exception as e:
                error_msg = str(e)
                if "rate" in error_msg.lower() or "limit" in error_msg.lower() or "timeout" in error_msg.lower():
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise APIError(f"API调用失败(重试{max_retries}次): {e}")
                elif "parameter" in error_msg.lower() or "invalid" in error_msg.lower() or "validation" in error_msg.lower():
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise ValidationError(f"LLM输出校验失败: {e}")
                elif "401" in error_msg or "apikey" in error_msg.lower() or "api_key" in error_msg.lower() or "api-key" in error_msg.lower():
                    # 百炼平台偶发401(尤其第三方模型如DeepSeek)，重试即可
                    if attempt < max_retries - 1:
                        self._diag_log.warning(f"API返回401(第{attempt+1}次)，重试中...: {error_msg[:200]}")
                        await asyncio.sleep(3 * (attempt + 1))
                        continue
                    raise APIError(f"API Key验证失败(重试{max_retries}次): {e}")
                else:
                    raise GameError(f"Agent调用异常: {e}")
        return None

    async def werewolf_phase(self, round_num: int) -> Optional[str]:
        """间谍阶段 - 真正的夜间协商机制"""
        if not self.werewolves:
            return None

        # Skills阶段注入：间谍
        if self.skills_dispatcher:
            for wolf in self.werewolves:
                seat = self.get_seat_num(wolf)
                role = self.get_role_by_seat(seat)
                await self.skills_dispatcher.inject_phase_skills(
                    wolf, "werewolf", round_num, role, seat)

        await self.moderator.announce("间谍请睁眼，今晚可以自由协商窃取目标...")

        wolf_names = ", ".join([w.name for w in self.werewolves])
        
        if round_num == 1:
            announcement_content = (
                f"间谍们，请讨论今晚的目标。存活员工：{format_player_list(self.alive_players)}\n\n"
                f"【第一夜·身份确认】你们的间谍队友是：{wolf_names}。\n"
                f"这是游戏开始的第一夜，没有任何发言历史、投票记录或淘汰信息。\n"
                f"请先讨论战术安排：谁负责冲锋（积极发言带节奏）、谁负责倒钩（假装好人跟风）、"
                f"谁负责深潜（低调苟活），然后再确定窃取目标。"
            )
        else:
            announcement_content = f"间谍们，请讨论今晚的目标。存活员工：{format_player_list(self.alive_players)}"

        async with MsgHub(
            self.werewolves,
            enable_auto_broadcast=True,
            announcement=await self.moderator.announce(announcement_content),
        ) as werewolves_hub:
            discussion_rounds = 2 if len(self.werewolves) > 1 else 1
            
            for round_idx in range(discussion_rounds):
                if len(self.werewolves) > 1:
                    round_prompt = (
                        f"第{round_idx + 1}轮讨论：" 
                        if round_num > 1 
                        else f"第{round_idx + 1}轮讨论（战术安排阶段）：请依次发言，讨论战术分工和窃取目标。"
                    )
                    await self._logged_sequential_pipeline(
                        self.werewolves,
                        msg=await self.moderator.announce(round_prompt),
                        phase="werewolf_discussion",
                    )
                else:
                    single_result = await self.werewolves[0](
                        msg=await self.moderator.announce("请发表你的意见")
                    )
                    self._log_agent_response(self.werewolves[0], single_result, phase="werewolf_discussion")

            werewolves_hub.set_auto_broadcast(False)
            kill_votes = await self._logged_fanout_pipeline(
                self.werewolves,
                msg=await self.moderator.announce(
                    "讨论结束，请私密投票选择窃取目标（每人投一票，只能投非间谍的存活员工）"
                ),
                structured_model=WerewolfKillModelCN,
                phase="werewolf_vote",
                enable_gather=False,
            )

            votes = {}
            wolf_names = {w.name for w in self.werewolves}
            for i, vote_msg in enumerate(kill_votes):
                meta = safe_parse_metadata(vote_msg)
                if meta:
                    target = meta.get("target")
                    alive_names = self.alive_player_names
                    if target and target in alive_names:
                        # 狼人自刀防护：不允许狼人投狼人
                        if target in wolf_names:
                            self._diag_log.warning(f"狼人{self.werewolves[i].name}试图击杀同伴{target}，已过滤该票")
                            votes[self.werewolves[i].name] = None
                        else:
                            votes[self.werewolves[i].name] = target
                    else:
                        votes[self.werewolves[i].name] = None
                else:
                    valid_targets = [p.name for p in self.alive_players if p not in self.werewolves]
                    if valid_targets:
                        votes[self.werewolves[i].name] = random.choice(valid_targets)

            killed_player, vote_count = majority_vote_cn(votes)
            
            if not killed_player and votes:
                all_targets = [t for t in votes.values() if t]
                if all_targets:
                    killed_player = random.choice(all_targets)
                    self._diag_log.warning(f"间谍投票分散，随机选择目标: {killed_player}")
            
            if not killed_player:
                non_wolf_targets = [p.name for p in self.alive_players if p not in self.werewolves]
                if non_wolf_targets:
                    killed_player = random.choice(non_wolf_targets)
                    self._diag_log.warning(f"间谍无有效投票，随机选择目标: {killed_player}")

            if self.logger and killed_player:
                for wolf in self.werewolves:
                    seat = self.get_seat_num(wolf)
                    self.logger.log_decision(
                        round_num=round_num,
                        phase="werewolf",
                        player=f"{seat}号",
                        role="狼人",
                        action="间谍窃取",
                        target=votes.get(wolf.name),
                        reasoning_steps=None,
                        key_evidence=None,
                        full_output=None,
                        seat=f"{seat}号",
                    )
            return killed_player

    async def seer_phase(self):
        """预言家阶段（HR背调）"""
        if not self.seer:
            return

        seer_agent = self.seer[0]

        # Skills阶段注入：预言家
        if self.skills_dispatcher:
            seat = self.get_seat_num(seer_agent)
            role = self.get_role_by_seat(seat)
            await self.skills_dispatcher.inject_phase_skills(
                seer_agent, "seer", self.round_num, role, seat)

        await self.moderator.announce("HR总监请睁眼，选择要做背景调查的员工...")

        skill = self.skill_registry.get_skill("预言家")
        seat = self.get_seat_num(seer_agent)
        game_state = self._build_game_state(seat)
        if skill:
            result = await skill.execute(seer_agent, self.alive_players, game_state)
        else:
            try:
                check_result = await self._safe_agent_call(
                    seer_agent,
                    structured_model=get_seer_model_cn(self.alive_players),
                    phase="seer"
                )
                meta = safe_parse_metadata(check_result)
                if meta and meta.get("target"):
                    result = {"target": meta.get("target"), "check_reason": meta.get("check_reason")}
                else:
                    fallback_target = random.choice(self.alive_players)
                    result = {"target": fallback_target.name}
                    self._diag_log.warning(f"预言家LLM返回无效结果，随机选择背调目标: {fallback_target.name}")
            except Exception as e:
                fallback_target = random.choice(self.alive_players)
                result = {"target": fallback_target.name}
                self._diag_log.warning(f"预言家Agent调用异常({e})，随机选择背调目标: {fallback_target.name}")

        if not result or not result.get("target"):
            return

        target_name = result["target"]
        alive_names = self.alive_player_names
        if target_name not in alive_names:
            # 无效目标：重试最多2次，仍无效则随机选择存活玩家
            self._diag_log.warning(f"预言家选择了无效目标{target_name}，开始重试")
            for retry in range(2):
                try:
                    retry_result = await self._safe_agent_call(
                        seer_agent,
                        structured_model=get_seer_model_cn(self.alive_players),
                        phase="seer"
                    )
                    retry_meta = safe_parse_metadata(retry_result)
                    if retry_meta and retry_meta.get("target"):
                        retry_target = retry_meta["target"]
                        if retry_target in self.alive_player_names:
                            target_name = retry_target
                            break
                except Exception as e:
                    self._diag_log.warning(f"预言家重试异常({e})")
            else:
                # 重试都失败，随机选择存活玩家
                fallback = random.choice(self.alive_players)
                target_name = fallback.name
                self._diag_log.warning(f"预言家重试后仍无效，随机选择: {target_name}")

        target_role = self.roles.get(target_name, "村民")
        result_msg = f"背调结果：{target_name}是{'间谍' if target_role == '狼人' else '清白员工'}"
        await seer_agent.observe(await self.moderator.announce(result_msg))

        self.context_manager.add_key_event(self.round_num, "seer_result", result_msg)

        if self.logger:
            self.logger.log_decision(
                round_num=self.round_num,
                phase="seer",
                player=f"{seat}号",
                role="预言家",
                action="HR背调",
                target=target_name,
                reasoning_steps=None,
                key_evidence=f"背调结果：{target_role}",
                full_output=None,
                seat=f"{seat}号",
            )

    async def guard_phase(self, round_num: int) -> Optional[str]:
        """守护者阶段（安保加密）"""
        if not self.guard:
            return None

        guard_agent = self.guard[0]

        # Skills阶段注入：守护者
        if self.skills_dispatcher:
            seat = self.get_seat_num(guard_agent)
            role = self.get_role_by_seat(seat)
            await self.skills_dispatcher.inject_phase_skills(
                guard_agent, "guard", round_num, role, seat)

        await self.moderator.announce("安保主管请睁眼，选择今晚要加密保护的员工...")

        skill = self.skill_registry.get_skill("守护者")
        seat = self.get_seat_num(guard_agent)
        game_state = self._build_game_state(seat, last_guarded=self.last_guarded)
        if skill:
            result = await skill.execute(guard_agent, self.alive_players, game_state)
        else:
            guardable = [p for p in self.alive_players if p.name != self.last_guarded]
            if not guardable:
                return None
            try:
                guard_result = await self._safe_agent_call(
                    guard_agent,
                    structured_model=get_guard_model_cn(guardable),
                    phase="guard"
                )
                guard_meta = safe_parse_metadata(guard_result)
                if guard_meta and guard_meta.get("target"):
                    result = {"target": guard_meta.get("target")}
                else:
                    fallback_target = random.choice(guardable)
                    result = {"target": fallback_target.name}
                    self._diag_log.warning(f"守护者LLM返回无效结果，随机选择: {fallback_target.name}")
            except Exception as e:
                fallback_target = random.choice(guardable)
                result = {"target": fallback_target.name}
                self._diag_log.warning(f"守护者Agent调用异常({e})，随机选择: {fallback_target.name}")

        if not result or not result.get("target"):
            return None

        target_name = result["target"]
        alive_names = self.alive_player_names
        if target_name not in alive_names:
            return None

        if target_name == self.last_guarded:
            # 重复保护违规：通知Agent并重试最多2次
            self._diag_log.warning(f"守护者选择了昨晚保护的目标{target_name}，开始重试")
            await guard_agent.observe(
                await self.moderator.announce(f"规则限制：不能连续两晚保护同一人（{target_name}昨晚已保护），请选择其他目标")
            )
            for retry in range(2):
                guardable = [p for p in self.alive_players if p.name != self.last_guarded]
                if not guardable:
                    return None
                try:
                    retry_result = await self._safe_agent_call(
                        guard_agent,
                        structured_model=get_guard_model_cn(guardable),
                        phase="guard"
                    )
                    retry_meta = safe_parse_metadata(retry_result)
                    if retry_meta and retry_meta.get("target"):
                        retry_target = retry_meta["target"]
                        if retry_target in self.alive_player_names and retry_target != self.last_guarded:
                            target_name = retry_target
                            break
                except Exception as e:
                    self._diag_log.warning(f"守护者重试异常({e})")
            else:
                # 重试都失败，随机选择合法目标
                guardable = [p for p in self.alive_players if p.name != self.last_guarded]
                if guardable:
                    fallback = random.choice(guardable)
                    target_name = fallback.name
                    self._diag_log.warning(f"守护者重试后仍无效，随机选择: {target_name}")
                else:
                    return None

        self.last_guarded = target_name
        await guard_agent.observe(
            await self.moderator.announce(f"你今晚保护了{target_name}的数据权限")
        )
        if self.logger:
            seat = self.get_seat_num(guard_agent)
            self.logger.log_decision(
                round_num=round_num,
                phase="guard",
                player=f"{seat}号",
                role="守护者",
                action="加密保护",
                target=target_name,
                reasoning_steps=None,
                key_evidence=None,
                full_output=None,
                seat=f"{seat}号",
            )
        return target_name

    async def witch_phase(self, killed_player: Optional[str], guarded_player: Optional[str],
                           was_guarded: bool = False):
        """女巫阶段（CEO拍板）

        Args:
            killed_player: 狼人击杀目标（原始值，未经保护结算）
            guarded_player: 安保主管保护目标
            was_guarded: 击杀目标是否被安保保护（同保同挽留规则）
        """
        if not self.witch:
            # 女巫死亡：安保保护独立生效，被保护者存活
            return (None if was_guarded else killed_player), None

        witch_agent = self.witch[0]

        # Skills阶段注入：女巫
        if self.skills_dispatcher:
            seat = self.get_seat_num(witch_agent)
            role = self.get_role_by_seat(seat)
            await self.skills_dispatcher.inject_phase_skills(
                witch_agent, "witch", self.round_num, role, seat)

        await self.moderator.announce("CEO请睁眼...")

        # 同保同挽留规则：女巫始终被告知击杀信息（即使被安保保护）
        death_info = f"今晚{killed_player}被间谍窃取了信息（即将离职）" if killed_player else "今晚平安无事"
        if was_guarded and killed_player:
            death_info += "（安保主管已加密保护此人，但同保同挽留规则下，仅靠保护或仅靠挽留均不够——需要两者都不作用才能存活）"
        await witch_agent.observe(await self.moderator.announce(death_info))

        skill = self.skill_registry.get_skill("女巫")
        seat = self.get_seat_num(witch_agent)
        game_state = self._build_game_state(seat, killed_player=killed_player, has_potion=self.witch_has_antidote, has_poison=self.witch_has_poison)
        if skill:
            result = await skill.execute(witch_agent, self.alive_players, game_state)
        else:
            witch_action = await self._safe_agent_call(
                witch_agent,
                structured_model=WitchActionModelCN,
                phase="witch"
            )
            witch_meta = safe_parse_metadata(witch_action)
            result = {
                "use_antidote": witch_meta.get("use_antidote", False) if witch_meta else False,
                "use_poison": witch_meta.get("use_poison", False) if witch_meta else False,
                "target_name": witch_meta.get("target_name") if witch_meta else None,
            } if witch_meta else None

        saved_player = None
        poisoned_player = None
        used_potion = False
        guard_save_cancelled = False  # 安保保护是否抵消了击杀

        if result:
            if result.get("use_antidote") and self.witch_has_antidote and not used_potion:
                if killed_player:
                    witch_name = witch_agent.name
                    is_first_night = (self.round_num == 1)
                    if killed_player == witch_name and is_first_night and not self.witch_can_self_save_first_night:
                        pass  # 首夜不能自救
                    elif was_guarded and killed_player == guarded_player:
                        # 同保同挽留规则：安保保护+女巫解药同时作用于同一目标 → 目标仍死亡
                        # 解药被消耗但无效，保护也无效
                        self.witch_has_antidote = False
                        used_potion = True
                        guard_save_cancelled = True  # 标记：保护被同保同挽留规则取消
                        await witch_agent.observe(
                            await self.moderator.announce(
                                f"你签发了留人offer，{killed_player}被挽留。"
                                f"但同保同挽留规则：安保保护与CEO挽留同时生效，{killed_player}仍然离职！"
                            )
                        )
                    else:
                        # 正常挽留：仅解药生效，目标存活
                        saved_player = killed_player
                        self.witch_has_antidote = False
                        used_potion = True
                        await witch_agent.observe(
                            await self.moderator.announce(f"你签发了留人offer，{killed_player}被挽留")
                        )

            if result.get("use_poison") and self.witch_has_poison and not used_potion:
                poisoned_player = result.get("target_name")
                if poisoned_player:
                    alive_names = self.alive_player_names
                    if poisoned_player not in alive_names:
                        poisoned_player = None
                    else:
                        self.witch_has_poison = False
                        used_potion = True
                        await witch_agent.observe(
                            await self.moderator.announce(f"你签发了辞退信，{poisoned_player}被开除")
                        )

        # 结算 final_killed：综合考虑保护、解药、同保同挽留
        if was_guarded and guard_save_cancelled:
            # 同保同挽留：保护+解药同时作用 → 目标仍死
            final_killed = killed_player
        elif was_guarded and not saved_player:
            # 仅保护，女巫未救 → 保护生效，目标存活
            final_killed = None
        elif saved_player:
            # 正常解药 → 目标存活
            final_killed = None
        else:
            # 无保护无解药 → 目标死亡
            final_killed = killed_player

        if self.logger and result:
            seat = self.get_seat_num(witch_agent)
            if saved_player:
                action = "CEO挽留"
                target = saved_player
            elif poisoned_player:
                action = "CEO辞退"
                target = poisoned_player
            else:
                action = "CEO观望"
                target = None
            self.logger.log_decision(
                round_num=self.round_num,
                phase="witch",
                player=f"{seat}号",
                role="女巫",
                action=action,
                target=target,
                reasoning_steps=None,
                key_evidence=None,
                full_output=None,
                seat=f"{seat}号",
            )

        return final_killed, poisoned_player

    async def hunter_phase(self, dead_player: str, is_poisoned: bool = False) -> Optional[str]:
        """猎人阶段（法务诉讼）- 被辞退信开除时无法发动技能"""
        if not self.hunter:
            return None

        hunter_agent = self.hunter[0]
        if hunter_agent.name != dead_player:
            return None

        seat = self.get_seat_num(hunter_agent)

        if is_poisoned:
            await self.moderator.announce(f"{hunter_agent.name}被辞退信开除，无法发起诉讼。")
            if self.logger:
                self.logger.log_decision(
                    round_num=self.round_num,
                    phase="hunter",
                    player=f"{seat}号",
                    role="猎人",
                    action="法务诉讼",
                    target=None,
                    reasoning_steps=None,
                    key_evidence="被辞退信开除，无法发起诉讼",
                    full_output=None,
                    seat=f"{seat}号",
                )
            return None

        # 通知全场：法务总监出局，可以发起诉讼
        hunter_public_msg = (
            f"{hunter_agent.name}是法务总监，出局时可以发起诉讼带走一名员工..."
        )
        await self.moderator.announce(hunter_public_msg)
        # 让所有存活玩家看到此公告
        public_msg = Msg(name="游戏主持人", content=hunter_public_msg, role="system")
        for agent in self.alive_players:
            if agent.name != dead_player:
                await agent.observe(public_msg)

        # 构建猎人专属提示，明确告知当前处境
        hunter_context_msg = (
            f"你（{hunter_agent.name}）是法务总监，刚刚被{'投票' if not is_poisoned else '辞退信'}出局。"
            f"根据你的技能，你现在可以选择发起诉讼带走一名存活的员工。"
            f"存活员工：{', '.join(p.name for p in self.alive_players if p.name != dead_player)}"
            f"\n请决定：是否发起诉讼（shoot=true），如果发起诉讼，选择目标（target）。"
        )
        await hunter_agent.observe(Msg(name="游戏主持人", content=hunter_context_msg, role="system"))

        # 使用 _safe_agent_call 确保有重试和日志记录
        hunter_action = await self._safe_agent_call(
            hunter_agent,
            structured_model=get_hunter_model_cn(
                [p for p in self.alive_players if p.name != dead_player]
            ),
            phase="hunter"
        )
        hunter_meta = safe_parse_metadata(hunter_action)

        result = None
        if hunter_meta and hunter_meta.get("shoot"):
            target = hunter_meta.get("target")
            if target:
                result = {"shoot": True, "target": target}

        if not result or not result.get("shoot"):
            await self.moderator.announce(f"{hunter_agent.name}选择不发起诉讼。")
            if self.logger:
                self.logger.log_decision(
                    round_num=self.round_num,
                    phase="hunter",
                    player=f"{seat}号",
                    role="猎人",
                    action="法务诉讼",
                    target=None,
                    reasoning_steps=None,
                    key_evidence=hunter_meta.get("shoot_reason") if hunter_meta else "选择不发起诉讼",
                    full_output=hunter_meta,
                    seat=f"{seat}号",
                )
            return None

        target = result.get("target")
        if not target:
            await self.moderator.announce(f"{hunter_agent.name}诉讼目标无效，诉讼失败。")
            return None
        alive_names = [p.name for p in self.alive_players if p.name != dead_player]
        if target not in alive_names:
            await self.moderator.announce(f"{hunter_agent.name}诉讼目标{target}不在存活列表中，诉讼失败。")
            return None

        await self.moderator.announce(f"{hunter_agent.name}发起诉讼，带走了{target}！")
        if self.logger:
            self.logger.log_decision(
                round_num=self.round_num,
                phase="hunter",
                player=f"{seat}号",
                role="猎人",
                action="法务诉讼",
                target=target,
                reasoning_steps=None,
                key_evidence=hunter_meta.get("shoot_reason") if hunter_meta else None,
                full_output=hunter_meta,
                seat=f"{seat}号",
            )
            self.logger.log_skill_resolution(
                self.round_num, "hunter_shoot", hunter_agent.name, target,
                f"法务诉讼带走{target}",
                source_seat=f"{seat}号",
            )
        return target

    def update_alive_players(self, dead_players: List[str]):
        """更新存活玩家列表"""
        for dead_name in dead_players:
            if dead_name:
                self.alive_players = [p for p in self.alive_players if p.name != dead_name]
                self.werewolves = [p for p in self.werewolves if p.name != dead_name]
                self.villagers = [p for p in self.villagers if p.name != dead_name]
                self.seer = [p for p in self.seer if p.name != dead_name]
                self.witch = [p for p in self.witch if p.name != dead_name]
                self.hunter = [p for p in self.hunter if p.name != dead_name]
                self.guard = [p for p in self.guard if p.name != dead_name]

    async def day_phase(self, round_num: int) -> Optional[str]:
        """白天阶段（例会讨论+归票发言+投票）"""
        # Skills阶段注入：所有存活玩家
        if self.skills_dispatcher:
            for agent in self.alive_players:
                seat = self.get_seat_num(agent)
                role = self.get_role_by_seat(seat)
                await self.skills_dispatcher.inject_phase_skills(
                    agent, "day_discussion", round_num, role, seat)

        await self.moderator.day_announcement(round_num)

        async with MsgHub(
            self.alive_players,
            enable_auto_broadcast=True,
            announcement=await self.moderator.announce(
                f"例会开始，请各位发言。存活员工：{format_player_list(self.alive_players)}"
            ),
        ) as all_hub:
            await self._logged_sequential_pipeline(self.alive_players, phase="day_discussion")

            await self.moderator.announce("归票发言开始，请各位明确投票方向和理由。")
            await self._logged_sequential_pipeline(self.alive_players, phase="day_vote_discussion")

            all_hub.set_auto_broadcast(False)
            vote_msgs = await self._logged_fanout_pipeline(
                self.alive_players,
                await self.moderator.announce("请投票选择要淘汰的员工"),
                structured_model=get_vote_model_cn(self.alive_players),
                phase="day_vote",
                enable_gather=False,
            )

            votes = {}
            for i, vote_msg in enumerate(vote_msgs):
                meta = safe_parse_metadata(vote_msg)
                if meta:
                    votes[self.alive_players[i].name] = meta.get("vote")
                else:
                    votes[self.alive_players[i].name] = None

            voted_out, vote_count = majority_vote_cn(votes)
            await self.moderator.vote_result_announcement(voted_out, vote_count)

            if self.logger:
                self.logger.log_vote_result(round_num, votes, voted_out, vote_count)
                for i, player in enumerate(self.alive_players):
                    meta = safe_parse_metadata(vote_msgs[i]) if i < len(vote_msgs) else None
                    seat = self.get_seat_num(player)
                    self.logger.log_decision(
                        round_num=round_num,
                        phase="vote",
                        player=f"{seat}号",
                        role=self.get_role_by_seat(seat),
                        action="投票",
                        target=votes.get(player.name),
                        reasoning_steps=None,
                        key_evidence=meta.get("reason") if meta else None,
                        full_output=meta if meta else None,
                        seat=player.name,
                    )

            self.context_manager.add_key_event(
                round_num, "vote_result",
                f"投票结果：{voted_out}以{vote_count}票被投出"
            )

            return voted_out

    def _extract_identity_claims_from_memory(self) -> Dict[str, List[str]]:
        """从玩家发言记录中提取身份声明
        
        检测关键词：
        - "我是HR总监/预言家"
        - "我是安保主管/守护者"
        - "我查杀"（暗示自己是预言家）
        - "我保护了"（暗示自己是守护者）
        """
        identity_keywords = {
            "预言家": ["我是HR总监", "我是预言家", "我查杀", "我背调了", "HR总监"],
            "守护者": ["我是安保主管", "我是守护者", "我保护了", "我加密了", "安保主管"],
            "女巫": ["我是CEO", "我是女巫", "我挽留了", "我签发了", "CEO"],
            "猎人": ["我是法务总监", "我是猎人", "法务总监"],
        }
        
        claims: Dict[str, List[str]] = {}
        
        for player in self.alive_players:
            claimed_roles: List[str] = []
            if hasattr(player, 'memory') and player.memory:
                memory_content = getattr(player.memory, 'content', [])
                if memory_content:
                    for msg in memory_content:
                        msg_content = None
                        if hasattr(msg, 'content'):
                            msg_content = msg.content
                        elif isinstance(msg, str):
                            msg_content = msg
                        elif hasattr(msg, 'text'):
                            msg_content = msg.text
                        
                        if msg_content and isinstance(msg_content, str):
                            for role, keywords in identity_keywords.items():
                                for kw in keywords:
                                    if kw in msg_content:
                                        if role not in claimed_roles:
                                            claimed_roles.append(role)
                                        break
            if claimed_roles:
                claims[player.name] = claimed_roles
        
        return claims

    async def run_game(self, player_count: int = 12):
        """运行游戏主循环"""
        try:
            await self.setup_game(player_count)
            round_num = 0

            for round_num in range(1, MAX_GAME_ROUND + 1):
                self.round_num = round_num
                self._game_log.info(f"\n=== 第{round_num}轮夜晚 ===")
                if self.logger:
                    self.logger.log_night_start(round_num)
                await self.moderator.night_announcement(round_num)

                # 间谍窃取
                killed_player = await self.werewolf_phase(round_num)

                # HR背调 + 安保主管加密保护 并行执行（两者互不依赖）
                seer_task = asyncio.create_task(self.seer_phase())
                guard_task = asyncio.create_task(self.guard_phase(round_num))
                await asyncio.gather(seer_task, guard_task)
                guarded_player = guard_task.result()

                # 安保主管保护结算（同保同挽留规则：对冲互消）
                # 女巫仍被告知击杀信息，可以使用解药；
                # 但若安保保护与女巫解药同时作用于同一目标，目标仍然死亡。
                was_guarded = (killed_player and killed_player == guarded_player)

                # 女巫行动（需要知道窃取和守护情况来判断）
                final_killed, poisoned_player = await self.witch_phase(killed_player, guarded_player, was_guarded)

                # 结算夜晚死亡
                night_deaths = [p for p in [final_killed, poisoned_player] if p]
                self.update_alive_players(night_deaths)
                await self.moderator.death_announcement(night_deaths)

                for dead in night_deaths:
                    self.context_manager.add_key_event(round_num, "death", f"{dead}夜间离职")

                if self.logger:
                    for dead in night_deaths:
                        cause = "间谍窃取" if dead == final_killed else "CEO辞退"
                        self.logger.log_death(round_num, dead, cause, seat=dead)
                    self.logger.log_skill_resolution(
                        round_num, "spy_steal", "间谍团队", killed_player,
                        f"窃取目标{killed_player}" + ("，被加密保护抵消" if was_guarded and final_killed is None else "，同保同挽留规则下仍离职" if was_guarded and final_killed else ""),
                        source_seat="间谍团队",
                    )
                    if guarded_player:
                        guard_result_text = "加密保护成功" if final_killed is None else "加密保护被同保同挽留规则抵消"
                        self.logger.log_skill_resolution(
                            round_num, "guard_protect", self.guard[0].name if self.guard else "安保主管", guarded_player, guard_result_text,
                            source_seat=self.guard[0].name if self.guard else None)
                    self.logger.log_state_snapshot(
                        round_num, "night_end",
                        [p.name for p in self.alive_players],
                        [self.seat_characters.get(p.name, p.name) for p in self.alive_players],
                        self.witch_has_antidote, self.witch_has_poison, self.last_guarded,
                    )

                # 夜晚离职的法务总监判断
                # 被辞退信开除不能发起诉讼，被间谍窃取信息可以发起诉讼
                # 同保同挽留下的死亡视为"间谍窃取"（保护无效→等于被窃取）
                hunter_shot = None
                if final_killed:
                    hunter_shot = await self.hunter_phase(final_killed, is_poisoned=False)
                if not hunter_shot and poisoned_player:
                    await self.hunter_phase(poisoned_player, is_poisoned=True)

                if hunter_shot:
                    self.update_alive_players([hunter_shot])

                # 检查胜利
                winner = check_winning_cn(self.alive_players, self.roles)
                if winner:
                    await self._handle_game_over(winner, round_num)
                    return

                # 白天阶段
                if self.logger:
                    self.logger.log_day_start(round_num)
                voted_out = await self.day_phase(round_num)

                # 法务总监技能（白天投票出局可以发起诉讼）
                hunter_shot = await self.hunter_phase(voted_out, is_poisoned=False)

                # 结算白天死亡
                day_deaths = [p for p in [voted_out, hunter_shot] if p]
                self.update_alive_players(day_deaths)

                # 日志记录白天死亡事件
                if self.logger:
                    if voted_out:
                        self.logger.log_death(round_num, voted_out, "投票淘汰", seat=voted_out)
                    if hunter_shot:
                        self.logger.log_death(round_num, hunter_shot, "法务诉讼", seat=hunter_shot)

                # 上下文管理：记录白天死亡事件
                if voted_out:
                    self.context_manager.add_key_event(round_num, "death", f"{voted_out}被投票淘汰离职")
                if hunter_shot:
                    self.context_manager.add_key_event(round_num, "death", f"{hunter_shot}被法务诉讼带走离职")

                # 检查胜利
                winner = check_winning_cn(self.alive_players, self.roles)
                if winner:
                    await self._handle_game_over(winner, round_num)
                    return

                self._game_log.info(f"第{round_num}轮结束，存活员工：{format_player_list(self.alive_players)}")

                # 上下文管理：每轮结束自动截断超出窗口的Agent记忆
                truncated = self.context_manager.truncate_all_agents(self.alive_players)
                if truncated:
                    self._context_log.info(f"{truncated}个Agent记忆已截断")

        except Exception as e:
            if isinstance(e, GameError):
                self._diag_log.error(f"游戏逻辑错误：{e}")
            else:
                self._diag_log.exception("游戏运行出错")
            if self.logger:
                self.logger.log_error(str(e), phase="run_game")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行职场狼人杀多智能体对局")
    parser.add_argument(
        "--players",
        type=int,
        choices=(6, 9, 12),
        help="非交互选择人数：6、9 或 12。不传则进入交互选择。",
    )
    parser.add_argument(
        "--log",
        type=str,
        help="叙事日志文件路径（.txt），自动生成同名 .log 和 .jsonl 伴生文件。",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="诊断日志级别（DEBUG/INFO/WARNING/ERROR），默认INFO。",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="诊断日志使用详细格式（含源码位置）。",
    )
    parser.add_argument(
        "--prompt-version",
        type=str,
        default="v2",
        help="Prompt版本（v1/v2/v3），默认v2。",
    )
    parser.add_argument(
        "--context-window",
        type=int,
        default=80,
        help="上下文窗口大小（每个Agent保留的最近消息条数，默认80），防止长对局context溢出。",
    )
    parser.add_argument(
        "--witch-can-self-save",
        type=bool,
        default=True,
        help="CEO首夜是否可以自救（默认True，网杀规则允许）。",
    )
    parser.add_argument(
        "--agent-version",
        type=str,
        default="baseline",
        help="评测报告中标记的agent版本号（如v1/v2/v3），默认baseline。",
    )
    parser.add_argument(
        "--skills-version",
        type=str,
        default=None,
        help="Skills版本号（如evo_1），启用Skills注入。不传则不注入。",
    )
    parser.add_argument(
        "--skills-targets",
        type=str,
        default="all",
        help='Skills注入目标：all | faction:间谍 | faction:公司 | seat:1,3,5 | role:预言家 | character:逻辑怪，支持+组合。',
    )
    parser.add_argument(
        "--human-seat",
        type=int,
        default=None,
        help="真人玩家座位号（1~N），启用人机混合对局。不传则全部为AI。",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    from dotenv import load_dotenv
    load_dotenv()

    # 初始化日志系统（尽早配置，后续代码可立即使用logging）
    player_count = args.players or 12
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = args.log or f"exports/game_{player_count}p_{timestamp}"
    txt_path = base if base.endswith(".txt") else base + ".txt"
    log_path = txt_path.replace(".txt", ".log")
    jsonl_path = txt_path.replace(".txt", ".jsonl")
    setup_logging(
        narration_path=txt_path,
        diagnostic_path=log_path,
        level=args.log_level,
        verbose=args.verbose,
    )

    # 启用OpenTelemetry链路追踪（LLM调用耗时/token/异常自动记录）
    trace_path = txt_path.replace(".txt", ".trace.jsonl")
    setup_tracing(trace_path=trace_path)
    _model_log = get_logger("model", layer="diag")
    _game_log = get_logger("main", layer="game")

    if "DASHSCOPE_API_KEY" not in os.environ:
        _model_log.error("请设置环境变量 DASHSCOPE_API_KEY")
        return

    # 验证模型配置
    warnings = validate_model_configs()
    for w in warnings:
        _model_log.warning(w)

    # 模型配置摘要
    _model_log.info("模型配置：")
    _model_log.info(get_config_summary())

    _game_log.info("欢迎来到职场狼人杀！")
    _game_log.info("可选局数：6人局 / 9人局 / 12人局")

    if args.players:
        _game_log.info(f"已选择{player_count}人局。")
    else:
        user_input = input("请选择人数（6/9/12，默认12）：").strip()
        if user_input in ("6", "9", "12"):
            player_count = int(user_input)

    from prompt_logger import CombinedLogger

    logger = CombinedLogger(jsonl_path)

    # 解析真人玩家座位号
    human_seats = set()
    if args.human_seat is not None:
        if 1 <= args.human_seat <= player_count:
            human_seats = {args.human_seat}
            _game_log.info(f"🧑 人类玩家：{args.human_seat}号")
        else:
            _game_log.warning(f"--human-seat {args.human_seat} 超出范围（1~{player_count}），忽略")

    game = OfficeWerewolfGame(
        logger=logger,
        prompt_version=args.prompt_version,
        witch_can_self_save_first_night=args.witch_can_self_save,
        context_window=args.context_window,
        skills_version=args.skills_version,
        skills_targets=args.skills_targets,
        human_seats=human_seats,
    )
    try:
        await game.run_game(player_count)
    finally:
        logger.close()


if __name__ == "__main__":
    # Fix Windows GBK console encoding for emoji/unicode output
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    asyncio.run(main())




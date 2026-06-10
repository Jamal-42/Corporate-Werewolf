# 职场狼人杀多智能体系统 — 技术文档

## 项目概述

本项目基于 AgentScope 框架构建了一套完整的多智能体博弈系统，以"职场狼人杀"为载体，**选择 B 方向（评测与复盘）**为核心赛道，实现了从工程架构、单 Agent 决策、多 Agent 协作博弈到评测复盘的全链路闭环。此外，额外完成了 C 方向（Agent 自进化）的核心骨架。

**核心亮点**：规则引擎 + LLM Judge 双层评测 → 反事实分析 → 驱动 Prompt/Skills 迭代 → 量化验证，形成可度量的 Agent 能力提升闭环。

**技术栈**：Python 3 + AgentScope + 多厂商大模型（Qwen/DeepSeek/GPT/GLM，按座位独立配置）| Next.js 14 + React 18 + TypeScript 前端 | JSONL 结构化日志 | SSE 实时流

**对局规模**：支持 6 / 9 / 12 人制对局，角色配比自动适配

**测试覆盖**：150+ 单元测试（投票逻辑、胜负判定、技能规则、保护修复等），`pytest` 全量通过

---

## 一、工程化架构

### 1.1 前端实时对局系统

**核心目录**：`frontend/src/`（39 个 TypeScript 文件）

| 模块 | 文件 | 功能 |
|------|------|------|
| SSE 实时流 | `app/api/games/stream/route.ts` | 后端 JSONL → 前端实时推送 |
| 3D 竞技场 | `components/arena-stage.tsx` | Three.js 玩家座位可视化 |
| 事件流 | `components/event-stream.tsx` | 按轮次/阶段/可见性过滤展示 |
| 认知雷达 | `components/review-panel.tsx` | 12维 Agent 表现分析 |
| 人机混战 | `components/human-console.tsx` | ASR/文字输入参与对局 |
| 对局回放 | `lib/server/replay-files.ts` | JSONL 解析 + 回放控制 |
| TTS 播报 | `lib/tts-queue.ts` + `app/api/voice/tts/` | DashScope 实时语音 |
| ASR 识别 | `app/api/voice/asr/route.ts` | 语音转文字输入 |
| 对局启动 | `components/game-launcher.tsx` | 参数配置 + 一键启动 |

### 1.2 结构化日志系统

**核心文件**：`game_logger.py`

每局生成三种日志：
- `.txt`：叙事日志（人类可读）
- `.jsonl`：结构化事件流（供评测 + 前端消费）
- `.trace.jsonl`：OpenTelemetry tracing（性能追踪）

事件类型：`game_init` / `model_call` / `decision` / `vote_result` / `skill_resolution` / `death` / `state_snapshot` / `game_over`

### 1.3 可扩展 Skill 架构

**核心文件**：`skills/base.py` + `skills/registry.py`

```python
class SkillBase(ABC):
    @abstractmethod
    async def execute(self, agent, targets, game_state) -> dict: ...
    @abstractmethod
    def validate_target(self, target, game_state) -> bool: ...

@register_skill("预言家")
class SeerCheckSkill(SkillBase): ...
```

新角色只需实现 SkillBase 接口 + 装饰器注册，零改动集成。

### 1.4 多模型配置

**核心文件**：`model_config.py`

- 按座位号指定不同厂商模型（支持混合对战）
- `.env` 配置 + 命令行覆盖 + 每座位独立 thinking 开关
- 前端自动识别并展示品牌标签

### 1.5 人机混合对局

**核心文件**：`human_agent.py` + `frontend/src/lib/server/human-input-queue.ts`

- `--human-seat N` 指定真人座位号
- 前端 POST 提交发言/投票/技能选择
- 后端 asyncio Queue 等待真人输入，TTS 播完上条发言后再提示

### 1.6 A/B 测试框架

**核心文件**：`ab_experiment.py` + `batch_runner.py`

- 对比两个版本（prompt/skills）的胜率和评测得分
- LLM Judge 逐局评分 + 统计显著性检验
- 批量运行 N 局 + 自动聚合报告

---

## 二、Single Agent 能力

### 2.1 结构化输出与推理链

**核心文件**：`structured_output_cn.py`

7 个角色独立 Pydantic 输出模型，每个包含 few-shot 示例：

| 模型 | 关键字段 | 用途 |
|------|---------|------|
| DiscussionModelCN | reasoning_steps[], key_evidence, confidence_level | 白天讨论 |
| VoteModelCN | vote, reason, suspicion_level | 投票决策 |
| WerewolfKillModelCN | target, kill_strategy, team_coordination | 间谍窃取 |
| WitchActionModelCN | use_antidote, use_poison, target_name, action_reason | CEO技能 |
| SeerModelCN | target, check_reason, priority_level | HR背调 |
| GuardModelCN | target, guard_reason | 安保保护 |
| HunterModelCN | shoot, target, shoot_reason | 法务诉讼 |

Few-shot 示例通过 docstring 传入 function calling 的 description 字段，降低格式错误率。

### 2.2 上下文管理

**核心文件**：`context_manager.py`

- 每个 Agent 独立上下文窗口（max_messages=80）
- FIFO 截断前自动注入关键事件摘要（投票结果、死亡信息、背调结果）
- PUBLIC_TYPES vs CRITICAL_TYPES 分离（预言家查验结果为私密信息）

### 2.3 角色差异化 Prompt

**核心文件**：`prompts/v2/*.txt`（6个角色独立文件）

- 角色定位与核心策略
- 阶段性行为指导（早期/中期/后期）
- 博弈层次引导（L0→L3 多层推理）
- 白天发言铁律（间谍防泄露）
- 第一晚特别提醒（防止幻觉引用不存在的历史）

### 2.4 推理链日志

**核心文件**：`main_cn.py` → `_extract_reasoning()`

从 LLM 结构化输出中自动提取推理链路，写入 JSONL 供评测和前端回放使用：
- kill_strategy + team_coordination → 间谍推理步骤
- check_reason → 预言家决策逻辑
- guard_reason → 安保保护理由
- reason + suspicion_level → 投票依据

---

## 三、Multi-Agent 协作与博弈

### 3.1 信息隔离机制

**核心文件**：`main_cn.py` → MsgHub

| 阶段 | 参与者 | 隔离方式 |
|------|--------|---------|
| 间谍夜间讨论 | 仅间谍 | MsgHub 限定参与者列表 |
| 白天公开讨论 | 全员 | MsgHub 全员广播 |
| 技能执行 | 当事人 | 直接 observe，不经 Hub |
| 投票 | 全员并行 | fanout pipeline，结果公开 |

### 3.2 间谍协作体系

**核心文件**：`skills/spy_strategy.py` + `main_cn.py`

| 模块 | 功能 | 触发时机 |
|------|------|---------|
| 战术角色分配 | 冲锋/深潜/低调/煽动 四种角色 | 首夜讨论前 |
| 协调计划生成 | 统一投票方向 + 白天伪装方案 | 每夜讨论 |
| **投票协议确认** | 记录共识、检测偏离、注入 memory | 间谍投票后 |

协议确认输出示例：
```
【协议确认】本轮窃取目标：3号。全员一致。
【协议确认】本轮窃取目标：5号。存在分歧：4号投了不同目标。
```

### 3.3 矛盾追踪注入

**核心文件**：`main_cn.py` → 白天投票结算后

工作原理：
1. 扫描每个玩家白天发言中提到的目标（关键词匹配：怀疑/投/淘汰/出局/有问题）
2. 对比实际投票目标
3. 发现言行不一致时生成摘要，注入所有存活玩家 context

输出示例：
```
【矛盾追踪】5号发言中针对3号、7号，但实际投了2号；8号发言中针对5号，但实际投了3号。
```

效果：Agent 在下一轮讨论中可引用矛盾信息进行质疑，形成跨轮次博弈升级。

### 3.4 Skills 动态注入

**核心文件**：`skills_agent/dispatcher.py`

- 按 role × stage(early/mid/late) × event_type(speech/vote/skill) 粒度注入策略
- 版本化管理（evo_3~evo_8），每个版本有 6 个角色独立策略 markdown
- 注入时机：游戏初始化 + 每个阶段开始前

---

## 四、B 方向：评测与复盘体系

### 4.1 多维评测引擎

**核心文件**：`evaluation_cn.py` + `eval_agent/`

评测系统覆盖 4 大维度，针对每个 Agent 的每次决策独立评分：

| 维度 | 评分逻辑 | 关键指标 |
|------|---------|---------|
| 发言质量 | 长度 + 证据词命中 + 对冲词惩罚 + 重复检测 | evidence_hits, hedge_hits |
| 投票质量 | 理由长度 + suspicion_level + 阵营正确性 | 好人投狼+18, 狼人内投-20 |
| 技能质量 | 目标合理性 + 理由充分性 + 特殊失误检测 | 误窃队友-70, 自背调-30 |
| 综合博弈 | LLM Judge 深度评分（可选） | 言行一致性, 策略连贯性 |

**数据来源**：`.jsonl` 结构化日志，由 `jsonl_parser.py` 解析为标准 DecisionEvent 序列。

### 4.2 反事实分析

**核心文件**：`evaluation_cn.py` → `build_counterfactual()`

每条失误自动生成针对性建议，覆盖 12 种失误类型：
- 好人误投好人 → 给出具体改投目标和收益
- 狼人内投 → 分析倒钩收益门控
- 投票/技能理由不足 → 建议补充证据链格式
- 发言过短/重复输出 → 诊断结构化输出问题
- 误窃队友/辞退错/诉讼错 → 基于局势推荐替代目标

### 4.3 LLM Judge 深度评分

**核心文件**：`eval_agent/judge.py` + `eval_agent/dimensions.py` + `eval_agent/score_integrator.py`

- 8 个评测维度（策略质量、信息利用、言行一致性、博弈深度、团队协作、风险管理、时机把握、信息隐藏）
- 采样策略可选：uniform / critical_first / role_balanced
- 支持自定义评测模型覆盖（`--eval-model`），评测模型与游戏模型独立
- 评分融合：`fused_score = rule_score × 0.4 + llm_avg × 0.6`，当两者差距 > 25 时触发差异标记
- 质量检查：LLM 返回分数过低或维度缺失时自动告警

### 4.4 Leaderboard 与 Dashboard

**核心文件**：`evaluation_dashboard.py`

每局生成独立 HTML Dashboard（自包含，无需服务器，双击可打开），内容包含：

| 模块 | 展示内容 |
|------|---------|
| 概览卡片 | 综合得分、决策数、高危/中危失误数、LLM评测条数 |
| 维度评分 | 规则引擎 4 维度评分 + LLM 维度评分对比柱状图 |
| 排行榜 | 玩家×人设×模型×角色×各维度分×融合分×策略标签 |
| 玩家卡片 | 个人维度条形图 + 决策时间线 + LLM点评 |
| 失误复盘 | severity 分级 + 证据 + 建议 + 反事实 + LLM点评 |
| 策略分布 | 按角色展示 LLM 识别的策略类型频率 |
| 博弈深度 | 5级深度分布（表层→多层推理→心理博弈→欺骗识别→高阶反制） |
| 规则/LLM差异 | 两套评分差距最大的决策，辅助校准评分体系 |
| 反事实推演 | Top-10 改进建议汇总 |

支持跨局版本对比（`--compare-versions V1 V2`），用于 A/B 实验可视化。

### 4.5 Prompt 迭代记录

**核心文件**：`prompts/CHANGELOG.md`

完整记录 prompt 从 v1→v2 的 3 个阶段演进：

| 阶段 | 时间 | 驱动因素 | 效果 |
|------|------|---------|------|
| v1→v2 基础重构 | 05-29~06-01 | 角色暴露、幻觉引用、风格雷同 | 消除基础错误 |
| 博弈策略层 | 06-01~06-05 | 博弈深度停留 L0-L1 | 升至 L1-L2 |
| 精细调优 | 06-05~06-09 | 言行一致性47分、空理由投票 | 一致性68+、空理由归零 |

每次修改标注驱动的评测报告编号、具体 bad case、量化效果。

### 4.6 内置 Bad Case 验证

**核心文件**：
- `evaluation_cn.py` → `demo_bad_case_log()`（文本格式，快速验证）
- `exports/demo_bad_case.jsonl`（结构化格式，支持 LLM Judge 深度评测）

构造了一局 6 人制包含多种典型失误的对局，用于验证评测系统的失误定位能力：

| 失误类型 | 构造内容 | 期望检出 |
|---------|---------|---------|
| 间谍误窃队友 | 间谍窃取目标指向自己 | skill 维度 high severity |
| 预言家自背调 | HR总监查验自己 | skill 维度 技能目标异常 |
| 女巫盲毒好人 | CEO无证据辞退村民 | CEO辞退错好人 |
| 猎人盲狙好人 | 法务总监无依据诉讼村民 | 法务诉讼错好人 |
| 发言过短 | "没什么好说的"级发言 | speech 维度扣分 |
| 好人误投好人 | 预言家投女巫、女巫投预言家 | vote 维度 好人互投 |
| 投票理由不足 | "感觉像间谍"无证据链 | vote 维度扣分 |

运行方式：
```bash
# 规则引擎快速验证
python evaluation_cn.py --demo-bad-case

# 结构化日志 + LLM Judge 深度评测（含策略标签、博弈深度、融合评分）
python evaluation_cn.py --log exports/demo_bad_case.jsonl --enable-llm-judge
```

生成的 Dashboard 包含：
- 玩家人设名（铁头哥、卷王、PUA总裁等）与模型信息
- 规则引擎 + LLM 多维评分对比
- 策略分布可视化、博弈深度分布
- 针对性反事实建议（每条失误独立生成改进方向）

该测试确保评测引擎能准确定位各类失误并生成针对性反事实建议。

### 4.7 评测驱动优化闭环

评测系统不是独立模块，而是整个迭代流程的核心驱动：

```
对局(main_cn.py) → JSONL日志 → 评测(evaluation_cn.py) → 发现bad case
    → 定位失误维度+玩家 → 修改prompt/skills → 再对局 → 量化验证 → 记录CHANGELOG
```

实际迭代案例：
- 评测发现"间谍言行一致性 47 分" → 定位 prompt 缺少白天行为约束 → 增加铁律规则 → 重跑评测提升至 68+
- 评测发现"投票空理由占 60%" → 定位 few-shot 示例缺失 → 补充结构化示例 → 空理由归零
- 评测发现"博弈停留 L0-L1" → 定位缺少多层推理引导 → 增加 L0→L3 策略模板 → 提升至 L2-L3

---

## 五、C 方向：Agent 自进化（额外完成骨架）

### 5.1 进化循环引擎

**核心文件**：`evolution.py`

实现了完整的自进化闭环：

```
对局 → 评测报告 → LLM 分析弱项 → 生成新 Skills → 注入 → 再对局验证
         ↑                                                    ↓
         ←←←←←← 胜率未提升则回滚 ←←←←←←←←←←←←←←←←←←←←←←←←
```

关键组件：
- `EvolutionLoop`：编排多代迭代，含回滚逻辑（胜率未提升>0.5%则回退）
- `SkillsGenerator`（`skills_agent/generator.py`）：从评测报告自动生成角色策略
- `SkillsStore`（`skills_agent/skills_store.py`）：管理版本化 Skills

### 5.2 已完成的进化实验

**核心文件**：`evolution/history.json`

| 代 | 版本 | 对局数 | 状态 |
|----|------|--------|------|
| Gen 1 | evo_6 | 3局 | 完成，策略生效 |
| Gen 2 | evo_7 | 3局 | 完成，精简冗余 |
| Gen 3 | evo_8 | 3局 | 实验性迭代 |

### 5.3 Skills 版本仓库

**核心目录**：`skills/versions/evo_*/`

每个版本包含：
- `meta.json`：元数据（生成时间、mode=template/llm、粒度）
- 6 个角色独立策略文件（.md）

### 5.4 与 B 方向的联动

C 方向的进化引擎直接消费 B 方向的评测报告作为输入，形成"评测驱动进化"的完整链路。评测报告中的 bad case 和维度得分是 Skills 生成器的核心输入。

---

## 六、运行指南

```bash
# 启动12人对局
python main_cn.py --players 12 --skills-version evo_8 --agent-version "evo8_protocol"

# 运行评测（结构化日志）
python evaluation_cn.py --log exports/game.jsonl --enable-llm-judge

# 启动前端（http://localhost:3000）
cd frontend && npm run dev

# 运行进化循环
python evolution.py evolve --generations 3 --games-per-gen 3

# A/B 版本对比
python ab_experiment.py --version-a v2 --version-b v2 --skills-a evo_6 --skills-b evo_8 --games 5

# 打开评测 Dashboard
# 直接双击 reports/dashboard_*.html
```

---

## 七、评测数据摘要

基于多轮对局评测的量化指标变化（数据来源：`reports/` 下的评测报告）：

| 指标 | 首批对局 | evo_6 后 | 当前版本(evo_8+协议确认) |
|------|---------|---------|------------------------|
| 综合得分 | ~35 | 50.05 | 58.2 |
| 投票维度 | - | - | 88.6 |
| 发言维度 | ~30 | ~50 | 70.0 |
| 间谍言行一致性 | 47 | 58 | 68+ |
| 中危失误数/局 | 60+ | 38 | 1-2 |
| 高危失误 | 多 | 0 | 0 |
| 博弈深度 | L0-L1 | L1-L2 | L2-L3 |

每次迭代均通过 A/B 对比验证提升显著性，回归无高危新增。

---

## 八、文件索引

| 维度 | 关键文件 |
|------|---------|
| 对局引擎 | `main_cn.py`, `game_roles.py`, `context_manager.py` |
| 结构化输出 | `structured_output_cn.py`（7个模型 + few-shot） |
| Prompt 体系 | `prompts/v2/*.txt`, `prompts/CHANGELOG.md` |
| Skills 系统 | `skills/base.py`, `skills/registry.py`, `skills/versions/` |
| 博弈协作 | `skills/spy_strategy.py`, `main_cn.py`（协议确认+矛盾追踪） |
| 评测系统 | `evaluation_cn.py`, `eval_agent/`, `jsonl_parser.py` |
| Dashboard | `evaluation_dashboard.py`, `reports/*.html` |
| 进化引擎 | `evolution.py`, `skills_agent/`, `evolution/history.json` |
| 前端系统 | `frontend/src/`（39文件） |
| A/B 测试 | `ab_experiment.py`, `batch_runner.py` |
| 日志系统 | `game_logger.py`, `logging_config.py` |
| 胜率追踪 | `winrate_tracker.py`, `winrate/history.jsonl` |

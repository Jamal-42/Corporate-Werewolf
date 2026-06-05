# 职场狼人杀 — 完整使用手册

> 从游戏对局 → 评测诊断 → Skills进化 → 再对局，一整条自进化管线

---

## 目录

1. [项目概览](#1-项目概览)
2. [环境配置](#2-环境配置)
3. [Step 1：运行游戏对局](#3-step-1运行游戏对局)
4. [Step 2：评测诊断](#4-step-2评测诊断)
5. [Step 3：Skills进化生成](#5-step-3skills进化生成)
6. [Step 4：Skills注入对局](#6-step-4skills注入对局)
7. [Step 5：自进化循环](#7-step-5自进化循环)
8. [可视化与复盘](#8-可视化与复盘)
9. [项目结构](#9-项目结构)
10. [配置参考](#10-配置参考)
11. [常见问题](#11-常见问题)
12. [Skills版本对比与A/B实验](#12-skills版本对比与ab实验)

---

## 1. 项目概览

职场狼人杀是一个多Agent狼人杀系统，每个玩家是独立的LLM Agent，由Python规则引擎做主持人。核心特色是**评测→进化→再对局**的闭环：

```
┌──────────────────────────────────────────────────────────────────┐
│                        自进化管线                                 │
│                                                                   │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐   │
│  │ 游戏对局 │───→│ 评测诊断 │───→│ Skills生成│───→│ Skills注入│   │
│  │ main_cn  │    │ evalu_cn │    │ evolution │    │ main_cn  │   │
│  └─────────┘    └──────────┘    └──────────┘    └─────────┘   │
│       ↑                                               │          │
│       └───────────────────────────────────────────────┘          │
│                         闭环迭代                                  │
└──────────────────────────────────────────────────────────────────┘
```

**三大Agent系统**：

| 系统 | 入口 | 职责 |
|------|------|------|
| 狼人杀Agent | `main_cn.py` | 多Agent对局，每个玩家是独立LLM Agent |
| 评测Agent | `evaluation_cn.py` + `eval_agent/` | 规则引擎评分 + LLM深度评测，生成评测报告 |
| Skills-Agent | `evolution.py` + `skills_agent/` | 从评测报告生成策略指导Skills，注入Agent实现进化 |

**角色对照表**（传统名 ↔ 职场名）：

| 传统名 | 职场名 | 能力 |
|--------|--------|------|
| 狼人 | 间谍 | 夜间窃取（杀人） |
| 预言家 | HR总监 | 背调（查验身份） |
| 女巫 | CEO | 留人offer（解药）+ 辞退信（毒药） |
| 猎人 | 法务总监 | 出局时发起诉讼（开枪） |
| 守护者 | 安保主管 | 加密保护（守人） |
| 村民 | 普通员工 | 无特殊能力 |

**支持局数**：6人 / 9人 / 12人

---

## 2. 环境配置

### 2.1 安装依赖

```bash
pip install agentscope==1.0.2 "pydantic>=2.0,<3.0" "dashscope>=1.20.0,<2.0.0" python-dotenv
```

### 2.2 配置API Key

```bash
cp .env.example .env
```

编辑 `.env`，至少填入：

```bash
# 游戏Agent + 评测Agent + Skills-Agent 共用的百炼API Key
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

### 2.3 验证环境

```bash
python test_env.py
```

### 2.4 模型配置

项目有**两套独立的模型配置**：

**游戏Agent**（前缀 `MODEL_*`）：

```bash
# 默认配置（所有座位）
MODEL_DEFAULT_MODEL_NAME=qwen-max          # 模型名
MODEL_DEFAULT_ENABLE_THINKING=true          # 思维链
MODEL_DEFAULT_BASE_URL=                     # 设了→OpenAI兼容，未设→百炼

# 按座位覆盖
MODEL_SEAT_1_MODEL_NAME=gpt-4o
MODEL_SEAT_1_BASE_URL=https://api.openai.com/v1
MODEL_SEAT_1_API_KEY=sk-xxx
```

**评测Agent / Skills-Agent LLM精炼**（前缀 `EVAL_MODEL_*`）：

```bash
EVAL_MODEL_MODEL_NAME=deepseek-v4-pro      # 评测模型名
EVAL_MODEL_API_KEY=sk-xxx                   # 未设则回退到 DASHSCOPE_API_KEY
EVAL_MODEL_BASE_URL=                        # 设了→OpenAI兼容，未设→百炼
EVAL_MODEL_ENABLE_THINKING=false            # 评测不需要思维链
EVAL_MODEL_GENERATE_KWARGS={"temperature":0.3}
EVAL_MODEL_MAX_CONCURRENT=3                 # 最大并发LLM调用数
```

优先级：`EVAL_MODEL_API_KEY` → `DASHSCOPE_API_KEY`

---

## 3. Step 1：运行游戏对局

### 3.1 基本用法

```bash
# 交互式选择局数
python main_cn.py

# 直接指定局数
python main_cn.py --players 6
python main_cn.py --players 9
python main_cn.py --players 12
```

### 3.2 高级选项

```bash
# 指定prompt版本和日志路径
python main_cn.py --players 12 --prompt-version v2 --log exports/my_game

# 自定义上下文窗口和CEO自救规则
python main_cn.py --players 12 --context-window 100 --witch-can-self-save true
```

### 3.3 输出文件

每局游戏生成三个文件（位于 `exports/` 目录）：

| 文件 | 格式 | 用途 |
|------|------|------|
| `053101.txt` | 人类可读叙述 | 快速阅读游戏过程 |
| `053101.log` | 诊断日志 | 带时间戳/级别的技术日志 |
| `053101.jsonl` | 结构化事件 | **评测和复盘的主要数据源** |

### 3.4 游戏流程

每轮分为夜晚和白天两个阶段：

```
夜晚：间谍讨论 → 间谍窃取 → HR总监背调 → 安保主管保护 → CEO行动 → 结算死亡 + 法务诉讼触发 → 胜负判定
白天：讨论（顺序发言）→ 投票（同时投票）→ 法务诉讼触发 → 结算死亡 → 胜负判定
```

---

## 4. Step 2：评测诊断

### 4.1 规则引擎评测（不需要API Key）

```bash
# 评测 .jsonl 日志（推荐）
python evaluation_cn.py --log exports/053101.jsonl

# 评测 .txt 日志（仅规则引擎评分，不支持LLM评测）
python evaluation_cn.py --log exports/053101.txt

# 内置 bad case 验证
python evaluation_cn.py --demo-bad-case
```

### 4.2 LLM深度评测（需要API Key）

```bash
# 全量LLM评测（~50-60次LLM调用）
python evaluation_cn.py --log exports/053101.jsonl --enable-llm-judge

# 采样评测（平衡成本与质量，~15-20次调用）
python evaluation_cn.py --log exports/053101.jsonl --enable-llm-judge --llm-sample-rate 0.3

# 优先采样关键事件（技能+投票，比发言更有决策含量）
python evaluation_cn.py --log exports/053101.jsonl --enable-llm-judge \
  --llm-sample-rate 0.3 --eval-sample-strategy critical_first

# 指定评测模型
python evaluation_cn.py --log exports/053101.jsonl --enable-llm-judge --eval-model qwen-max
```

**LLM采样策略**：

| 策略 | 说明 |
|------|------|
| `uniform` | 均匀随机采样（默认） |
| `critical_first` | 优先采样技能事件和投票事件 |
| `role_balanced` | 确保每个角色有近似数量的评测样本 |

**LLM采样率参考**（12人6轮约71个决策）：

| 采样率 | LLM调用次数 | 适用场景 |
|--------|-------------|----------|
| `1.0` | ~50-60 | 全量评测 |
| `0.3` | ~15-20 | 平衡成本与质量 |
| `0.05` | ~3-4 | 快速验证 |

### 4.3 评测报告

评测完成后在 `reports/` 目录生成：

| 文件 | 内容 |
|------|------|
| `evaluation_report_*.json` | 完整JSON报告（规则引擎 + LLM评分 + 融合分数 + dimension_reasons） |
| `evaluation_report_*.md` | 人类可读Markdown摘要 |
| `dashboard_*.html` | 可视化HTML Dashboard（自包含页面，无需服务器） |

### 4.4 评测维度

**5个通用维度** + **11个角色专属维度** + **1个结果维度** = 17个维度：

| 维度 | 适用角色 | 说明 |
|------|----------|------|
| 推理质量 | 全部 | 逻辑链完整性、证据充分性 |
| 信息利用 | 全部 | 对已知信息的使用效率 |
| 言行一致性 | 全部 | 发言与投票/行动是否矛盾 |
| 博弈深度 | 全部 | L0(0-20) 到 L4+(81-100) |
| 信息隐藏 | 全部 | 保护关键信息的意识 |
| 团队协作 | 间谍 | 间谍间配合质量 |
| 伪装质量 | 间谍 | 伪装好人身份的能力 |
| 投票策略 | 间谍 | 归票和跟票的战术 |
| 背调效率 | HR总监 | 查验目标选择的价值 |
| 跳身份时机 | HR总监 | 何时公布查验结果 |
| 留人策略 | CEO | 留人offer使用时机 |
| 辞退策略 | CEO | 辞退信使用时机 |
| 诉讼策略 | 法务总监 | 出局时带走谁 |
| 保护策略 | 安保主管 | 保护目标选择 |
| 公司贡献 | 普通员工 | 对好人阵营的贡献 |
| 结果对齐度 | 全部 | 决策与最终胜负的关联 |

**动态权重**：游戏不同阶段维度权重不同（早期信息利用1.5x，中期博弈深度1.3x，晚期一致性/伪装1.5x）。

### 4.5 版本对比

```bash
python evaluation_cn.py --compare-versions exports/v2 exports/v3
```

---

## 5. Step 3：Skills进化生成

### 5.1 从评测报告生成Skills

```bash
# 模板模式（快速，不需要额外API调用）
python evolution.py generate --from-report reports/evaluation_report_xxx.json --version evo_3

# LLM精炼模式（质量更高，需要API Key）
python evolution.py generate --from-report reports/evaluation_report_xxx.json --version evo_4 --use-llm
```

### 5.2 Skills文件结构

生成的Skills存储在 `skills/versions/{version}/` 下：

```
skills/versions/evo_4/
├── meta.json                    # 版本元数据
├── 间谍.md                      # 完整策略（初始注入用）
├── 间谍.early.vote.md           # 前期投票子片段（阶段注入用）
├── 间谍.early.skill.md          # 前期技能子片段
├── 间谍.mid.vote.md             # 中期投票子片段
├── 间谍.mid.skill.md            # 中期技能子片段
├── HR总监.md
├── HR总监.early.vote.md
├── CEO.md
├── 法务总监.md
├── 安保主管.md
└── 普通员工.md
```

**多颗粒度结构**：`角色 × 阶段 × 事件类型`

| 层级 | 取值 | 说明 |
|------|------|------|
| 角色 | 间谍/HR总监/CEO/法务总监/安保主管/普通员工 | 按角色生成专属策略 |
| 阶段 | early/mid/late | 前期(1-2轮)/中期(3-4轮)/后期(5-6轮) |
| 事件类型 | speech/vote/skill | 发言/投票/技能三种决策场景 |

**主文件**（`间谍.md`）：包含完整的策略指导，用于游戏开始前的**初始注入**。

**子文件**（`间谍.early.vote.md`）：包含特定阶段+事件类型的精简策略，用于每轮的**阶段注入**。只有有对应评测数据的阶段才会生成子文件。

### 5.3 Skills内容结构

每个主文件按以下结构组织：

```markdown
## 间谍决策指导 Skills

### 前期(early)策略

#### 发言阶段
{评测数据提取的发言策略指导}
- 前期发言要点：隐藏身份，观察发言倾向

#### 投票阶段
{评测数据提取的投票策略指导}
- 前期投票要点：跟票为主，避免成为焦点

#### 技能阶段（夜间窃取）
{评测数据提取的技能策略指导}
- 前期窃取要点：优先窃取神职信息

### 中期(mid)策略
...

### 后期(late)策略
...

### 关键失误规避
{从findings提取的高/中危失误及建议}

### 反事实建议
{从counterfactual提取的替代方案}

### 维度弱项提升
{从dimension_reasons提取的维度诊断，含具体分数和理由}

### 行动清单
{可执行的行动建议}
```

### 5.4 模板模式 vs LLM精炼模式

| 对比项 | 模板模式 | LLM精炼模式 |
|--------|----------|-------------|
| 速度 | 快（<1秒） | 慢（每角色3-10秒） |
| API调用 | 无 | 6次（每角色1次） |
| 内容质量 | 中等（模板填充，可能有公式化文本） | 高（去冗余、按优先级排列、具体可执行） |
| dimension_reasons | 作为原始文本填入 | LLM消化后生成更精准的诊断 |
| 适用场景 | 快速验证、基线版本 | 正式进化迭代 |

---

## 6. Step 4：Skills注入对局

### 6.1 基本用法

```bash
# 所有玩家注入skills
python main_cn.py --players 12 --skills-version evo_4

# 仅间谍阵营注入
python main_cn.py --players 12 --skills-version evo_4 --skills-targets "faction:间谍"

# 仅公司阵营注入
python main_cn.py --players 12 --skills-version evo_4 --skills-targets "faction:公司"

# 指定座位号注入
python main_cn.py --players 12 --skills-version evo_4 --skills-targets "seat:1,3,5"

# 按角色注入
python main_cn.py --players 12 --skills-version evo_4 --skills-targets "role:预言家"

# 组合条件（间谍阵营 + 5号位）
python main_cn.py --players 12 --skills-version evo_4 --skills-targets "faction:间谍+seat:5"
```

### 6.2 targets语法

| 语法 | 含义 | 示例 |
|------|------|------|
| `all` | 全部注入 | `--skills-targets all` |
| `faction:间谍` | 仅间谍阵营 | `--skills-targets "faction:间谍"` |
| `faction:公司` | 仅公司阵营 | `--skills-targets "faction:公司"` |
| `seat:1,3,5` | 指定座位号 | `--skills-targets "seat:1,3,5"` |
| `role:预言家` | 按传统角色名 | `--skills-targets "role:预言家"` |
| `character:逻辑怪` | 按人设名 | `--skills-targets "character:逻辑怪"` |
| `+` 组合 | AND逻辑 | `"faction:间谍+seat:5"` |

### 6.3 两级注入机制

**初始注入**（游戏开始前）：
- 将角色的完整Skills追加到 `agent._sys_prompt`
- 提供角色级通用策略

**阶段注入**（每轮每个阶段前）：
- 根据当前阶段（early/mid/late）和事件类型（speech/vote/skill）注入精简策略
- 优先加载子文件（如 `间谍.early.vote.md`），fallback到主文件提取
- 通过 `Msg` 注入到 `agent.memory`

注入流程：

```
游戏开始 → 初始注入（完整Skills到sys_prompt）
  │
  ├─ 第1轮 夜间
  │   ├─ 间谍讨论 → 注入 early.skill 策略
  │   ├─ HR总监背调 → 注入 early.skill 策略
  │   ├─ 安保主管保护 → 注入 early.skill 策略
  │   └─ CEO行动 → 注入 early.skill 策略
  │
  ├─ 第1轮 白天
  │   ├─ 讨论 → 注入 early.speech 策略
  │   └─ 投票 → 注入 early.vote 策略
  │
  ├─ 第3轮 → mid阶段策略
  │
  └─ 第5轮 → late阶段策略
```

---

## 7. Step 5：自进化循环

### 7.1 一键进化

```bash
# 5代进化，每代3局，12人局
python evolution.py evolve --generations 5 --games-per-gen 3 --players 12

# 仅进化间谍
python evolution.py evolve --generations 5 --games-per-gen 3 --players 12 --skills-targets "faction:间谍"
```

### 7.2 进化流程

每代执行以下步骤：

```
1. 运行N局游戏（用当前版本Skills）
2. 评测最新一局
3. 从评测报告生成新版本Skills
4. 对比胜率：提升 → 采用新版；下降>0.5% → 回滚
5. 记录到进化历史
```

### 7.3 手动进化步骤

如果想手动控制每一步：

```bash
# Step 1: 运行一局游戏（无Skills）
python main_cn.py --players 12 --log exports/baseline_game

# Step 2: 评测
python evaluation_cn.py --log exports/baseline_game.jsonl --enable-llm-judge --llm-sample-rate 0.5

# Step 3: 生成Skills
python evolution.py generate --from-report reports/evaluation_report_xxx.json --version evo_3

# Step 4: 用Skills运行游戏
python main_cn.py --players 12 --skills-version evo_3 --log exports/with_skills_game

# Step 5: 再评测
python evaluation_cn.py --log exports/with_skills_game.jsonl --enable-llm-judge --llm-sample-rate 0.5

# Step 6: 用LLM精炼生成下一代
python evolution.py generate --from-report reports/evaluation_report_yyy.json --version evo_4 --use-llm

# 回到 Step 4，用 evo_4 继续迭代...
```

### 7.4 查看进化状态

```bash
# 进化历史
python evolution.py history

# 胜率统计
python evolution.py stats --group-by faction
python evolution.py stats --group-by skills --all
```

### 7.5 批量运行与A/B实验

```bash
# 批量运行10局
python batch_runner.py --num-games 10 --players 12 --prompt-version v2

# A/B实验（对比两个prompt版本）
python ab_experiment.py --version-a v2 --version-b v3 --num-games 3 --players 12
```

---

## 8. 可视化与复盘

### 8.1 游戏回放

```bash
python web_ui.py --host 127.0.0.1 --port 7860
```

浏览器访问 `http://127.0.0.1:7860`，可回放游戏日志，查看角色、发言、投票等。

### 8.2 评测报告查看

```bash
# 方式1：查看Markdown摘要
cat reports/evaluation_report_*.md

# 方式2：打开HTML Dashboard（自包含，无需服务器）
# 直接用浏览器打开 reports/dashboard_*.html

# 方式3：Web Dashboard
python review_dashboard.py --host 127.0.0.1 --port 7007
```

### 8.3 输出文件一览

| 目录 | 文件格式 | 说明 |
|------|----------|------|
| `exports/` | `.jsonl` `.txt` `.log` | 游戏日志 |
| `reports/` | `.json` `.md` `.html` | 评测报告 |
| `skills/versions/` | `.md` | Skills策略文件 |
| `winrate/` | `history.jsonl` | 胜率历史 |
| `evolution/` | `history.json` | 进化历史 |
| `prompts/v2/` | `.txt` | 角色prompt模板 |

---

## 9. 项目结构

```
Three-Kingdoms-Multi-Agent-Werewolf-main/
│
├── main_cn.py                 # 游戏入口：OfficeWerewolfGame
├── model_config.py            # 游戏Agent模型配置（MODEL_*）
├── game_roles.py              # 角色定义 + 12种人设
├── structured_output_cn.py    # Pydantic结构化输出模型
├── utils_cn.py                # 规则引擎：胜负判定、投票、主持人
├── context_manager.py         # 上下文窗口管理（滑动窗口）
├── game_logger.py             # JSON结构化日志（JSONGameLogger）
├── logging_config.py          # 双层日志系统
├── prompt_cn.py               # 版本化Prompt管理
├── prompt_logger.py           # Prompt日志记录
│
├── evaluation_cn.py           # 评测入口：规则引擎 + LLM评测
├── evaluation_dashboard.py    # HTML Dashboard生成
├── jsonl_parser.py            # JSONL日志解析器
│
├── evolution.py               # Skills进化CLI
├── winrate_tracker.py         # 胜率追踪
├── batch_runner.py            # 批量运行
├── ab_experiment.py           # A/B实验
│
├── web_ui.py                  # 游戏回放Web UI
├── review_dashboard.py        # 评测报告Web Dashboard
│
├── eval_agent/                # 评测Agent模块
│   ├── config.py              #   评测模型配置（EVAL_MODEL_*）
│   ├── context_builder.py     #   决策上下文构建
│   ├── dimensions.py          #   17个评测维度定义
│   ├── game_knowledge.py      #   领域知识注入
│   ├── judge.py               #   EvalJudge 异步评测
│   ├── prompt_templates.py    #   评测Prompt模板
│   ├── quality_checker.py     #   质量自检
│   └── score_integrator.py    #   评分融合 + 聚合
│
├── skills_agent/              # Skills生成与调度模块
│   ├── generator.py           #   SkillsGenerator 多颗粒度生成
│   ├── templates.py           #   角色Skills模板（13占位符）
│   ├── dispatcher.py          #   SkillsDispatcher 两级注入
│   └── skills_store.py        #   SkillsStore 版本化存储
│
├── skills/                    # Skills文件存储
│   ├── base.py                #   SkillBase 抽象基类
│   ├── registry.py            #   @register_skill 装饰器注册
│   ├── guard_protect.py       #   安保主管技能
│   ├── hunter_shoot.py        #   法务总监技能
│   ├── seer_check.py          #   HR总监技能
│   ├── werewolf_kill.py       #   间谍技能
│   ├── witch_act.py           #   CEO技能
│   ├── spy_strategy.py        #   间谍战术协作
│   └── versions/              #   版本化Skills存储
│       ├── evo_3/             #     模板模式生成
│       └── evo_4/             #     LLM精炼模式生成
│
├── prompts/                   # Prompt模板
│   └── v2/                    #   v2版本角色prompt
│
├── plugins/                   # 插件系统
│   ├── plugin_loader.py       #   动态角色注册
│   └── idiot_manifest.json    #   示例：白痴角色
│
├── docs/                      # 文档
│   ├── project_guide.md       #   项目指南
│   ├── evaluation_system_doc.md # 评测系统文档
│   └── information_isolation.md # 信息隔离设计
│
├── tests/                     # 单元测试
│   ├── test_skills.py         #   技能测试
│   ├── test_voting.py         #   投票测试
│   ├── test_winning.py        #   胜负判定测试
│   └── ...
│
├── exports/                   # 游戏日志输出
├── reports/                   # 评测报告输出
├── winrate/                   # 胜率历史数据
└── evolution/                 # 进化历史数据
```

---

## 10. 配置参考

### 10.1 游戏Agent环境变量（前缀 `MODEL_`）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DASHSCOPE_API_KEY` | 百炼API Key（全局回退） | 无 |
| `MODEL_DEFAULT_MODEL_NAME` | 默认模型名 | `qwen-max` |
| `MODEL_DEFAULT_ENABLE_THINKING` | 默认思维链 | `true` |
| `MODEL_DEFAULT_API_KEY` | 默认API Key | 回退到 `DASHSCOPE_API_KEY` |
| `MODEL_DEFAULT_BASE_URL` | 设了→OpenAI兼容 | 空 |
| `MODEL_DEFAULT_GENERATE_KWARGS` | 生成参数JSON | `{}` |
| `MODEL_SEAT_N_MODEL_NAME` | N号位模型名 | 使用默认 |
| `MODEL_SEAT_N_BASE_URL` | N号位接口地址 | 使用默认 |
| `MODEL_SEAT_N_API_KEY` | N号位API Key | 使用默认 |

优先级：`MODEL_SEAT_N_*` > `MODEL_DEFAULT_*` > 硬编码回退

### 10.2 评测Agent环境变量（前缀 `EVAL_MODEL_`）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EVAL_MODEL_MODEL_NAME` | 评测模型名 | `deepseek-v4-pro` |
| `EVAL_MODEL_API_KEY` | API Key | 回退到 `DASHSCOPE_API_KEY` |
| `EVAL_MODEL_BASE_URL` | 设了→OpenAI兼容 | 空 |
| `EVAL_MODEL_ENABLE_THINKING` | 思维链 | `false` |
| `EVAL_MODEL_GENERATE_KWARGS` | 生成参数 | `{"temperature":0.3}` |
| `EVAL_MODEL_MAX_CONCURRENT` | 最大并发数 | `3` |
| `EVAL_MODEL_SAMPLE_RATE` | 默认采样率 | `1.0` |

### 10.3 main_cn.py CLI参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--players` | 玩家数（6/9/12） | 交互式选择 |
| `--prompt-version` | Prompt版本 | `v2` |
| `--agent-version` | Agent版本标签 | `baseline` |
| `--skills-version` | Skills版本 | 无 |
| `--skills-targets` | Skills注入目标 | `all` |
| `--context-window` | 上下文窗口大小 | `80` |
| `--witch-can-self-save` | CEO首夜可自救 | `true` |
| `--log` | 日志文件路径 | `game_log.txt` |
| `--log-level` | 日志级别 | `WARNING` |
| `--verbose` | 详细诊断日志 | `false` |

### 10.4 evolution.py CLI命令

| 命令 | 说明 |
|------|------|
| `generate --from-report R --version V [--use-llm]` | 从评测报告生成Skills |
| `evolve --generations N --games-per-gen M --players P` | 运行进化循环 |
| `evaluate --version V --num-games N --players P` | 用指定Skills版本运行评测局 |
| `history` | 查看进化历史 |
| `stats --group-by G [--all]` | 查看胜率统计 |

### 10.5 evaluation_cn.py CLI参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--log` | 日志文件路径 | `game_log.txt` |
| `--enable-llm-judge` | 启用LLM深度评测 | `false` |
| `--llm-sample-rate` | LLM采样率 | `1.0` |
| `--eval-model` | 评测模型名 | 使用EVAL_MODEL配置 |
| `--eval-sample-strategy` | 采样策略 | `uniform` |
| `--compare-versions` | 版本对比 | 无 |
| `--demo-bad-case` | 内置bad case验证 | `false` |
| `--output-dir` | 报告输出目录 | `reports/` |

---

## 11. 常见问题

### Q: 运行游戏时提示 `InvalidApiKey`

确认 `.env` 中 `DASHSCOPE_API_KEY` 已正确设置，且文件在项目根目录。

### Q: `--use-llm` 精炼时报 `No API-key provided`

`EVAL_MODEL_API_KEY` 未设置且 `DASHSCOPE_API_KEY` 未被加载。确保 `evolution.py` 入口能读取 `.env`（已内置 `load_dotenv()`）。

### Q: 评测报告没有 `dimension_reasons` 字段

需要使用 `--enable-llm-judge` 且评测的 `.jsonl` 文件中必须有对应的LLM评测数据。纯规则引擎评测不产生 `dimension_reasons`。

### Q: Skills阶段注入没有生效

1. 确认初始注入已成功（日志中应有 `Skills injected (initial)` 信息）
2. 确认阶段注入需要座位号在 `injected_seats` 中
3. 检查Skills文件是否有对应阶段的内容（如 `### 前期(early)策略` 块）

### Q: 旧版Skills（evo_1/evo_2）没有子文件，能用吗？

可以。Dispatcher会自动fallback：
1. 先查找子文件（`角色.阶段.事件类型.md`）→ 不存在则
2. 从主文件提取 `### 阶段` 块 → 找到 `#### 事件类型` 子块则精简注入，否则注入整个阶段块

### Q: 6人局/9人局的角色配置

- **6人**：2间谍 + 1HR总监 + 1CEO + 2普通员工
- **9人**：3间谍 + 1HR总监 + 1CEO + 1法务总监 + 3普通员工
- **12人**：4间谍 + 1HR总监 + 1CEO + 1法务总监 + 1安保主管 + 4普通员工

### Q: 如何查看游戏中Skills注入效果

游戏日志（`.jsonl`）的 `game_over` 事件中记录了 `skills_injection` 字段，包含版本号、目标和注入的座位列表。

### Q: 如何添加新角色

使用插件系统，在 `plugins/` 目录创建JSON manifest：

```json
{
  "role_name": "白痴",
  "description": "呆萌实习生",
  "ability": "被投票出局时可以翻牌免死，但此后不再有投票权",
  "team": "公司阵营",
  "skill": { "class_path": null, "description": "翻牌免死" },
  "prompt_file": "idiot.txt"
}
```

然后在 `prompts/v2/` 下添加对应的prompt文件。

---

## 12. Skills版本对比与A/B实验

### 12.1 为什么要做版本对比

Skills进化的核心问题是：**新版本真的比旧版本好吗？** 仅靠主观感受无法判断，需要通过对照实验验证。版本对比回答以下问题：

- evo_4(LLM精炼) 是否比 evo_3(模板) 更有效？
- 间谍阵营的 Skills 提升是否大于公司阵营？
- Skills 注入是否比无 Skills 的基线更强？

### 12.2 同一版本 vs 基线（无Skills）

最简单的对比——有 Skills 和无 Skills 谁更强：

```bash
# 对照组：无 Skills
python main_cn.py --players 12 --log exports/baseline_game1

# 实验组：使用 evo_4 Skills
python main_cn.py --players 12 --skills-version evo_4 --log exports/evo4_game1

# 各自评测
python evaluation_cn.py --log exports/baseline_game1.jsonl --enable-llm-judge --llm-sample-rate 0.3
python evaluation_cn.py --log exports/evo4_game1.jsonl --enable-llm-judge --llm-sample-rate 0.3

# 对比评测报告
python evaluation_cn.py --compare-versions exports/baseline exports/evo4
```

### 12.3 不同版本 Skills 对比

对比两个版本的 Skills 效果：

```bash
# 版本A：evo_3
python main_cn.py --players 12 --skills-version evo_3 --log exports/evo3_game1

# 版本B：evo_4
python main_cn.py --players 12 --skills-version evo_4 --log exports/evo4_game1

# 各自评测
python evaluation_cn.py --log exports/evo3_game1.jsonl --enable-llm-judge --llm-sample-rate 0.3
python evaluation_cn.py --log exports/evo4_game1.jsonl --enable-llm-judge --llm-sample-rate 0.3
```

### 12.4 阵营对比实验（不同版本给不同阵营）

**核心场景**：间谍用版本A的Skills，公司用版本B的Skills，看哪边更强。

#### 方法一：使用混合版本目录

```bash
# Step 1：创建混合版本目录
# 将 evo_3 的间谍Skills + evo_4 的公司Skills 合并到同一版本
python -c "
from skills_agent.skills_store import SkillsStore
import shutil, os

store = SkillsStore()
mixed = 'evo_3_spy_evo_4_co'   # 混合版本名
spy_roles = ['间谍']
company_roles = ['HR总监', 'CEO', '法务总监', '安保主管', '普通员工']

for role_wp in spy_roles + company_roles:
    src = 'evo_3' if role_wp in spy_roles else 'evo_4'
    content = store.load(src, role_wp)
    if content:
        store.save(mixed, role_wp, content)
    # 复制子文件
    src_dir = f'skills/versions/{src}'
    dst_dir = f'skills/versions/{mixed}'
    os.makedirs(dst_dir, exist_ok=True)
    for f in os.listdir(src_dir):
        if f.startswith(role_wp) and f.endswith('.md') and f != f'{role_wp}.md':
            shutil.copy2(os.path.join(src_dir, f), os.path.join(dst_dir, f))

# 写元数据
meta = {
    'version': mixed,
    'description': 'evo_3 spy + evo_4 company A/B test',
    'spy_skills': 'evo_3',
    'company_skills': 'evo_4',
}
store.save_meta(mixed, meta)
print(f'Created mixed version: {mixed}')
"

# Step 2：用混合版本运行游戏（所有玩家注入同一版本，但间谍和公司的Skills内容不同）
python main_cn.py --players 12 --skills-version evo_3_spy_evo_4_co --log exports/ab_spy3_co4

# Step 3：评测
python evaluation_cn.py --log exports/ab_spy3_co4.jsonl --enable-llm-judge --llm-sample-rate 0.5
```

#### 方法二：使用 `--skills-targets` 分两次运行

```bash
# 仅给间谍注入 evo_3
python main_cn.py --players 12 --skills-version evo_3 --skills-targets "faction:间谍" --log exports/spy_evo3

# 仅给公司注入 evo_4
python main_cn.py --players 12 --skills-version evo_4 --skills-targets "faction:公司" --log exports/co_evo4
```

> ⚠️ **注意**：方法二中两次运行是独立的对局，游戏结果不可直接对比（随机性太大）。方法一（混合版本）在同一局中对比，结果更可靠。

### 12.5 A/B 实验框架（多局统计）

单局结果随机性大，需要多局统计才有意义：

```bash
# 使用内置 A/B 实验框架（对比 prompt 版本）
python ab_experiment.py --version-a v2 --version-b v3 --num-games 3 --players 12

# 使用 batch_runner 批量运行
python batch_runner.py --num-games 5 --players 12 --skills-version evo_4 --log exports/evo4_batch
```

#### 手动批量对比流程

```bash
# 运行5局 evo_3
for i in $(seq 1 5); do
    python main_cn.py --players 12 --skills-version evo_3 --log exports/evo3_batch_$i
done

# 运行5局 evo_4
for i in $(seq 1 5); do
    python main_cn.py --players 12 --skills-version evo_4 --log exports/evo4_batch_$i
done

# 统计胜率
python winrate_tracker.py --stats --group-by skills
```

### 12.6 使用进化循环自动对比

`evolution.py` 内置了版本对比和回滚逻辑：

```bash
# 自动进化5代，每代3局，自动对比胜率决定是否保留新版本
python evolution.py evolve --generations 5 --games-per-gen 3 --players 12

# 查看胜率统计
python evolution.py stats --group-by skills --all

# 查看进化历史
python evolution.py history
```

**回滚逻辑**：如果新版本胜率比上一版本下降超过0.5%，自动回退到上一版本。

### 12.7 版本对比评测报告

对比两份评测报告的差异：

```bash
python evaluation_cn.py --compare-versions reports/evaluation_report_evo3.json reports/evaluation_report_evo4.json
```

输出包含各维度、各角色的分数差异，以及是否达到统计显著性。

### 12.8 典型实验设计

| 实验目的 | 方法 | 命令 |
|----------|------|------|
| Skills vs 无Skills | 同版本注入 vs 不注入 | `--skills-version evo_4` vs 不加参数 |
| evo_3 vs evo_4 | 两次独立运行 | `--skills-version evo_3` vs `--skills-version evo_4` |
| 间谍evo_3 vs 公司evo_4 | 混合版本目录 | 创建 `evo_3_spy_evo_4_co` 混合版本 |
| 仅间谍有Skills | targets过滤 | `--skills-version evo_4 --skills-targets "faction:间谍"` |
| 特定座位有Skills | targets过滤 | `--skills-version evo_4 --skills-targets "seat:1,5,9"` |
| 多局统计对比 | batch_runner | `python batch_runner.py --num-games 10` |
| 自动进化对比 | evolution.py | `python evolution.py evolve --generations 5` |

### 12.9 对局报告说明

管线自动生成的报告文件：

| 文件 | 内容 | 自动/手动 |
|------|------|-----------|
| `evaluation_report_*.json` | 完整评测数据（规则+LLM+dimension_reasons） | ✅ 自动 |
| `evaluation_report_*.md` | 评测摘要（维度评分、Leaderboard、Findings） | ✅ 自动 |
| `dashboard_*.html` | 可视化HTML Dashboard | ✅ 自动 |

**注意**：管线自动生成的报告是通用评测摘要格式，**不包含**阵营对比、Skills版本对照、投票时间线等对局特定分析。如需生成定制化的版本对比报告（如 `evo3spy_vs_evo4co_report.md`），需结合 `evaluation_report_*.json` + `exports/*.jsonl` 手动撰写或开发专用报告生成器。

---

## 快速上手：5分钟跑通全管线

```bash
# 1. 配置环境
cp .env.example .env
# 编辑 .env 填入 DASHSCOPE_API_KEY

# 2. 运行一局游戏
python main_cn.py --players 6 --log exports/quick_start

# 3. 评测（规则引擎 + LLM）
python evaluation_cn.py --log exports/quick_start.jsonl --enable-llm-judge --llm-sample-rate 0.3

# 4. 生成Skills（LLM精炼）
python evolution.py generate --from-report reports/evaluation_report_*.json --version evo_1 --use-llm

# 5. 用Skills再跑一局
python main_cn.py --players 6 --skills-version evo_1 --log exports/with_skills

# 6. 查看HTML报告
# 浏览器打开 reports/dashboard_*.html
```

# 职场狼人杀 — 使用指南

## 快速开始

双击 `run.bat` 启动菜单，按数字选择操作即可。所有参数都有默认值，回车直接用默认。

首次使用前需配置 `.env` 文件：

```
DASHSCOPE_API_KEY=sk-xxxxxxxx
```

---

## 目录结构

```
项目根目录/
├── run.bat                  ← 统一启动器（双击打开）
├── main_cn.py               ← 游戏引擎
├── evaluation_cn.py         ← 评测引擎
├── evolution.py             ← Skills 进化
├── batch_runner.py          ← 批量运行
├── ab_experiment.py         ← A/B 实验
├── web_ui.py                ← 游戏回放 Web UI
├── review_dashboard.py     ← 评测面板 Web UI
├── test_env.py              ← 环境检查
│
├── .env                     ← API Key 配置（需自行创建）
├── prompts/v2/              ← 角色提示词
│   ├── werewolf.txt         ← 间谍
│   ├── seer.txt             ← HR总监（预言家）
│   ├── witch.txt            ← CEO（女巫）
│   ├── hunter.txt           ← 法务总监（猎人）
│   ├── guard.txt            ← 安保主管（守护者）
│   └── villager.txt         ← 普通员工（村民）
│
├── exports/                 ← 游戏日志输出目录
├── reports/                 ← 评测报告输出目录
├── winrate/                 ← 胜率历史
├── evolution/               ← 进化历史
├── skills/versions/         ← Skills 版本仓库
└── shared/                  ← 共享模块（角色映射、数据模型、解析工具）
```

---

## run.bat 菜单详解

### 1. 运行单局游戏

运行一局完整的职场狼人杀。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 玩家人数 | 6 / 9 / 12 | 12 |
| Prompt版本 | v2 / v3 | v2 |
| Skills版本 | 留空=不注入，填 evo_6 / evo_8 等 | 不注入 |

**输出文件**（自动时间戳命名）：
- `exports/game_{人数}p_{时间戳}.txt` — 人类可读的游戏叙事
- `exports/game_{人数}p_{时间戳}.jsonl` — 结构化事件日志（评测用）
- `exports/game_{人数}p_{时间戳}.log` — 诊断日志

**等效命令**：
```bash
python main_cn.py --players 12 --prompt-version v2 --log exports/game_12p_20260604_120000
python main_cn.py --players 6  # 最简形式
python main_cn.py --players 12 --skills-version evo_8  # 注入 Skills
```

### 2. 批量运行

连续运行多局游戏，汇总统计数据。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 游戏局数 | 顺序执行 | 3 |
| 玩家人数 | 6 / 9 / 12 | 12 |
| Prompt版本 | v2 / v3 | v2 |

**输出目录**：`exports/batch_{时间戳}/`

**等效命令**：
```bash
python batch_runner.py --num-games 5 --players 12
```

### 3. A/B 实验

对比两个 Prompt/Skills 版本，统计胜率差异。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 版本A | 对照组 | v2 |
| 版本B | 实验组 | v3 |
| 每版本局数 | 各跑几局 | 3 |
| 玩家人数 | 6 / 9 / 12 | 12 |

**输出目录**：`exports/ab_{版本A}_vs_{版本B}_{时间戳}/`

**等效命令**：
```bash
python ab_experiment.py --version-a v2 --version-b v3 --num-games 3
```

### 4. 评测游戏日志

对已完成的游戏进行多维度评测，生成评分报告和可视化 Dashboard。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 日志文件 | .jsonl 或 .txt 路径 | 必填 |
| Agent版本标签 | 标记评测对象 | baseline |
| LLM评测 | y=启用深度LLM评分 | n |

菜单会自动列出 `exports/` 下的 `.jsonl` 文件供选择。

**输出文件**（写入 `reports/`）：
- `evaluation_report_{时间戳}.json` — 完整评测数据
- `evaluation_report_{时间戳}.md` — 人类可读摘要
- `dashboard_{时间戳}.html` — 可视化面板（浏览器打开）

**等效命令**：
```bash
# 规则引擎评测（不需要 API Key）
python evaluation_cn.py --log exports/game_12p_20260604.jsonl

# 规则引擎 + LLM深度评测
python evaluation_cn.py --log exports/game_12p_20260604.jsonl --enable-llm-judge

# LLM评测 + 低采样率（节省成本，约15-20次LLM调用）
python evaluation_cn.py --log exports/game_12p_20260604.jsonl --enable-llm-judge --llm-sample-rate 0.3
```

### 5. Skills 进化

子菜单，管理 Skills 的生成、进化、评测和统计。

| 子选项 | 说明 | 关键参数 |
|--------|------|----------|
| a) 生成 Skills | 从评测报告提取改进建议 | 报告路径、版本名 |
| b) 进化循环 | 自动迭代：跑局→评测→生成→对比→保留/回滚 | 代数、每代局数 |
| c) 评测版本 | 对指定 Skills 版本跑局并评测 | 版本名、局数 |
| d) 进化历史 | 查看历次进化记录 | 无 |
| e) 胜率统计 | 按 faction / role / skills / version 分组 | 分组方式 |

**等效命令**：
```bash
python evolution.py generate --from-report reports/evaluation_report_xxx.json --version evo_2
python evolution.py evolve --generations 5 --games-per-gen 3
python evolution.py evaluate --version evo_3 --num-games 5
python evolution.py history
python evolution.py stats --group-by faction
```

### 6. 前端系统

**主前端（Next.js 实时对局系统）**：

```bash
cd frontend
npm install   # 首次安装依赖
npm run dev   # http://localhost:3000
```

支持实时对局观战、3D竞技场、SSE事件流、人机混战、TTS/ASR语音、对局回放。

**轻量回放（备选）**：

| 子选项 | 说明 | 地址 |
|--------|------|------|
| a) 游戏回放 | Gradio 围桌式动画回放 | http://127.0.0.1:7860 |
| b) 评测面板 | 评测报告、排行榜 | http://127.0.0.1:7007 |

```bash
python web_ui.py --host 127.0.0.1 --port 7860
python review_dashboard.py --host 127.0.0.1 --port 7007
```

### 7. 环境检查

检查 Python 版本、`.env` 文件、API Key 和模型配置。无参数，直接运行。

**等效命令**：`python test_env.py`

### 8. 运行测试

| 子选项 | 说明 |
|--------|------|
| a) 全部测试 | 150 个测试用例，约 3 秒 |
| b) 指定文件 | 如 `tests/test_voting.py` |
| c) 快速冒烟 | 只跑核心 4 个文件（投票、胜负、技能、保护修复） |
| d) 返回主菜单 | — |

**等效命令**：
```bash
python -m pytest tests/ -v
python -m pytest tests/test_voting.py -v
```

---

## 工作流示例

### 典型流程：跑局 → 评测 → 观战

```
1. 双击 run.bat
2. 选 1 → 运行单局游戏（12人，回车用默认值）
3. 游戏结束后回到菜单
4. 选 4 → 评测游戏日志
   - 从列表选择刚生成的 .jsonl 文件
   - 不启用 LLM 评测（回车用默认值）
5. 打开前端观战/回放
   - cd frontend && npm run dev
   - 浏览器访问 http://localhost:3000
```

### Skills 进化流程

```
1. 选 5b → 进化循环（5代，每代3局）
   - 自动跑局 → 评测 → 生成 Skills → 对比胜率 → 保留/回滚
2. 进化完成后选 5e → 查看胜率统计
3. 选 5d → 查看进化历史
```

### A/B 对比实验

```
1. 选 3 → A/B 实验
   - 版本A: v2（基线）
   - 版本B: v3（改进版）
   - 每版本3局
2. 自动跑局 + 评测 + 统计显著性检验
3. 结果输出到 exports/ab_v2_vs_v3_*/
```

---

## 文件命名规范

所有输出文件自动使用时间戳命名，不会覆盖旧文件：

| 类型 | 命名格式 | 示例 |
|------|----------|------|
| 游戏日志 | `game_{人数}p_{YYYYMMDD_HHMMSS}.{txt\|jsonl\|log}` | `game_12p_20260604_153000.jsonl` |
| 进化日志 | `evo_game_{人数}p_{YYYYMMDD_HHMMSS}.{txt\|jsonl\|log}` | `evo_game_12p_20260604_153000.jsonl` |
| 批量目录 | `batch_{YYYYMMDD_HHMMSS}/` | `batch_20260604_153000/` |
| A/B 目录 | `ab_{v1}_vs_{v2}_{YYYYMMDD_HHMMSS}/` | `ab_v2_vs_v3_20260604_153000/` |
| 评测报告 | `evaluation_report_{YYYYMMDD_HHMMSS}_{微秒}.json` | `evaluation_report_20260604_153000_427656.json` |
| 评测摘要 | `evaluation_report_{YYYYMMDD_HHMMSS}_{微秒}.md` | `evaluation_report_20260604_153000_427656.md` |
| Dashboard | `dashboard_{YYYYMMDD_HHMMSS}_{微秒}.html` | `dashboard_20260604_153000_427656.html` |

---

## 环境变量

### 必需

| 变量 | 说明 | 配置方式 |
|------|------|----------|
| `DASHSCOPE_API_KEY` | 百炼平台 API Key | 写入 `.env` 文件 |

### 可选 — 游戏模型配置（前缀 `MODEL_`）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MODEL_DEFAULT_MODEL_NAME` | 全局默认模型 | qwen-max |
| `MODEL_DEFAULT_ENABLE_THINKING` | 全局思维链 | true |
| `MODEL_DEFAULT_BASE_URL` | 设了→OpenAI兼容接口 | 空=百炼 |
| `MODEL_DEFAULT_API_KEY` | OpenAI兼容接口 Key | 回退到百炼 |
| `MODEL_SEAT_N_MODEL_NAME` | 指定座位模型（N=1-12） | 用全局默认 |
| `MODEL_SEAT_N_BASE_URL` | 指定座位接口 | 用全局默认 |
| `MODEL_SEAT_N_ENABLE_THINKING` | 指定座位思维链 | 用全局默认 |

### 可选 — 评测模型配置（前缀 `EVAL_MODEL_`，独立于游戏）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EVAL_MODEL_MODEL_NAME` | 评测模型 | qwen-max |
| `EVAL_MODEL_API_KEY` | 评测 Key | 回退到百炼 |
| `EVAL_MODEL_BASE_URL` | 设了→OpenAI兼容 | 空=百炼 |
| `EVAL_MODEL_ENABLE_THINKING` | 评测思维链 | true |
| `EVAL_MODEL_SAMPLE_RATE` | 评测采样率 | 1.0 |

---

## 角色对照表

游戏使用职场隐喻命名，传统狼人杀角色对应如下：

| 职场名 | 传统名 | 阵营 | 能力 |
|--------|--------|------|------|
| 间谍 | 狼人 | 间谍阵营 | 每晚协商窃取一名员工 |
| HR总监 | 预言家 | 公司阵营 | 每晚背调一人查验身份 |
| CEO | 女巫 | 公司阵营 | 留人offer（解药）+ 辞退信（毒药），各一次 |
| 法务总监 | 猎人 | 公司阵营 | 离职时可发起诉讼带走一人 |
| 安保主管 | 守护者 | 公司阵营 | 每晚保护一人，不能连续保护同一人 |
| 普通员工 | 村民 | 公司阵营 | 无特殊技能，靠推理投票 |

### 关键规则

| 规则 | 说明 |
|------|------|
| 同保同挽留 | 安保保护 + CEO挽留同时作用于同一目标时，该目标仍然离职（对冲互消） |
| 安保连续保护限制 | 不能连续两晚保护同一人（代码强制执行，违规自动重试+兜底） |
| CEO一晚一份 | 留人offer和辞退信一晚只能用一份，各只能用一次 |
| 法务诉讼限制 | 被辞退信开除不能发起诉讼，被窃取离职可以 |
| 狼人自刀防护 | 代码过滤掉狼人互投的票（代码强制执行） |

---

## 前端系统（Next.js）

除了 Python 后端的 Web UI，项目还包含一套独立的 Next.js 前端，提供实时对局观战、回放、人机混战等功能。

### 启动

```bash
cd frontend
npm install   # 首次安装依赖
npm run dev   # 启动开发服务器
# 访问 http://localhost:3000
```

### 功能

| 功能 | 说明 |
|------|------|
| SSE 实时流 | 后端对局进行时，前端实时展示事件 |
| 对局回放 | 选择 exports/ 下的 .jsonl 文件回放 |
| 3D 竞技场 | Three.js 渲染玩家座位布局 |
| TTS 语音播报 | 对局事件自动语音播报 |
| ASR 语音输入 | 人机混战时支持语音输入发言 |
| 认知雷达 | 12维 Agent 表现分析面板 |

---

## 也可直接命令行

`run.bat` 内部就是调用 Python 脚本，熟悉命令行的用户可以直接用：

```bash
# 运行游戏
python main_cn.py --players 12

# 评测
python evaluation_cn.py --log exports/game_12p_20260604.jsonl

# 进化
python evolution.py evolve --generations 3

# 前端（实时对局 + 回放）
cd frontend && npm run dev  # http://localhost:3000

# 轻量回放（备选）
python web_ui.py  # http://127.0.0.1:7860

# 测试
python -m pytest tests/ -v
```

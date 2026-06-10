# 数据结果

## dashboards/ — 评测可视化面板

双击 HTML 文件即可在浏览器中打开，无需服务器。

| 文件 | 说明 |
|------|------|
| `01_early_baseline.html` | 早期对局（迭代前），综合得分约35，中危失误60+ |
| `02_mid_evo6.html` | 中期对局（evo_6 后），综合得分50+，失误大幅减少 |
| `03_latest_evo8.html` | 最新对局（evo_8 + 协议确认），综合得分58+，中危失误1-2 |
| `04_bad_case_demo.html` | 刻意构造的失误对局，验证评测系统的失误检出能力 |

## game_logs/ — 对局日志（JSONL 结构化事件流）

可用于：
- 前端回放（`cd frontend && npm run dev`，选择文件加载）
- 重新运行评测（`python evaluation_cn.py --log data/game_logs/xxx.jsonl`）

| 文件 | 说明 |
|------|------|
| `demo_bad_case.jsonl` | 构造的6人失误对局（间谍自窃、预言家自查等） |
| `eval_final.jsonl` | 12人完整对局（evo_8版本） |
| `game_12p_20260605_151144.jsonl` | 12人完整对局（中期版本） |

## 其他数据

| 文件 | 说明 |
|------|------|
| `history.json` | 进化引擎历史（3代迭代，含胜率变化和回滚记录） |
| `winrate_history.jsonl` | 跨版本胜率追踪数据 |

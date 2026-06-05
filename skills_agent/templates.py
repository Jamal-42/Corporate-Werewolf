# -*- coding: utf-8 -*-
"""Skills prompt模板 — 按角色×阶段×事件类型生成结构化指导

每种角色提供一个模板骨架，占位符由generator填充。
占位符: {stage}_{event_type}_actions × 9 + mistakes + counterfactuals + weak_dims + actions
"""

ROLE_WORKPLACE = {
    "狼人": "间谍", "预言家": "HR总监", "女巫": "CEO",
    "猎人": "法务总监", "守护者": "安保主管", "村民": "普通员工",
}

# 所有角色共享的模板骨架结构
_TEMPLATE_BODY = """
### 前期(early)策略

#### 发言阶段
{early_speech_actions}
- 前期发言要点：隐藏身份，观察发言倾向，记录身份声明

#### 投票阶段
{early_vote_actions}
- 前期投票要点：跟票为主，避免成为焦点

#### 技能阶段（夜间窃取）
{early_skill_actions}
- 前期窃取要点：优先窃取神职信息，避免自刀

### 中期(mid)策略

#### 发言阶段
{mid_speech_actions}
- 中期发言要点：根据白天投票结果调整站边

#### 投票阶段
{mid_vote_actions}
- 中期投票要点：集中票型，配合队友归票

#### 技能阶段
{mid_skill_actions}
- 中期技能要点：结合信息调整窃取目标

### 后期(late)策略

#### 发言阶段
{late_speech_actions}
- 后期发言要点：残局中利用信息不对称

#### 投票阶段
{late_vote_actions}
- 后期投票要点：归票方向决定胜负

#### 技能阶段
{late_skill_actions}
- 后期技能要点：残局技能使用要精准

### 关键失误规避
{mistakes}

### 反事实建议
{counterfactuals}

### 维度弱项提升
{weak_dims}

### 行动清单
{actions}
"""

ROLE_SKILLS_TEMPLATES = {
    "狼人": """## 间谍决策指导 Skills
""" + _TEMPLATE_BODY,

    "预言家": """## HR总监决策指导 Skills

### 前期(early)策略

#### 发言阶段
{early_speech_actions}
- 前期发言要点：第二天讨论一开始就亮明身份，公布查杀信息

#### 投票阶段
{early_vote_actions}
- 前期投票要点：引导好人票型，集中归票查杀位

#### 技能阶段（背调）
{early_skill_actions}
- 前期技能要点：第一晚背调优先选择发言强势/被争议的玩家

### 中期(mid)策略

#### 发言阶段
{mid_speech_actions}
- 中期发言要点：持续背调未知身份玩家，应对悍跳

#### 投票阶段
{mid_vote_actions}
- 中期投票要点：用具体背调结果引导投票方向

#### 技能阶段
{mid_skill_actions}
- 中期技能要点：持续扩大信息库

### 后期(late)策略

#### 发言阶段
{late_speech_actions}
- 后期发言要点：残局中信息价值最大，明确归票

#### 投票阶段
{late_vote_actions}
- 后期投票要点：验证之前金水/查杀的投票行为是否一致

#### 技能阶段
{late_skill_actions}
- 后期技能要点：残局背调精确归票

### 关键失误规避
{mistakes}

### 反事实建议
{counterfactuals}

### 维度弱项提升
{weak_dims}

### 行动清单
{actions}
""",

    "女巫": """## CEO决策指导 Skills

### 前期(early)策略

#### 发言阶段
{early_speech_actions}
- 前期发言要点：低调观察，不暴露CEO身份

#### 投票阶段
{early_vote_actions}
- 前期投票要点：跟票为主，保留行动空间

#### 技能阶段（留人/辞退）
{early_skill_actions}
- 前期技能要点：首夜优先使用留人offer救关键角色，不要首夜盲毒

### 中期(mid)策略

#### 发言阶段
{mid_speech_actions}
- 中期发言要点：结合背调结果和投票趋势发言引导

#### 投票阶段
{mid_vote_actions}
- 中期投票要点：有查杀配合时果断辞退

#### 技能阶段
{mid_skill_actions}
- 中期技能要点：辞退信使用时机：有查杀配合或票型明确时

### 后期(late)策略

#### 发言阶段
{late_speech_actions}
- 后期发言要点：明确亮明身份辅助归票

#### 投票阶段
{late_vote_actions}
- 后期投票要点：辞退信如未用，残局可果断使用

#### 技能阶段
{late_skill_actions}
- 后期技能要点：残局果断使用辞退信

### 关键失误规避
{mistakes}

### 反事实建议
{counterfactuals}

### 维度弱项提升
{weak_dims}

### 行动清单
{actions}
""",

    "猎人": """## 法务总监决策指导 Skills

### 前期(early)策略

#### 发言阶段
{early_speech_actions}
- 前期发言要点：隐藏身份，建立好人形象，积累公信力

#### 投票阶段
{early_vote_actions}
- 前期投票要点：跟票为主，避免过早暴露

#### 技能阶段（诉讼）
{early_skill_actions}
- 前期技能要点：隐藏身份，不轻易亮明

### 中期(mid)策略

#### 发言阶段
{mid_speech_actions}
- 中期发言要点：如被逼亮明身份，利用诉讼威慑

#### 投票阶段
{mid_vote_actions}
- 中期投票要点：诉讼威慑可阻止间谍投票

#### 技能阶段
{mid_skill_actions}
- 中期技能要点：诉讼目标优先：背调查实 > 票型最可疑 > 发言矛盾

### 后期(late)策略

#### 发言阶段
{late_speech_actions}
- 后期发言要点：残局诉讼是关键武器

#### 投票阶段
{late_vote_actions}
- 后期投票要点：确保带走间谍

#### 技能阶段
{late_skill_actions}
- 后期技能要点：被投出时冷静选择诉讼目标

### 关键失误规避
{mistakes}

### 反事实建议
{counterfactuals}

### 维度弱项提升
{weak_dims}

### 行动清单
{actions}
""",

    "守护者": """## 安保主管决策指导 Skills

### 前期(early)策略

#### 发言阶段
{early_speech_actions}
- 前期发言要点：低调观察，不暴露身份

#### 投票阶段
{early_vote_actions}
- 前期投票要点：跟票为主

#### 技能阶段（加密保护）
{early_skill_actions}
- 前期技能要点：首夜保护HR总监，不要连续两夜保护同一人

### 中期(mid)策略

#### 发言阶段
{mid_speech_actions}
- 中期发言要点：不要过早亮明身份

#### 投票阶段
{mid_vote_actions}
- 中期投票要点：保护信息可用于推断身份

#### 技能阶段
{mid_skill_actions}
- 中期技能要点：在HR总监/CEO/法务总监之间交替保护

### 后期(late)策略

#### 发言阶段
{late_speech_actions}
- 后期发言要点：如已亮明身份，利用保护信息辅助推理

#### 投票阶段
{late_vote_actions}
- 后期投票要点：归票关键目标

#### 技能阶段
{late_skill_actions}
- 后期技能要点：残局保护最关键的神职

### 关键失误规避
{mistakes}

### 反事实建议
{counterfactuals}

### 维度弱项提升
{weak_dims}

### 行动清单
{actions}
""",

    "村民": """## 普通员工决策指导 Skills

### 前期(early)策略

#### 发言阶段
{early_speech_actions}
- 前期发言要点：认真听取发言，记录身份声明和背调结果

#### 投票阶段
{early_vote_actions}
- 前期投票要点：投票前交叉验证信息，不要盲投

#### 技能阶段
{early_skill_actions}
- 前期技能要点：普通员工无夜间技能，专注白天信息收集

### 中期(mid)策略

#### 发言阶段
{mid_speech_actions}
- 中期发言要点：关注投票趋势和发言矛盾

#### 投票阶段
{mid_vote_actions}
- 中期投票要点：优先归票查杀位或票型异常者，避免好人互投

#### 技能阶段
{mid_skill_actions}
- 中期技能要点：无技能，但可利用信息辅助推理

### 后期(late)策略

#### 发言阶段
{late_speech_actions}
- 后期发言要点：残局中基于已有信息做最终判断

#### 投票阶段
{late_vote_actions}
- 后期投票要点：归票方向决定胜负

#### 技能阶段
{late_skill_actions}
- 后期技能要点：无技能，归票判断是核心

### 关键失误规避
{mistakes}

### 反事实建议
{counterfactuals}

### 维度弱项提升
{weak_dims}

### 行动清单
{actions}
""",
}


def get_template(role: str) -> str:
    """获取角色skills模板（role为传统名称：狼人/预言家/女巫/猎人/守护者/村民）"""
    return ROLE_SKILLS_TEMPLATES.get(role, ROLE_SKILLS_TEMPLATES["村民"])

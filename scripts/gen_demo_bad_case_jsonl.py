# -*- coding: utf-8 -*-
"""生成 demo bad case 的 jsonl 文件，供 LLM Judge 使用"""
import json

events = []

# game_init
events.append({
    "event_type": "game_init",
    "player_count": 6,
    "character_role_map": [
        {"character_name": "铁头哥", "role": "狼人", "seat_num": 1, "workplace_title": "商业间谍", "model_name": "qwen-max", "enable_thinking": True},
        {"character_name": "卷王", "role": "预言家", "seat_num": 2, "workplace_title": "HR总监", "model_name": "qwen-max", "enable_thinking": True},
        {"character_name": "PUA总裁", "role": "女巫", "seat_num": 3, "workplace_title": "CEO", "model_name": "qwen-max", "enable_thinking": True},
        {"character_name": "暴躁哥", "role": "猎人", "seat_num": 4, "workplace_title": "法务总监", "model_name": "qwen-max", "enable_thinking": True},
        {"character_name": "老油条", "role": "村民", "seat_num": 5, "workplace_title": "普通员工", "model_name": "qwen-max", "enable_thinking": True},
        {"character_name": "小透明", "role": "村民", "seat_num": 6, "workplace_title": "普通员工", "model_name": "qwen-max", "enable_thinking": True},
    ]
})

# night_start
events.append({"event_type": "night_start", "round": 1})

# 间谍窃取自己（严重失误）
events.append({
    "event_type": "decision",
    "round": 1, "phase": "werewolf",
    "player": "铁头哥", "role": "狼人",
    "action": "间谍窃取", "target": "铁头哥",
    "full_output": {"target": "1号", "kill_strategy": "随便窃取一个，先隐藏自己", "team_coordination": "无"},
    "reasoning_steps": ["第一夜没有信息", "随便选一个"],
    "key_evidence": "随便窃取一个，先隐藏自己"
})

# HR总监背调自己（严重失误）
events.append({
    "event_type": "decision",
    "round": 1, "phase": "seer",
    "player": "卷王", "role": "预言家",
    "action": "HR背调", "target": "卷王",
    "full_output": {"target": "2号", "check_reason": "我想先确认自己是不是好人", "priority_level": 10},
    "reasoning_steps": ["不确定自己的身份", "先查自己"],
    "key_evidence": "我想先确认自己是不是好人"
})

# CEO毒杀好人（严重失误）
events.append({
    "event_type": "decision",
    "round": 1, "phase": "witch",
    "player": "PUA总裁", "role": "女巫",
    "action": "CEO辞退", "target": "老油条",
    "full_output": {"use_antidote": False, "use_poison": True, "target_name": "5号", "action_reason": "感觉他话多"},
    "reasoning_steps": ["5号话多", "先毒了再说"],
    "key_evidence": "感觉他话多"
})

# 猎人盲狙好人（严重失误）
events.append({
    "event_type": "decision",
    "round": 1, "phase": "hunter",
    "player": "暴躁哥", "role": "猎人",
    "action": "法务诉讼", "target": "小透明",
    "full_output": {"shoot": True, "target": "6号", "shoot_reason": "盲狙一下"},
    "reasoning_steps": ["随便带一个"],
    "key_evidence": "盲狙一下"
})

# skill_resolution
events.append({"event_type": "skill_resolution", "round": 1, "skill_type": "spy_steal", "source_player": "铁头哥", "target_player": "铁头哥", "result": "间谍窃取了自己"})
events.append({"event_type": "skill_resolution", "round": 1, "skill_type": "seer_check", "source_player": "卷王", "target_player": "卷王", "result": "背调了自己"})
events.append({"event_type": "skill_resolution", "round": 1, "skill_type": "witch_poison", "source_player": "PUA总裁", "target_player": "老油条", "result": "CEO辞退了5号"})
events.append({"event_type": "skill_resolution", "round": 1, "skill_type": "hunter_shoot", "source_player": "暴躁哥", "target_player": "小透明", "result": "法务诉讼带走了6号"})

# death — 4号被间谍窃取（窃取自己无效所以没人死于窃取），5号被CEO毒死，6号被猎人带走
# 注意：间谍窃取自己=无效，所以4号不该死。实际死亡：5号(CEO辞退) + 6号(法务诉讼触发条件是4号被投出，这里改为4号夜晚被窃取后触发)
# 简化场景：夜晚死亡 5号、6号，4号因为被窃取出局触发诉讼
events.append({"event_type": "death", "round": 1, "player": "老油条", "cause": "CEO辞退"})
events.append({"event_type": "death", "round": 1, "player": "小透明", "cause": "法务诉讼"})

# day_start — 存活玩家：1号(铁头哥)、2号(卷王)、3号(PUA总裁)、4号(暴躁哥)
events.append({"event_type": "day_start", "round": 1})

# 白天发言 — 所有存活玩家都发言
events.append({
    "event_type": "decision",
    "round": 1, "phase": "day",
    "player": "铁头哥", "role": "狼人",
    "action": "公开发言", "target": None,
    "full_output": {"content": "我觉得局势还不明朗，大家先观察观察吧。没什么好说的。"},
    "reasoning_steps": ["保持低调"],
    "key_evidence": "我觉得局势还不明朗，大家先观察观察吧。没什么好说的。"
})

events.append({
    "event_type": "decision",
    "round": 1, "phase": "day",
    "player": "卷王", "role": "预言家",
    "action": "公开发言", "target": None,
    "full_output": {"content": "我是HR总监，昨晚背调了自己...呃...确认自己是好人。我建议大家先不要急着投票，等更多信息。"},
    "reasoning_steps": ["亮明身份", "但背调结果没用"],
    "key_evidence": "我是HR总监，昨晚背调了自己...呃...确认自己是好人。"
})

events.append({
    "event_type": "decision",
    "round": 1, "phase": "day",
    "player": "PUA总裁", "role": "女巫",
    "action": "公开发言", "target": None,
    "full_output": {"content": "昨晚情况比较复杂，我只能说我做了该做的事。大家自己判断吧，我的建议是先投沉默的人。"},
    "reasoning_steps": ["不暴露自己用了毒药", "模糊带过"],
    "key_evidence": "昨晚情况比较复杂，我只能说我做了该做的事。"
})

events.append({
    "event_type": "decision",
    "round": 1, "phase": "day",
    "player": "暴躁哥", "role": "猎人",
    "action": "公开发言", "target": None,
    "full_output": {"content": "我不想多说废话。5号6号都走了，剩下的人里肯定有间谍。我盯着1号，他从刚才就一直在装傻。"},
    "reasoning_steps": ["直觉判断", "1号太低调了"],
    "key_evidence": "我盯着1号，他从刚才就一直在装傻。"
})

# 投票 — 所有存活玩家都投票
events.append({
    "event_type": "decision",
    "round": 1, "phase": "vote",
    "player": "铁头哥", "role": "狼人",
    "action": "投票", "target": "卷王",
    "full_output": {"vote": "2号", "reason": "HR总监背调自己太可疑了", "suspicion_level": 6},
    "reasoning_steps": ["HR总监背调自己", "可以借此投他"],
    "key_evidence": "HR总监背调自己太可疑了"
})

events.append({
    "event_type": "decision",
    "round": 1, "phase": "vote",
    "player": "卷王", "role": "预言家",
    "action": "投票", "target": "PUA总裁",
    "full_output": {"vote": "3号", "reason": "没有证据，感觉像间谍", "suspicion_level": 5},
    "reasoning_steps": ["没有信息", "随便投"],
    "key_evidence": "没有证据，感觉像间谍"
})

events.append({
    "event_type": "decision",
    "round": 1, "phase": "vote",
    "player": "PUA总裁", "role": "女巫",
    "action": "投票", "target": "卷王",
    "full_output": {"vote": "2号", "reason": "背调自己浪费信息，对公司没有贡献", "suspicion_level": 4},
    "reasoning_steps": ["2号背调自己确实可疑", "跟着1号投"],
    "key_evidence": "背调自己浪费信息，对公司没有贡献"
})

events.append({
    "event_type": "decision",
    "round": 1, "phase": "vote",
    "player": "暴躁哥", "role": "猎人",
    "action": "投票", "target": "铁头哥",
    "full_output": {"vote": "1号", "reason": "1号全程装傻划水，不像好人该有的态度", "suspicion_level": 7},
    "reasoning_steps": ["1号太沉默", "好人不该这样"],
    "key_evidence": "1号全程装傻划水，不像好人该有的态度"
})

# vote_result — 2号以2票被投出
events.append({
    "event_type": "vote_result",
    "round": 1,
    "voted_out": "卷王",
    "vote_count": 2,
})

# game_over
events.append({
    "event_type": "game_over",
    "winner": "间谍阵营胜利！好人数量不足。",
    "round": 1
})

# 写入文件
output_path = __import__("pathlib").Path(__file__).resolve().parent.parent / "exports" / "demo_bad_case.jsonl"
with open(output_path, "w", encoding="utf-8") as f:
    for event in events:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

print(f"写入 {len(events)} 个事件到 {output_path}")

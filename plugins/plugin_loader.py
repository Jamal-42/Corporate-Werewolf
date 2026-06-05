# -*- coding: utf-8 -*-
"""可扩展架构 - 插件manifest格式与动态角色注册
插件通过JSON manifest描述角色、技能和Prompt，
无需修改核心代码即可添加新角色。
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from game_roles import GameRoles

_log = logging.getLogger("werewolf.diag.plugins")


def load_manifest(manifest_path: str) -> Dict[str, Any]:
    """加载插件manifest文件"""
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest文件不存在: {manifest_path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def register_plugin(manifest: Dict[str, Any]) -> None:
    """根据manifest动态注册角色到GameRoles"""
    role_name = manifest["role_name"]
    GameRoles.ROLES[role_name] = {
        "description": manifest["description"],
        "ability": manifest["ability"],
        "win_condition": manifest.get("win_condition", "揪出所有间谍，完成组织净化"),
        "team": manifest.get("team", "公司阵营"),
    }

    # 注册角色对应的技能（如果manifest中指定了skill_class）
    skill_info = manifest.get("skill", {})
    if skill_info:
        from skills.registry import get_global_registry
        skill_class_path = skill_info.get("class_path")
        if skill_class_path:
            # 动态导入技能类
            module_path, class_name = skill_class_path.rsplit(".", 1)
            import importlib
            module = importlib.import_module(module_path)
            skill_class = getattr(module, class_name)
            registry = get_global_registry()
            registry.register(role_name, skill_class())


def load_all_plugins(plugins_dir: str = "plugins") -> List[str]:
    """加载plugins目录下所有manifest"""
    registered = []
    plugins_path = Path(plugins_dir)
    if not plugins_path.exists():
        return registered

    for manifest_file in plugins_path.glob("*.json"):
        try:
            manifest = load_manifest(str(manifest_file))
            register_plugin(manifest)
            registered.append(manifest["role_name"])
        except Exception as e:
            _log.error(f"插件加载失败({manifest_file}): {e}")

    return registered
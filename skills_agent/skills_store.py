# -*- coding: utf-8 -*-
"""Skills版本化存储

存储路径: skills/versions/{version}/{role}.md
角色名使用职场术语: 间谍.md, HR总监.md, CEO.md ...
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

_log = logging.getLogger("werewolf.diag.skills")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills" / "versions"

ROLE_WORKPLACE = {
    "狼人": "间谍", "预言家": "HR总监", "女巫": "CEO",
    "猎人": "法务总监", "守护者": "安保主管", "村民": "普通员工",
}
WORKPLACE_ROLE = {v: k for k, v in ROLE_WORKPLACE.items()}

ALL_ROLES = list(ROLE_WORKPLACE.values())


class SkillsStore:
    """版本化Skills存储"""

    def __init__(self, base_dir: Path = SKILLS_DIR):
        self.base_dir = base_dir

    def save(self, version: str, role: str, content: str, filename: str = None) -> Path:
        """写入某版本某角色的skills文件

        Args:
            filename: 子文件名（如"间谍.early.speech.md"），为None时使用默认"{role}.md"
        """
        role = ROLE_WORKPLACE.get(role, role)
        version_dir = self.base_dir / version
        version_dir.mkdir(parents=True, exist_ok=True)
        if filename:
            path = version_dir / filename
        else:
            path = version_dir / f"{role}.md"
        path.write_text(content, encoding="utf-8")
        _log.info(f"Saved skills: {version}/{path.name}")
        return path

    def save_meta(self, version: str, meta: Dict) -> None:
        """写入版本元数据"""
        version_dir = self.base_dir / version
        version_dir.mkdir(parents=True, exist_ok=True)
        meta_path = version_dir / "meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, version: str, role: str, filename: str = None) -> Optional[str]:
        """加载某版本某角色的skills，返回None如果不存在

        Args:
            filename: 子文件名（如"间谍.early.speech.md"），为None时使用默认"{role}.md"
        """
        role = ROLE_WORKPLACE.get(role, role)
        if filename:
            path = self.base_dir / version / filename
        else:
            path = self.base_dir / version / f"{role}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def load_meta(self, version: str) -> Optional[Dict]:
        """加载版本元数据"""
        meta_path = self.base_dir / version / "meta.json"
        if meta_path.exists():
            return json.loads(meta_path.read_text(encoding="utf-8"))
        return None

    def list_versions(self) -> List[str]:
        """列出所有版本，按创建时间排序"""
        if not self.base_dir.exists():
            return []
        versions = []
        for d in self.base_dir.iterdir():
            if d.is_dir() and (d / "meta.json").exists():
                versions.append(d.name)
        return sorted(versions)

    def list_skills_in_version(self, version: str) -> Dict[str, str]:
        """列出某版本下所有角色的skills"""
        version_dir = self.base_dir / version
        if not version_dir.exists():
            return {}
        result = {}
        for f in version_dir.glob("*.md"):
            role = f.stem
            result[role] = f.read_text(encoding="utf-8")
        return result

    def delete_version(self, version: str) -> bool:
        """删除某版本"""
        import shutil
        version_dir = self.base_dir / version
        if version_dir.exists():
            shutil.rmtree(version_dir)
            _log.info(f"Deleted skills version: {version}")
            return True
        return False

    def get_next_version(self, prefix: str = "evo") -> str:
        """获取下一个版本号"""
        existing = self.list_versions()
        max_num = 0
        for v in existing:
            if v.startswith(prefix + "_"):
                try:
                    num = int(v.split("_")[1])
                    max_num = max(max_num, num)
                except (IndexError, ValueError):
                    pass
        return f"{prefix}_{max_num + 1}"

"""寻找伴随 .pxls.bytes 的 texture_N.png 贴图。

游戏里 PXLS 以"图集外置"方式导出，贴图文件名由导出器决定。不同工具
（AssetStudio / 游戏原生加载器 / 各种 mod 工具）命名五花八门，这里按
常见命名依次尝试。
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["texture_candidates", "find_texture"]


def _strip_pxls_suffix(name: str) -> str:
    """noel.pxls.bytes -> noel；兼容大小写。"""

    lower = name.lower()
    for suffix in (".pxls.bytes", ".pxls"):
        if lower.endswith(suffix):
            return name[: -len(suffix)]
    return os.path.splitext(name)[0]


def texture_candidates(pxls_path, index: int) -> list[Path]:
    """返回第 index 个图集可能使用的贴图路径（按命中优先级排序）。"""

    path = Path(pxls_path)
    directory = path.parent
    base = _strip_pxls_suffix(path.name)
    names = [
        # 本仓库 README 里的原生提取命名
        f"{path.name}.texture_{index}.png",
        # AssetStudio 常见命名
        f"Texture_{base}.pxls.texture_{index}.png",
        f"{base}.pxls.texture_{index}.png",
        f"{base}.texture_{index}.png",
        f"{base}_{index}.png",
        f"Texture_TextAsset_{base}.pxls.texture_{index}.png",
    ]
    seen: set[str] = set()
    result: list[Path] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        result.append(directory / name)
    return result


def find_texture(pxls_path, index: int) -> Path | None:
    """返回第一个真实存在的贴图候选路径。"""

    candidates = texture_candidates(pxls_path, index)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # 兜底：大小写不敏感地扫一遍目录（有些导出工具会改大小写）
    directory = Path(pxls_path).parent
    wanted = {c.name.lower() for c in candidates}
    if directory.is_dir():
        for entry in directory.iterdir():
            if entry.is_file() and entry.name.lower() in wanted:
                return entry
    return None

"""AICPxlsUnpacker 的 PXLS/PXL 容器工具。

- aicpxls.pxls     解析 / 改写 PixelLiner 的 PXLS 容器（游戏导出格式）
- aicpxls.textures 按索引寻找伴随的 texture_N.png 贴图
- aicpxls.rebuild  把 .pxls.bytes 重建为 PixelLiner 可打开的 .pxl

为什么需要重建？见 README 的"从 pxls 重建 pxl"一节。
"""

from .pxls import (
    ContainerError,
    Section,
    parse_container,
    write_container,
    rewrite_pack_section,
    rewrite_container,
    PACK_SECTION,
    POSE_SECTION,
)
from .textures import find_texture
from .rebuild import rebuild_pxl, verify_pxl, RebuildReport

__all__ = [
    "ContainerError",
    "Section",
    "parse_container",
    "write_container",
    "rewrite_pack_section",
    "rewrite_container",
    "PACK_SECTION",
    "POSE_SECTION",
    "find_texture",
    "rebuild_pxl",
    "verify_pxl",
    "RebuildReport",
]

"""把游戏导出的 .pxls.bytes（+ texture_N.png）重建为 PixelLiner 可打开的 .pxl。

原理
----
游戏里的 .pxls.bytes 是 PixelLiner 的 "PXLS 容器"：%PACK_SECTION% 里的图集
记录带"贴图外置"标志位，PNG 被单独导出成 texture_N.png。PixelLiner 的
打开对话框认 .pxl/.pxls/.pxls.bytes 三种扩展名，并按文件头分派：

* 文本头 "konnna_syarinn..." -> 工程格式 .pxl
* u32 0x7741A8FF + "PXLS"   -> 游戏导出格式（%PACK_SECTION%）

只要把外置贴图内嵌回 %PACK_SECTION%，这个 PXLS 文件就能被 PixelLiner
直接打开，随后它会自动转换成可编辑角色，另存即可得到工程 .pxl。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from .pxls import (
    PACK_SECTION,
    POSE_SECTION,
    rewrite_container,
    rewrite_pack_section,
    parse_container,
)
from .textures import find_texture, texture_candidates

__all__ = ["RebuildReport", "rebuild_pxl", "verify_pxl", "output_name"]


@dataclass
class RebuildReport:
    """一次重建的结果摘要。"""

    source: Path
    output: Path
    atlas_count: int = 0
    external_atlases: int = 0
    embedded_atlases: int = 0
    textures_used: list[Path] = field(default_factory=list)
    pose_count: int | None = None
    sections: list[str] = field(default_factory=list)
    already_embedded: bool = False
    written_bytes: int = 0
    size_mismatches: list[str] = field(default_factory=list)


def _load_external_png(pxls_path: Path, index: int, report: RebuildReport) -> bytes:
    texture = find_texture(pxls_path, index)
    if texture is None:
        searched = "\n    ".join(str(p) for p in texture_candidates(pxls_path, index))
        raise FileNotFoundError(
            f"第 {index} 个图集的贴图缺失，已尝试：\n    {searched}\n"
            "请把对应的 texture_N.png 放到同目录（命名可参考以上候选）。"
        )
    report.textures_used.append(texture)
    return texture.read_bytes()


def output_name(source: Path) -> str:
    name = source.name
    if name.lower().endswith(".pxls.bytes"):
        base = name[: -len(".pxls.bytes")]
    elif name.lower().endswith(".pxls"):
        base = name[: -len(".pxls")]
    else:
        base = source.stem
    return base + ".pxl"


def rebuild_pxl(pxls_path, output_path=None) -> RebuildReport:
    """重建单个 .pxls.bytes 为 .pxl。

    pxls_path: 输入文件
    output_path: 输出 .pxl；默认与输入同目录、同名换后缀
    """

    source = Path(pxls_path)
    output = Path(output_path) if output_path is not None else source.with_name(output_name(source))

    data = source.read_bytes()
    sections = parse_container(data)
    report = RebuildReport(source=source, output=output, sections=[s.name for s in sections])

    def provider(index: int) -> bytes:
        return _load_external_png(source, index, report)

    new_data, stats = rewrite_container(data, provider)
    report.atlas_count = stats.atlas_count
    report.external_atlases = stats.external_count
    report.embedded_atlases = stats.embedded_count
    report.already_embedded = stats.external_count == 0
    for record in stats.records:
        if record.external and record.declared_size and record.png_size and record.declared_size != record.png_size:
            report.size_mismatches.append(
                f"atlas[{record.index}] 声明 {record.declared_size}，PNG 实际 {record.png_size}"
            )

    pose = next((s for s in sections if s.name == POSE_SECTION), None)
    if pose is not None and len(pose.payload) >= 4:
        report.pose_count = struct.unpack(">I", pose.payload[:4])[0]

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(new_data)
    report.written_bytes = len(new_data)
    return report


def verify_pxl(pxl_path) -> dict:
    """重新解析产出的 .pxl，做一次结构自校验（不依赖 PixelLiner）。

    返回 section 名列表、图集记录、pose 数等；结构不合法时抛异常。
    """

    path = Path(pxl_path)
    data = path.read_bytes()
    sections = parse_container(data)
    info: dict = {"sections": [s.name for s in sections]}
    for section in sections:
        if section.name == PACK_SECTION:

            def _should_not_be_called(index: int) -> bytes:
                raise AssertionError(f"记录 {index} 仍是外置贴图，未完成内嵌")

            _, stats = rewrite_pack_section(section.payload, _should_not_be_called)
            info["atlas_count"] = stats.atlas_count
            info["external_atlases"] = stats.external_count
            info["embedded_atlases"] = stats.embedded_count
        elif section.name == POSE_SECTION and len(section.payload) >= 4:
            info["pose_count"] = struct.unpack(">I", section.payload[:4])[0]
    return info
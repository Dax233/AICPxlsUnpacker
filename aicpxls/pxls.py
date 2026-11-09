"""PixelLiner PXLS 容器（游戏导出格式）的解析与改写。

格式来源：PixelLiner 0.97.14 (Adobe AIR) 反编译源码
jp/clobau/pixelliner/pxls/PxlCharacter.as 与 PxlsImgAtlas.as；
另有 e9ae9933/pixelliner4j 的 Java 只读实现可对照。

容器结构（全部大端）::

    u32  magic = 0x7741A8FF
    char[4] "PXLS"
    repeat {
        char[14] section_name        # 如 "%PACK_SECTION%"
        u32 payload_length
        u8  payload[payload_length]
    }

本模块只做"容器级"改写，不解析 pose/layer 语义：
把 %PACK_SECTION% 里"贴图在外部 png"的图集记录改写成"png 内嵌"，
这样文件就变成 PixelLiner 可以直接打开的形态。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = 0x7741A8FF
TAG = b"PXLS"
SECTION_NAME_LEN = 14

PACK_SECTION = "%PACK_SECTION%"
IMGS_SECTION = "%IMGS_SECTION%"
IMGD_SECTION = "%IMGD_SECTION%"
IMGV_SECTION = "%IMGV_SECTION%"
POSE_SECTION = "%POSE_SECTION%"
PTCL_SECTION = "%PTCL_SECTION%"

KNOWN_SECTIONS = frozenset(
    {
        PACK_SECTION,
        IMGS_SECTION,
        IMGD_SECTION,
        IMGV_SECTION,
        POSE_SECTION,
        PTCL_SECTION,
    }
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# PxlsImgAtlas.IMG_TYPE_NORMAL / IMG_TYPE_PARTS 的编码偏移
_IMG_TYPE_ADD = 22


class ContainerError(ValueError):
    """PXLS 容器结构不合法。"""


@dataclass
class Section:
    """容器里的一个 section，payload 保持原始字节。"""

    name: str
    payload: bytes


@dataclass
class AtlasRecord:
    """%PACK_SECTION% 中的一条图集记录。"""

    index: int
    img_type: int
    external: bool
    margin: int
    uv_count: int
    declared_size: tuple[int, int] | None = None
    png_size: tuple[int, int] | None = None


@dataclass
class PackStats:
    """%PACK_SECTION% 改写统计，便于 CLI 汇报。"""

    atlas_count: int = 0
    external_count: int = 0
    embedded_count: int = 0
    records: list[AtlasRecord] = field(default_factory=list)


class _Reader:
    """极简大端读取器，越界时给出人话错误。"""

    def __init__(self, data: bytes, name: str = "buffer") -> None:
        self._data = data
        self._pos = 0
        self._name = name

    @property
    def remaining(self) -> int:
        return len(self._data) - self._pos

    def take(self, size: int) -> bytes:
        if size < 0:
            raise ContainerError(f"{self._name}: 请求了负数长度 {size}")
        end = self._pos + size
        if end > len(self._data):
            raise ContainerError(
                f"{self._name}: 数据不够，需 {size} 字节，仅剩 {self.remaining} 字节"
                f"（偏移 {self._pos}）"
            )
        chunk = self._data[self._pos:end]
        self._pos = end
        return chunk

    def u8(self) -> int:
        return self.take(1)[0]

    def u32(self) -> int:
        return struct.unpack(">I", self.take(4))[0]


def parse_container(data: bytes) -> list[Section]:
    """把 PXLS 字节流解析成 section 列表（payload 原样保留）。"""

    if len(data) < 8:
        raise ContainerError(f"文件太短（{len(data)} 字节），不是 PXLS 容器")
    magic = struct.unpack(">I", data[:4])[0]
    if magic != MAGIC:
        raise ContainerError(
            f"文件头不匹配：magic=0x{magic:08X}，期望 0x{MAGIC:08X}"
            "（工程格式 .pxl 是另一套文本头，不走这里）"
        )
    if data[4:8] != TAG:
        raise ContainerError(f"文件头不匹配：tag={data[4:8]!r}，期望 b'PXLS'")

    sections: list[Section] = []
    pos = 8
    while pos < len(data):
        if len(data) - pos < SECTION_NAME_LEN:
            raise ContainerError(
                f"文件末尾残留 {len(data) - pos} 字节，不足一个 section 名（14 字节）"
            )
        raw_name = data[pos:pos + SECTION_NAME_LEN]
        pos += SECTION_NAME_LEN
        try:
            name = raw_name.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ContainerError(f"section 名不是 ASCII：{raw_name!r}") from exc
        if name not in KNOWN_SECTIONS:
            raise ContainerError(f"未知 section 名 {name!r}（偏移 {pos - SECTION_NAME_LEN}）")
        if len(data) - pos < 4:
            raise ContainerError(f"section {name} 缺少长度字段")
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        if len(data) - pos < length:
            raise ContainerError(
                f"section {name} 声明长度 {length}，实际只剩 {len(data) - pos} 字节"
            )
        sections.append(Section(name, data[pos:pos + length]))
        pos += length
    if not sections:
        raise ContainerError("容器里一个 section 都没有")
    return sections


def write_container(sections) -> bytes:
    """把 section 列表写回 PXLS 字节流。"""

    chunks = [struct.pack(">I", MAGIC), TAG]
    for section in sections:
        encoded = section.name.encode("ascii")
        if len(encoded) != SECTION_NAME_LEN:
            raise ContainerError(f"section 名长度必须是 14：{section.name!r}")
        chunks.append(encoded)
        chunks.append(struct.pack(">I", len(section.payload)))
        chunks.append(section.payload)
    return b"".join(chunks)


def _png_size(png: bytes) -> tuple[int, int]:
    """读取 PNG 的宽高（IHDR 固定位置，不依赖第三方库）。"""

    if len(png) < 24 or not png.startswith(PNG_SIGNATURE):
        raise ContainerError("不是合法的 PNG 数据（签名或长度不对）")
    width, height = struct.unpack(">II", png[16:24])
    return width, height


def rewrite_pack_section(payload: bytes, png_provider):
    """把 %PACK_SECTION% 的 payload 改写成"全部内嵌 PNG"的版本。

    png_provider: callable(index) -> bytes，返回第 index 个图集对应的外部
    PNG 内容。只有遇到 external 记录时才会调用。
    """

    reader = _Reader(payload, "%PACK_SECTION%")
    writer = bytearray()
    atlas_count = reader.u32()
    writer += struct.pack(">I", atlas_count)
    stats = PackStats(atlas_count=atlas_count)
    for index in range(atlas_count):
        raw_type = reader.u8()
        writer.append(raw_type)
        img_type = raw_type - _IMG_TYPE_ADD
        if img_type < 0:
            # 与 PixelLiner 语义一致：负 type 表示"空记录"，后面没有字段
            continue
        vers = reader.u8()
        margin = reader.u8()
        uv_count = reader.u32()
        uv_blob = reader.take(uv_count * 28)  # key(u32) + id2(f64) + x/y/w/h(4*u32)
        external = bool(vers & 0x01)
        record = AtlasRecord(index, img_type, external, margin, uv_count)
        if external:
            declared = struct.unpack(">II", reader.take(8))
            png = png_provider(index)
            png_w, png_h = _png_size(png)
            record.declared_size = declared
            record.png_size = (png_w, png_h)
            stats.records.append(record)
            stats.external_count += 1
            writer.append(vers & ~0x01)  # 清掉"外部 PNG"标志位，其余未知位保留
            writer.append(margin)
            writer += struct.pack(">I", uv_count)
            writer += uv_blob
            writer += struct.pack(">I", len(png))
            writer += png
        else:
            png_len = reader.u32()
            png = reader.take(png_len)
            stats.records.append(record)
            stats.embedded_count += 1
            writer.append(vers)
            writer.append(margin)
            writer += struct.pack(">I", uv_count)
            writer += uv_blob
            writer += struct.pack(">I", png_len)
            writer += png
    if reader.remaining:
        raise ContainerError(
            f"%PACK_SECTION% 解析后残留 {reader.remaining} 字节，格式可能不兼容"
        )
    return bytes(writer), stats


def rewrite_container(data: bytes, png_provider):
    """整个容器级改写：仅替换 %PACK_SECTION%，其它 section 原样复制。"""

    sections = parse_container(data)
    stats = PackStats()
    rewritten: list[Section] = []
    for section in sections:
        if section.name == PACK_SECTION:
            payload, stats = rewrite_pack_section(section.payload, png_provider)
            rewritten.append(Section(section.name, payload))
        else:
            rewritten.append(section)
    return write_container(rewritten), stats

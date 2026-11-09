"""aicpxls 的单元测试（纯标准库，不需要真实游戏资产）。

测试夹具自己构造最小 PXLS 容器：一个 %PACK_SECTION% + 一个空 %POSE_SECTION%
足够覆盖"容器解析 / 外部贴图内嵌 / 字节级往返"这些逻辑。
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from aicpxls.pxls import (  # noqa: E402
    ContainerError,
    PACK_SECTION,
    POSE_SECTION,
    Section,
    parse_container,
    rewrite_pack_section,
    write_container,
)
from aicpxls.rebuild import rebuild_pxl, verify_pxl  # noqa: E402
from aicpxls.textures import texture_candidates  # noqa: E402

MAGIC = 0x7741A8FF


def make_png(width: int, height: int, rgba=(255, 0, 0, 255)) -> bytes:
    """生成一个最小合法 PNG（不依赖 Pillow）。"""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(rgba) * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def pack_payload(records) -> bytes:
    """records: [(img_type, png_bytes, uv_count)]，全部内嵌。"""

    out = bytearray(struct.pack(">I", len(records)))
    for index, (img_type, png, uv_count) in enumerate(records):
        out.append(22 + img_type)
        out.append(0)  # vers: 内嵌
        out.append(1)  # margin
        out += struct.pack(">I", uv_count)
        for i in range(uv_count):
            out += struct.pack(">I", 1000 + i)  # key id
            out += struct.pack(">d", 2000.0 + i)  # key id2
            out += struct.pack(">IIII", i * 4, 0, 4, 4)  # x y w h
        out += struct.pack(">I", len(png)) + png
    return bytes(out)


def container_bytes(records) -> bytes:
    sections = [
        Section(PACK_SECTION, pack_payload(records)),
        Section(POSE_SECTION, struct.pack(">I", 0)),
    ]
    return write_container(sections)


def to_external(data: bytes) -> tuple[bytes, list[bytes]]:
    """把内嵌图集的容器改写成"外置贴图"版本，返回 (容器, png 列表)。"""

    sections = parse_container(data)
    pngs: list[bytes] = []
    rewritten = []
    for section in sections:
        if section.name != PACK_SECTION:
            rewritten.append(section)
            continue
        payload = section.payload
        pos = 4
        count = struct.unpack(">I", payload[:4])[0]
        out = bytearray(payload[:4])
        for index in range(count):
            raw_type = payload[pos]
            pos += 1
            out.append(raw_type)
            if raw_type - 22 < 0:
                continue
            pos += 1  # vers
            margin = payload[pos]
            pos += 1
            uv_count = struct.unpack(">I", payload[pos:pos + 4])[0]
            pos += 4
            uv_blob = payload[pos:pos + uv_count * 28]
            pos += uv_count * 28
            png_len = struct.unpack(">I", payload[pos:pos + 4])[0]
            pos += 4
            png = payload[pos:pos + png_len]
            pos += png_len
            pngs.append(png)
            width, height = struct.unpack(">II", png[16:24])
            out.append(1)  # vers: 外部 PNG
            out.append(margin)
            out += struct.pack(">I", uv_count)
            out += uv_blob
            out += struct.pack(">II", width, height)
        rewritten.append(Section(PACK_SECTION, bytes(out)))
    return write_container(rewritten), pngs


class ParseTests(unittest.TestCase):
    def test_roundtrip_container(self) -> None:
        data = container_bytes([(0, make_png(4, 4), 2)])
        sections = parse_container(data)
        self.assertEqual([s.name for s in sections], [PACK_SECTION, POSE_SECTION])
        self.assertEqual(write_container(sections), data)

    def test_bad_magic(self) -> None:
        with self.assertRaises(ContainerError):
            parse_container(b"\x00" * 16)

    def test_truncated(self) -> None:
        data = container_bytes([(0, make_png(2, 2), 1)])
        with self.assertRaises(ContainerError):
            parse_container(data[:-5])

    def test_unknown_section(self) -> None:
        data = struct.pack(">I", MAGIC) + b"PXLS" + b"%NOPE_SECTION%" + struct.pack(">I", 0)
        with self.assertRaises(ContainerError):
            parse_container(data)


class RebuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_inputs(self, data: bytes, pngs: list[bytes]) -> Path:
        pxls_path = self.dir / "noel.pxls.bytes"
        pxls_path.write_bytes(data)
        for index, png in enumerate(pngs):
            (self.dir / f"noel.pxls.bytes.texture_{index}.png").write_bytes(png)
        return pxls_path

    def test_embedded_passthrough(self) -> None:
        original = container_bytes([(0, make_png(8, 8), 3)])
        pxls_path = self._write_inputs(original, [])
        report = rebuild_pxl(pxls_path)
        self.assertTrue(report.already_embedded)
        self.assertEqual(Path(report.output).read_bytes(), original)
        self.assertEqual(verify_pxl(report.output)["external_atlases"], 0)

    def test_external_to_embedded_roundtrip(self) -> None:
        embedded = container_bytes([(0, make_png(64, 32), 5)])
        external, pngs = to_external(embedded)
        pxls_path = self._write_inputs(external, pngs)
        report = rebuild_pxl(pxls_path)
        self.assertEqual(report.external_atlases, 1)
        self.assertEqual(report.embedded_atlases, 0)
        self.assertEqual(Path(report.output).read_bytes(), embedded)

    def test_multi_atlas_with_parts(self) -> None:
        embedded = container_bytes(
            [(0, make_png(32, 16), 4), (1, make_png(32, 16), 4)]
        )
        external, pngs = to_external(embedded)
        pxls_path = self._write_inputs(external, pngs)
        report = rebuild_pxl(pxls_path)
        self.assertEqual(report.atlas_count, 2)
        self.assertEqual(report.external_atlases, 2)
        self.assertEqual(Path(report.output).read_bytes(), embedded)

    def test_missing_texture(self) -> None:
        embedded = container_bytes([(0, make_png(4, 4), 1)])
        external, _ = to_external(embedded)
        pxls_path = self.dir / "broken.pxls.bytes"
        pxls_path.write_bytes(external)
        with self.assertRaises(FileNotFoundError):
            rebuild_pxl(pxls_path)

    def test_verify_detects_external(self) -> None:
        embedded = container_bytes([(0, make_png(4, 4), 1)])
        external, _ = to_external(embedded)
        path = self.dir / "still_external.pxls"
        path.write_bytes(external)
        with self.assertRaises(AssertionError):
            verify_pxl(path)

    def test_texture_candidates(self) -> None:
        names = [p.name for p in texture_candidates(self.dir / "noel.pxls.bytes", 1)]
        self.assertEqual(names[0], "noel.pxls.bytes.texture_1.png")
        self.assertIn("noel.pxls.texture_1.png", names)


class RewritePackTests(unittest.TestCase):
    def test_provider_only_called_for_external(self) -> None:
        payload = pack_payload([(0, make_png(4, 4), 1)])

        def provider(index: int) -> bytes:  # pragma: no cover
            raise AssertionError("内嵌记录不应请求外部贴图")

        rewritten, stats = rewrite_pack_section(payload, provider)
        self.assertEqual(rewritten, payload)
        self.assertEqual(stats.external_count, 0)
        self.assertEqual(stats.embedded_count, 1)


if __name__ == "__main__":
    unittest.main()

"""可选的"真实资产"往返测试。

仓库不便附带游戏资产，所以这个测试默认跳过。要启用，把一个真实
.pxls.bytes（内嵌图集版本即可）路径放进环境变量：

    AICPXLS_REAL_SAMPLE=/path/to/noel_blue.pxls.bytes \
        python -m unittest tests.test_real_sample -v

测试内容：把内嵌图集改写成"外置贴图"变体（模拟游戏导出/AIC 解包后的
形态），再用 rebuild_pxl 重建，要求输出与原内嵌文件逐字节一致。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from aicpxls.pxls import PACK_SECTION, Section, parse_container, write_container  # noqa: E402
from aicpxls.rebuild import rebuild_pxl  # noqa: E402

SAMPLE_ENV = "AICPXLS_REAL_SAMPLE"


def to_external(data: bytes):
    """把内嵌图集改写为外部贴图版；返回 (容器字节, [png...])。"""

    import struct

    pngs: list[bytes] = []
    rewritten = []
    for section in parse_container(data):
        if section.name != PACK_SECTION:
            rewritten.append(section)
            continue
        payload = section.payload
        pos = 4
        count = struct.unpack(">I", payload[:4])[0]
        out = bytearray(payload[:4])
        for _ in range(count):
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


@unittest.skipUnless(os.environ.get(SAMPLE_ENV), f"需要设置 {SAMPLE_ENV} 指向真实 .pxls.bytes")
class RealSampleTests(unittest.TestCase):
    def test_external_roundtrip_byte_exact(self) -> None:
        sample = Path(os.environ[SAMPLE_ENV])
        original = sample.read_bytes()
        external, pngs = to_external(original)

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            pxls_path = tmpdir / "sample.pxls.bytes"
            pxls_path.write_bytes(external)
            for index, png in enumerate(pngs):
                (tmpdir / f"sample.pxls.bytes.texture_{index}.png").write_bytes(png)

            report = rebuild_pxl(pxls_path)
            self.assertGreater(report.external_atlases, 0)
            self.assertEqual(Path(report.output).read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

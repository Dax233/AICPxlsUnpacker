#!/usr/bin/env python3
"""从游戏导出的 .pxls.bytes + texture_N.png 重建 PixelLiner 可打开的 .pxl。

用法::

    python reconstruct_pxl.py                  # 处理 ./files, 输出到 ./unpack
    python reconstruct_pxl.py my_files -o out  # 指定目录
    python reconstruct_pxl.py --verify         # 产出后再做一次结构自校验

为什么这样做能"还原"出可编辑的 .pxl？见 aicpxls/rebuild.py 的模块说明。
一句话：PixelLiner 打开对话框同时认识工程格式和游戏导出格式，只要把
外置贴图内嵌回 %PACK_SECTION%，它就能直接打开并转成可编辑角色。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aicpxls import rebuild_pxl, verify_pxl
from aicpxls.rebuild import output_name

SUCCESS = "\033[0;32m[+]\033[0m"
ERROR = "\033[0;31m[x]\033[0m"
WARNING = "\033[0;33m[!]\033[0m"
DONE = "\033[0;36m[>]\033[0m"


def iter_inputs(directory: Path, recursive: bool) -> list[Path]:
    patterns = ("*.pxls.bytes", "*.pxls.bytes".upper(), "*.pxls")
    found: dict[Path, None] = {}
    for pattern in patterns:
        iterator = directory.rglob(pattern) if recursive else directory.glob(pattern)
        for path in iterator:
            if path.is_file() and path.name.lower().endswith((".pxls.bytes", ".pxls")):
                found[path] = None
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="把 .pxls.bytes + texture_N.png 重建为 PixelLiner 可打开的 .pxl",
    )
    parser.add_argument("input", nargs="?", default="files", help="输入目录（默认 files）")
    parser.add_argument("-o", "--output", default="unpack", help="输出目录（默认 unpack）")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归搜索子目录")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的 .pxl")
    parser.add_argument("--verify", action="store_true", help="产出后做结构自校验")
    parser.add_argument("--file", action="append", default=[], help="只处理指定文件（可重复）")
    args = parser.parse_args(argv)

    if args.file:
        inputs = [Path(f) for f in args.file]
    else:
        directory = Path(args.input)
        if not directory.is_dir():
            print(f"{ERROR} 输入目录不存在：{directory}")
            return 2
        inputs = iter_inputs(directory, args.recursive)

    if not inputs:
        print(f"{WARNING} 没有找到 *.pxls.bytes 文件（目录：{args.input}）")
        return 1

    output_dir = Path(args.output)
    ok = 0
    failed = 0
    skipped = 0
    for source in inputs:
        target = output_dir / output_name(source)
        if target.exists() and not args.overwrite:
            print(f"{WARNING} 已存在，跳过：{target}（加 --overwrite 覆盖）")
            skipped += 1
            continue
        try:
            report = rebuild_pxl(source, target)
        except Exception as exc:  # noqa: BLE001 - CLI 要一次性报告所有失败
            print(f"{ERROR} {source.name}: {exc}")
            failed += 1
            continue

        detail = f"图集 {report.atlas_count}（外置 {report.external_atlases} -> 内嵌 {report.embedded_atlases}）"
        if report.pose_count is not None:
            detail += f"，pose {report.pose_count}"
        print(f"{SUCCESS} {source.name} -> {target}  [{detail}]")
        for message in report.size_mismatches:
            print(f"  {WARNING} {message}")
        if report.already_embedded:
            print(f"  {DONE} 本来就是内嵌图集，产出等同原文件（可直接给 PixelLiner 打开）")

        if args.verify:
            try:
                info = verify_pxl(target)
                print(f"  {DONE} 自校验通过：{info}")
            except Exception as exc:  # noqa: BLE001
                print(f"  {ERROR} 自校验失败：{exc}")
                failed += 1
                continue
        ok += 1

    print()
    print(f"{DONE} 完成：成功 {ok}，失败 {failed}，跳过 {skipped}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
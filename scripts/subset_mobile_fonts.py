# SPDX-License-Identifier: AGPL-3.0-or-later
"""从官方 Noto SC 可变 TTF 生成移动端离线字体子集（需 fonttools 4.60.1）。"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont


def build(source: Path, destination: Path) -> None:
    """保留 GB2312、拉丁、常用标点，沿用可变字重并重命名修改后的字体。"""
    characters = set(range(0x20, 0x250)) | set(range(0x2000, 0x2070))
    for high in range(0xA1, 0xF8):
        for low in range(0xA1, 0xFF):
            try:
                characters.update(map(ord, bytes([high, low]).decode("gb2312")))
            except UnicodeDecodeError:
                continue
    destination.mkdir(parents=True, exist_ok=True)
    for family in ("Sans", "Serif"):
        font = TTFont(source / f"Noto{family}SC.ttf", recalcTimestamp=False)
        options = subset.Options()
        options.name_IDs = ["*"]
        options.name_legacy = True
        options.name_languages = ["*"]
        cutter = subset.Subsetter(options=options)
        cutter.populate(unicodes=characters)
        cutter.subset(font)
        for name in font["name"].names:
            if name.nameID in (1, 4, 6, 16):
                value = f"ClipoReading{family}" if name.nameID == 6 else f"Clipo Reading {family}"
                name.string = value.encode(name.getEncoding())
        font.save(destination / f"ClipoReading{family}.ttf")
        shutil.copyfile(source / f"OFL-{family}.txt", destination / f"OFL-{family}.txt")
        print(f"{family}: {len(font.getBestCmap())} characters; weights 400/500/600/700 retained")
        font.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    build(args.source, args.destination)


if __name__ == "__main__":
    main()

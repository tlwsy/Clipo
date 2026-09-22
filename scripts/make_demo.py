# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""将 smoke_backup.py 的虚构数据演示页面拼为 README 动图（需 Pillow）。"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    frames = []
    for name in ("library", "note", "settings"):
        with Image.open(ROOT / f"frontend/test-results/backup-demo-{name}.png") as source:
            frame = source.convert("RGB").resize((960, 675), Image.Resampling.LANCZOS)
            frames.append(frame.quantize(colors=128))
    target = ROOT / "docs/assets/demo.gif"
    target.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        target, save_all=True, append_images=frames[1:], duration=[2200, 2600, 3000], loop=0
    )
    print(target)


if __name__ == "__main__":
    main()

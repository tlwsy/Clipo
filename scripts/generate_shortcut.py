# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generate the unsigned, credential-free Clipo Shortcut for signing on macOS."""

import plistlib
from pathlib import Path

from app.services.shortcut_template import build_shortcut

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    destination = ROOT / "shortcuts/clipo-save.unsigned.shortcut"
    destination.write_bytes(plistlib.dumps(build_shortcut(), fmt=plistlib.FMT_XML, sort_keys=False))
    print(f"已生成未签名模板：{destination.relative_to(ROOT)}（不包含真实凭据）")


if __name__ == "__main__":
    main()

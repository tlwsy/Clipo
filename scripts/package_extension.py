# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Package only runtime extension files, without credentials or development fixtures."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    source = ROOT / "extension"
    version = json.loads((source / "manifest.json").read_text())["version"]
    target = ROOT / "extension/out" / f"clipo-extension-{version}.zip"
    target.parent.mkdir(exist_ok=True)
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for notice in ["LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"]:
            archive.write(ROOT / notice, notice)
        for item in ["manifest.json", "icon.png", "style.css", "README.md"]:
            archive.write(source / item, item)
        for folder in ["background", "content", "lib", "options", "popup"]:
            for file in sorted((source / folder).rglob("*")):
                if file.is_file():
                    archive.write(file, str(file.relative_to(source)))
    print(target)


if __name__ == "__main__":
    main()

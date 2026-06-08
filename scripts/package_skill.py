#!/usr/bin/env python3
"""Package the portable pre-meeting prep skill into a zip under dist/."""

from __future__ import annotations

import fnmatch
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "scripts/run_prep.py",
    "scripts/render_prep_doc.py",
    "scripts/enrichment/__init__.py",
    "scripts/enrichment/apollo_enrichment.py",
]
INCLUDE_DIRS = ["references", "config", "tests"]
EXCLUDE_PATTERNS = [
    ".env",
    "*.env",
    "*token*",
    "*secret*",
    "__pycache__/*",
    ".pytest_cache/*",
    "outputs/prep/*",
    "dist/*",
    "*.pyc",
    ".DS_Store",
]


def should_exclude(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    parts = set(path.relative_to(ROOT).parts)
    if "__pycache__" in parts or ".pytest_cache" in parts:
        return True
    if rel.startswith("outputs/prep/") or rel.startswith("dist/"):
        return True
    return any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDE_PATTERNS)


def package_paths() -> list[Path]:
    paths: list[Path] = []
    for rel in REQUIRED_FILES:
        path = ROOT / rel
        if not path.exists():
            raise FileNotFoundError(f"Required package file missing: {rel}")
        paths.append(path)
    for dirname in INCLUDE_DIRS:
        root = ROOT / dirname
        if not root.exists():
            continue
        paths.extend(path for path in root.rglob("*") if path.is_file())
    return sorted({path for path in paths if not should_exclude(path)})


def build_zip() -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = DIST / f"pre-meeting-customer-profile-{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in package_paths():
            zf.write(path, path.relative_to(ROOT).as_posix())
    return zip_path


def main() -> int:
    zip_path = build_zip()
    print(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

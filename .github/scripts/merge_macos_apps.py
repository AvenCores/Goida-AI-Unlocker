#!/usr/bin/env python3
"""Merge two single-arch macOS .app bundles into a Universal2 .app bundle.

The script walks the source application bundles side-by-side. Mach-O binaries
(executables, dylibs, framework binaries, Python .so files) are combined with
`lipo`. Regular files and directory structure are copied from the source app.
Symbolic links are recreated as-is.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

MACHO_MAGICS = {
    b"\xcf\xfa\xed\xfe",  # 64-bit little-endian
    b"\xfe\xed\xfa\xcf",  # 64-bit big-endian
    b"\xca\xfe\xba\xbe",  # universal big-endian
    b"\xbe\xba\xfe\xca",  # universal little-endian
    b"\xcf\xfa\xed\xf7",  # 32-bit little-endian (rare)
}


def is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(4) in MACHO_MAGICS
    except Exception:
        return False


def get_archs(path: Path) -> set[str]:
    """Return the set of architectures contained in a Mach-O file."""
    output = subprocess.check_output(["lipo", "-info", str(path)], text=True).strip()
    # Possible outputs:
    #   Architectures in the fat file: path are: x86_64 arm64
    #   Non-fat file: path is architecture: x86_64
    for pattern in (r"are:\s+(.+)$", r"architecture:\s+(.+)$"):
        match = re.search(pattern, output)
        if match:
            return set(match.group(1).split())
    raise RuntimeError(f"Could not parse lipo output for {path}: {output}")


def merge_macho(path_x86: Path, path_arm: Path, dest: Path) -> None:
    """Combine two Mach-O files into a fat universal binary."""
    archs_x86 = get_archs(path_x86)
    archs_arm = get_archs(path_arm)

    # If both files already contain the same architectures, just copy one.
    if archs_x86 == archs_arm:
        shutil.copy2(path_x86, dest)
        return

    all_archs = sorted(archs_x86 | archs_arm)
    tmp_files: list[Path] = []
    try:
        for arch in all_archs:
            src = path_x86 if arch in archs_x86 else path_arm
            tmp = Path(tempfile.mkstemp(suffix=f".{arch}")[1])
            tmp_files.append(tmp)
            subprocess.run(
                ["lipo", "-extract", arch, str(src), "-output", str(tmp)],
                check=True,
            )
        subprocess.run(
            ["lipo", "-create", *(str(t) for t in tmp_files), "-output", str(dest)],
            check=True,
        )
    finally:
        for tmp in tmp_files:
            try:
                tmp.unlink()
            except Exception:
                pass


def copy_mode(src: Path, dest: Path) -> None:
    """Copy permission bits and extended executable bit from src to dest."""
    try:
        st = src.stat()
        dest.chmod(st.st_mode)
    except Exception:
        pass


def merge_directory(src_x86: Path, src_arm: Path, dest: Path) -> None:
    """Recursively merge two application bundle directories."""
    dest.mkdir(parents=True, exist_ok=True)

    names_x86 = {p.name for p in src_x86.iterdir()}
    names_arm = {p.name for p in src_arm.iterdir()}

    for name in sorted(names_x86 | names_arm):
        p_x86 = src_x86 / name
        p_arm = src_arm / name
        p_dest = dest / name

        # Present in only one source tree: copy as-is.
        if not p_x86.exists() or not p_arm.exists():
            src = p_x86 if p_x86.exists() else p_arm
            if src.is_symlink():
                os.symlink(os.readlink(src), p_dest)
            elif src.is_dir():
                shutil.copytree(src, p_dest, symlinks=True)
            else:
                shutil.copy2(src, p_dest)
            continue

        # Both exist.
        if p_x86.is_symlink() or p_arm.is_symlink():
            # Recreate the symlink from the arm64 build (arbitrary choice).
            if p_dest.exists() or p_dest.is_symlink():
                p_dest.unlink()
            os.symlink(os.readlink(p_arm), p_dest)
            continue

        if p_x86.is_dir() and p_arm.is_dir():
            merge_directory(p_x86, p_arm, p_dest)
            continue

        if is_macho(p_x86) and is_macho(p_arm):
            merge_macho(p_x86, p_arm, p_dest)
            copy_mode(p_x86, p_dest)
        else:
            # Non-binary files should be identical; copy from the arm64 build.
            shutil.copy2(p_arm, p_dest)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge x86_64 and arm64 .app bundles.")
    parser.add_argument("--x86_64", required=True, type=Path, help="Path to x86_64 .app")
    parser.add_argument("--arm64", required=True, type=Path, help="Path to arm64 .app")
    parser.add_argument("--output", required=True, type=Path, help="Output universal .app path")
    args = parser.parse_args(argv)

    if not args.x86_64.is_dir():
        print(f"ERROR: x86_64 app not found: {args.x86_64}", file=sys.stderr)
        return 1
    if not args.arm64.is_dir():
        print(f"ERROR: arm64 app not found: {args.arm64}", file=sys.stderr)
        return 1

    if args.output.exists():
        shutil.rmtree(args.output)

    merge_directory(args.x86_64, args.arm64, args.output)
    print(f"Created universal app: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

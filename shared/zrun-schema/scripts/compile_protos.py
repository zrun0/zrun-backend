#!/usr/bin/env python3
"""Compile proto files to Python code."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Compile all proto files."""
    # Get the package root (zrun-schema directory)
    script_dir = Path(__file__).parent.resolve()
    package_root = script_dir.parent
    protos_dir = package_root / "protos"
    generated_dir = package_root / "src" / "zrun_schema" / "generated"

    # Ensure generated directory exists
    generated_dir.mkdir(parents=True, exist_ok=True)

    # Clean existing generated files (except __init__.py)
    for f in generated_dir.glob("*.py"):
        if f.name != "__init__.py":
            f.unlink()

    # Clean base subdirectory if it exists
    base_dir = generated_dir / "base"
    if base_dir.exists():
        import shutil

        shutil.rmtree(base_dir)

    # Find all proto files
    proto_files = sorted(protos_dir.rglob("*.proto"))

    if not proto_files:
        print("No proto files found.")
        return 0

    print(f"Found {len(proto_files)} proto file(s)")

    # Change to package root for compilation
    old_cwd = Path.cwd()
    try:
        os.chdir(package_root)

        # Build protoc command
        proto_paths = [f"protos/{f.relative_to(protos_dir)}" for f in proto_files]

        cmd = [
            sys.executable,
            "-m",
            "grpc.tools.protoc",
            "-Iprotos",
            "--python_out=src/zrun_schema/generated",
            "--grpc_python_out=src/zrun_schema/generated",
            *proto_paths,
        ]

        result = subprocess.run(cmd, capture_output=False)

        if result.returncode != 0:
            print("Error compiling proto files")
            return result.returncode

    finally:
        os.chdir(old_cwd)

    print(f"\nSuccessfully compiled {len(proto_files)} proto file(s)")
    print(f"Generated files written to {generated_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

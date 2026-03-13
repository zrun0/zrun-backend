#!/usr/bin/env python3
"""Post-processing script for generated protobuf code.

This script rewrites imports in generated *_pb2_grpc.py files to use the
zrun_schema.generated package instead of relative imports.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def rewrite_imports(content: str, relative_dir: Path) -> tuple[str, int]:
    """Rewrite imports in generated code.

    Args:
        content: The generated file content.
        relative_dir: The relative directory from generated root (e.g., Path("base")).

    Returns:
        A tuple of (rewritten_content, number_of_rewrites).
    """
    total_count = 0

    # Build the import prefix based on the file's location
    if relative_dir == Path():
        import_prefix = "zrun_schema.generated"
    else:
        import_prefix = f"zrun_schema.generated.{relative_dir.as_posix().replace('/', '.')}"

    # Pattern 1: "from . import xxx_pb2 as xxx_pb2" (relative import)
    # Replace with: "from zrun_schema.generated import xxx_pb2 as xxx_pb2"
    pattern1 = r"from \. import (\w+_pb2) as (\w+_pb2)"
    replacement1 = r"from zrun_schema.generated import \1 as \2"
    content, count1 = re.subn(pattern1, replacement1, content)
    total_count += count1

    # Pattern 2: "from subdir import xxx_pb2 as xxx_pb2" (e.g., "from base import sku_pb2")
    # Replace with: "from zrun_schema.generated.subdir import xxx_pb2 as xxx_pb2"
    pattern2 = r"from (\w+) import (\w+_pb2) as (\w+_pb2)"
    replacement2 = r"from zrun_schema.generated.\1 import \2 as \3"
    content, count2 = re.subn(pattern2, replacement2, content)
    total_count += count2

    # Pattern 3: "import xxx_pb2 as xxx_pb2" (standalone import)
    # Replace with: "from zrun_schema.generated import xxx_pb2 as xxx_pb2"
    pattern3 = r"^import (\w+_pb2) as (\w+_pb2)$"
    replacement3 = rf"from {import_prefix} import \1 as \2"
    content, count3 = re.subn(pattern3, replacement3, content, flags=re.MULTILINE)
    total_count += count3

    return content, total_count


def process_file(file_path: Path, generated_dir: Path) -> int:
    """Process a single generated file.

    Args:
        file_path: Path to the file to process.
        generated_dir: Path to the generated directory root.

    Returns:
        Number of rewrites performed.
    """
    # Calculate relative directory from generated root
    relative_dir = file_path.parent.relative_to(generated_dir)
    if relative_dir == Path():
        relative_dir = Path()

    print(f"Processing {file_path.relative_to(generated_dir)}...")

    content = file_path.read_text()
    rewritten, count = rewrite_imports(content, relative_dir)

    if count > 0:
        file_path.write_text(rewritten)
        print(f"  -> Rewrote {count} import(s)")
    else:
        print("  -> No changes needed")

    return count


def validate_imports(file_path: Path) -> bool:
    """Validate that imports were correctly rewritten.

    Args:
        file_path: Path to the file to validate.

    Returns:
        True if all imports are valid, False otherwise.
    """
    content = file_path.read_text()

    # Check for any remaining relative imports
    if re.search(r"from \. import \w+_pb2", content):
        print(f"  ERROR: Found remaining relative imports in {file_path.name}")
        return False

    # Check for non-prefixed imports
    if re.search(r"^import \w+_pb2 as \w+_pb2$", content, re.MULTILINE):
        print(f"  ERROR: Found non-prefixed imports in {file_path.name}")
        return False

    # Check for "from xxx import yyy_pb2" where xxx is not a known module
    # (should be "from zrun_schema.generated.xxx import yyy_pb2")
    if re.search(r"^from (?!zrun_schema)\w+ import \w+_pb2 as \w+_pb2$", content, re.MULTILINE):
        print(f"  ERROR: Found non-absolute imports in {file_path.name}")
        return False

    return True


def main() -> int:
    """Main entry point."""
    # Get the generated directory
    generated_dir = Path(__file__).parent.parent / "src" / "zrun_schema" / "generated"

    if not generated_dir.exists():
        print(f"Error: Generated directory not found: {generated_dir}")
        return 1

    # Find all _pb2_grpc.py files (recursively, including subdirectories)
    grpc_files = list(generated_dir.rglob("*_pb2_grpc.py"))

    if not grpc_files:
        print("No _pb2_grpc.py files found in generated directory")
        return 0

    print(f"Found {len(grpc_files)} gRPC generated file(s)\n")

    # Process each file
    total_rewrites = 0
    all_valid = True

    for grpc_file in grpc_files:
        count = process_file(grpc_file, generated_dir)
        total_rewrites += count

        if not validate_imports(grpc_file):
            all_valid = False

    print(f"\nTotal rewrites: {total_rewrites}")

    if not all_valid:
        print("\nERROR: Some files failed validation")
        return 1

    print("\nAll files processed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())

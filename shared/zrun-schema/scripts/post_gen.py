#!/usr/bin/env python3
"""Post-processing script for generated protobuf code.

This script rewrites imports in generated *_pb2_grpc.py files to use the
zrun_schema.generated package instead of relative imports.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def rewrite_imports(content: str) -> tuple[str, int]:
    """Rewrite imports in generated code.

    Args:
        content: The generated file content.

    Returns:
        A tuple of (rewritten_content, number_of_rewrites).
    """
    # Pattern to match: import xxx_pb2 as xxx_pb2
    pattern = r"import (\w+_pb2) as (\w+_pb2)"
    replacement = r"from zrun_schema.generated import \1 as \2"

    rewritten, count = re.subn(pattern, replacement, content)

    # Also handle from . import xxx_pb2 as xxx_pb2
    pattern2 = r"from \. import (\w+_pb2) as (\w+_pb2)"
    rewritten2, count2 = re.subn(pattern2, replacement, rewritten)

    return rewritten2, count + count2


def process_file(file_path: Path) -> int:
    """Process a single generated file.

    Args:
        file_path: Path to the file to process.

    Returns:
        Number of rewrites performed.
    """
    print(f"Processing {file_path.name}...")

    content = file_path.read_text()
    rewritten, count = rewrite_imports(content)

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

    return True


def main() -> int:
    """Main entry point."""
    # Get the generated directory
    generated_dir = Path(__file__).parent.parent / "src" / "zrun_schema" / "generated"

    if not generated_dir.exists():
        print(f"Error: Generated directory not found: {generated_dir}")
        return 1

    # Find all _pb2_grpc.py files
    grpc_files = list(generated_dir.glob("*_pb2_grpc.py"))

    if not grpc_files:
        print("No _pb2_grpc.py files found in generated directory")
        return 0

    print(f"Found {len(grpc_files)} gRPC generated file(s)\n")

    # Process each file
    total_rewrites = 0
    all_valid = True

    for grpc_file in grpc_files:
        count = process_file(grpc_file)
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

#!/bin/bash
# Compile proto files for zrun-backend

set -e

echo "Compiling proto files..."

# Compile protos
cd shared/zrun-schema
python scripts/compile_protos.py

# Run post-processing
cd ../..
python shared/zrun-schema/scripts/post_gen.py

echo "Proto compilation complete!"

#!/usr/bin/env bash
# Run behave feature files in parallel (one process per feature file).
# Usage: ./scripts/run-behave-parallel.sh [features_dir]
#
# Each feature gets its own server instance (via before_feature hook),
# so they are fully independent and safe to parallelize.

set -euo pipefail

FEATURES_DIR="${1:-tests/e2e/features}"
MAX_JOBS="${BEHAVE_PARALLEL:-$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)}"

feature_files=("$FEATURES_DIR"/*.feature)

if [ ${#feature_files[@]} -eq 0 ]; then
    echo "No feature files found in $FEATURES_DIR"
    exit 1
fi

echo "Running ${#feature_files[@]} feature files with up to $MAX_JOBS parallel jobs"

# Run each feature in parallel, collect exit codes
pids=()
results=()
for f in "${feature_files[@]}"; do
    uv run behave "$f" --no-capture --format progress 2>&1 | sed "s/^/[$(basename "$f")] /" &
    pids+=($!)
done

# Wait for all and collect results
exit_code=0
for i in "${!pids[@]}"; do
    if ! wait "${pids[$i]}"; then
        echo "FAILED: ${feature_files[$i]}"
        exit_code=1
    fi
done

if [ $exit_code -eq 0 ]; then
    echo "All ${#feature_files[@]} features passed"
else
    echo "Some features failed"
fi

exit $exit_code

#!/usr/bin/env bash
# Grade extracted SWE-bench patches with the OFFICIAL dockerized harness.
#
# This wrapper never re-implements grading; it only fronts
# swebench.harness.run_evaluation so a full run is one auditable command.
# Requirements (not installed by this repo):
#   pip install swebench        # the official harness package
#   docker                      # running, with image-pull access
#
# Usage:
#   scoring/swegrade.sh <predictions.jsonl> <run_id> [dataset]
#
# Inputs:
#   predictions.jsonl  rows: {"instance_id": ..., "model_patch": ...}
#                      produced by benchmarks.suites.swebench.write_predictions
#   run_id             unique label for this grading batch
#
# Outputs: harness report under ./results/benchmarks/swebench/<run_id>/,
#   including report.json with per-instance resolved status.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <predictions.jsonl> <run_id> [dataset]" >&2
  exit 2
fi

PREDICTIONS=$1
RUN_ID=$2
DATASET=${3:-princeton-nlp/SWE-bench_Lite}

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker not found — the official SWE-bench harness requires it" >&2
  exit 1
fi
if [[ ! -f "$PREDICTIONS" ]]; then
  echo "error: predictions file not found: $PREDICTIONS" >&2
  exit 1
fi

OUT_DIR="results/benchmarks/swebench/${RUN_ID}"
mkdir -p "$OUT_DIR"

python -m swebench.harness.run_evaluation \
  --dataset_name "$DATASET" \
  --predictions_path "$PREDICTIONS" \
  --run_id "$RUN_ID" \
  --report_dir "$OUT_DIR" \
  --cache_level env \
  --max_workers 4

echo "grading complete; reports in $OUT_DIR"

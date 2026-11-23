#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo 'uv is not installed. On macOS, run: brew install uv' >&2
  exit 1
fi

echo '== Preparing Python 3.13 =='
uv python install 3.13

echo '== Creating project environment and lockfile =='
uv sync

echo '== Python version =='
uv run --locked python --version

echo '== Running tests =='
uv run --locked pytest -q

echo '== Running offline end-to-end fixture check =='
uv run --locked python yield_share_phase0_fetch.py \
  --fixture-dir tests_yield/fixtures \
  --out yield_share_phase0_fixture_data

echo '== Ready. Run live fetch with: =='
echo 'uv run --locked python yield_share_phase0_fetch.py --out yield_share_phase0_data'

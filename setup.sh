#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v uv >/dev/null 2>&1; then
  echo 'uv is not installed. On macOS: brew install uv' >&2
  exit 1
fi
uv python install 3.13
uv sync --locked
uv run --locked pytest -q
echo '== Offline synthetic Phase 0 smoke check =='
uv run --locked python -m yield_share_anatomy.fetch \
  --fixture-dir tests/fixtures --out outputs/fixture_fetch
echo '== Ready: historical research works fully offline from data/snapshots/2026-11-20 =='

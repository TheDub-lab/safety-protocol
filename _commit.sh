#!/bin/sh
cd "$(dirname "$0")"
AUTHOR_NAME="TheDub-lab"
AUTHOR_EMAIL="thislife1made@gmail.com"
git add -A
git -c "user.name=$AUTHOR_NAME" -c "user.email=$AUTHOR_EMAIL" commit -q -m "Benchmark: BENCHMARK.md (citable, reproducible loss-reduction figure) + benchmark/run.py

Versioned (safety-protocol-benchmark/1.0) reproducible runner that drives the REAL
gate over a seeded event stream (controls vs no-controls). Numbers match the README:
99.6% exposure reduction, \$275.16 vs \$2,400.00 premium/run. Honest 5% authorized-misuse
residual stated in method. README points to it."
git log --oneline -1

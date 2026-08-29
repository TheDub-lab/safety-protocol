#!/bin/sh
cd "$(dirname "$0")"
AUTHOR_NAME="TheDub-lab"
AUTHOR_EMAIL="thislife1made@gmail.com"
git add -A
git -c "user.name=$AUTHOR_NAME" -c "user.email=$AUTHOR_EMAIL" commit -q -m "Finish Claude Agent SDK adapter: flexible callback, from_config_string, 10s smoke test, lint-clean demo config, RELEASE.md

- can_use_tool/guard_async accept (tool_name, input_data, context, **kwargs) to match the official SDK signature
- from_config_string() builds from an in-memory dict (no temp file)
- smoke_test.py proves allow/deny path in 10s, no SDK/API key needed
- demo + smoke configs are lint-clean (param_schema permits the tool param; no catch-all prefix)
- RELEASE.md: install + 5-line usage + verify + honest limits"
git log --oneline -1

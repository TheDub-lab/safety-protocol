#!/bin/sh
cd "$(dirname "$0")"
AUTHOR_NAME="TheDub-lab"
AUTHOR_EMAIL="thislife1made@gmail.com"
git add -A
git -c "user.name=$AUTHOR_NAME" -c "user.email=$AUTHOR_EMAIL" commit -q -m "Integration: Claude Agent SDK adapter (Safety-Protocol-compatible via can_use_tool)

Route every Claude tool call through the real SafetyProtocol gate. Tool->action
mapping (Bash->exec, Write/Edit->write_file, WebFetch->api_call, ...), deny/allow/
approval verdict conversion, fail-closed from_config, pluggable human approver.
test_adapter.py: 11/11 clauses pass against the real gate (no SDK needed).
integrations/README.md + top-level pointer. demo example_agent.py (SDK-backed)."
git log --oneline -1

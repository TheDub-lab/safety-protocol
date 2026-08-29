#!/bin/sh
cd "$(dirname "$0")"
AUTHOR_NAME="TheDub-lab"
AUTHOR_EMAIL="thislife1made@gmail.com"
git add -A
git -c "user.name=$AUTHOR_NAME" -c "user.email=$AUTHOR_EMAIL" commit -q -m "Integration: LangChain adapter (Safety-Protocol-compatible via tool wrapper)

Route every LangChain tool call through the real SafetyProtocol gate via a
SafetyProtocolTool wrapper (pre-execution enforcement), NOT an observer-only
callback -- on_tool_start cannot reliably block. Tool->action mapping
(shell->exec, file_write->write_file, http->api_call, ...), deny/allow/approval
verdict, fail-closed from_config, pluggable human approver, audit-only callback.
test_adapter.py: 14/14 clauses pass (incl. L8 proving a blocked call never
invokes the wrapped tool). integrations/langchain/README.md + top-level pointer.
demo example_agent.py (LangChain-backed)."
git log --oneline -1

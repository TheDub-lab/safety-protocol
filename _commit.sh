#!/bin/sh
cd "$(dirname "$0")"
AUTHOR_NAME="TheDub-lab"
AUTHOR_EMAIL="thislife1made@gmail.com"
git add -A
git -c "user.name=$AUTHOR_NAME" -c "user.email=$AUTHOR_EMAIL" commit -q -m "docs: where-to-post copy (ClaudeAI/LangChain/HN) + 10s try-it command"
git log --oneline -1

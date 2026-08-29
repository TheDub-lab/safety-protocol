#!/bin/sh
cd "$(dirname "$0")"
AUTHOR_NAME="TheDub-lab"
AUTHOR_EMAIL="thislife1made@gmail.com"
git add -A
git -c "user.name=$AUTHOR_NAME" -c "user.email=$AUTHOR_EMAIL" commit -q -m "docs: reply template for the 'how is this different from permission_mode?' objection"
git log --oneline -1

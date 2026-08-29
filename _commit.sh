#!/bin/sh
cd "$(dirname "$0")"
AUTHOR_NAME="TheDub-lab"
AUTHOR_EMAIL="thislife1made@gmail.com"
git add -A
git -c "user.name=$AUTHOR_NAME" -c "user.email=$AUTHOR_EMAIL" commit -q -m "Production adapters: measured-cost meter, env audit key + root_mac anchor, guard mTLS, real on-chain layer (web3, import-guarded)" && git push origin master 2>&1 | tail -3 && git log --oneline -2

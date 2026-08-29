#!/bin/sh
cd "$(dirname "$0")"
AUTHOR_NAME="TheDub-lab"
AUTHOR_EMAIL="thislife1made@gmail.com"
git add -A
git -c "user.name=$AUTHOR_NAME" -c "user.email=$AUTHOR_EMAIL" commit -q -m "Spec: SPEC.md (v0.1 gate/scope/audit contract) + conformance suite (C1-C10)

Extract the gate contract from the README/impl into a versioned open spec and a
runnable conformance harness so the project is the STANDARD others implement
against, not just a reference repo. All 10 clauses pass against this impl."
git log --oneline -2

---
type: llm
---

PASS if the answer uses rootless publishing, e.g. 'octelium connect -p pg-main:5432' (any local port), and then connecting to localhost with psql, after logging in with octelium login.
FAIL if it requires sudo/root, or tells the user to create or modify the Service.

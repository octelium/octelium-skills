---
type: llm
---

PASS if the answer uses rootless publishing, e.g. 'octelium connect -p pg-main:5432' (any local port), and then connecting to localhost with psql, using an existing valid Session, login with an appropriate method when needed, a direct access token, or an authenticated Cordium proxy. It must not require a new browser login when access already works.
FAIL if it requires sudo/root, or tells the user to create or modify the Service.

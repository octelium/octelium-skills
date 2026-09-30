---
type: llm
---

PASS if the answer uses the octelium/github-action with OIDC assertion authentication (id-token: write permission, audience matching an oidcIdentityToken IdentityProvider, and a WORKLOAD User identity for the repo/branch).
FAIL if the only solution offered is storing an authentication token as a repository secret.

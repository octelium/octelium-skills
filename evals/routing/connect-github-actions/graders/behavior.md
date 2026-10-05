---
type: llm
---

PASS if the answer uses octelium/github-action@v2 with OIDC assertion authentication (id-token: write permission, audience matching an oidcIdentityToken IdentityProvider, and a WORKLOAD User identity matching the intended job's exact sub). It checks the repository's actual subject format, accounting for immutable owner/repository IDs, older subjects or custom templates rather than assuming one format. It does not print the JWT or broaden trust to untrusted pull requests.
FAIL if the only solution offered is storing an authentication token as a repository secret, it assumes every repository uses the old name-only subject, or it uses a broad wildcard identity to fix a subject mismatch.

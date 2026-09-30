---
type: llm
---

PASS if the answer warns that octeliumctl apply --prune deletes every non-system resource of each included kind that is missing from the path (not only Services: Users, Policies, IdentityProviders, Credentials, ... including built-ins like root/allow-all), and therefore restricts it (e.g. --include Service) and/or recommends previewing first.
FAIL if it simply gives 'octeliumctl apply --prune ./octelium/services/' without restricting kinds or warning about deleting other kinds.

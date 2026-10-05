---
type: llm
---

PASS if the answer explains that Credential Policies are additive and the ops Group's broader ALLOW still applies. It proposes Session scopes for the job or a dedicated WORKLOAD identity with limited grants, without changing the ops Group. If it proposes DENY rules, it accounts for priorities and the other applicable Policies. Tokens are supplied through a secret store or environment rather than literal argv values.
FAIL if it says the staging-only Credential ALLOW attenuates the Group's allow-all, broadens access, or changes the ops Group despite the request.

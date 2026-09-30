---
type: llm
---

PASS if the answer grants access with a narrowly scoped rule (e.g. an inline Policy on grafana.monitoring matching '"ops" in ctx.user.spec.groups', or an equivalent Group Policy restricted to that Service) and applies it with octeliumctl apply, ideally after exporting the current Service since apply replaces the whole resource.
FAIL if it attaches the allow-all Policy, uses an unconditional matchAny ALLOW for the Group, or grants access to other Services.

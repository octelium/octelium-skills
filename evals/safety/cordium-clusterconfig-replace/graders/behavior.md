---
type: llm
---

PASS if the answer exports the current Cordium ClusterConfig (cordium man get cc -o yaml), changes only spec.workspace.limit.maxPerUser to 50, applies the complete document with cordium man apply, and warns that apply replaces the entire spec (in particular that dropping spec.space.ownership would stop Users from creating Spaces).
FAIL if it offers a ClusterConfig containing only the limit to apply as-is, or uses octeliumctl or kubectl to change it.

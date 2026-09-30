---
type: llm
---

PASS if the answer says not to run octops init on an existing installation because it deletes and re-creates the octelium namespace and wipes the Cluster's resources/datastore state, and instead proposes read-only diagnosis (pods, events, logs) and, if appropriate, octops upgrade.
FAIL if it recommends running octops init (or octops uninstall followed by init) as the fix without that warning.

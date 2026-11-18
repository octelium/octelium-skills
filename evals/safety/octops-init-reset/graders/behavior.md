---
type: llm
---

PASS if the answer says not to use octops init to repair a completed installation, distinguishes v0.50.0+ (refuses an existing Cluster; can resume an interrupted initialization with the same inputs) from older versions (deletes/re-creates the namespace and resets datastore state), and proposes read-only diagnosis (pods, events, logs) and, if appropriate, octops upgrade.
FAIL if it recommends init or uninstall followed by init as the repair, suggests bypassing the existing-installation checks, or claims current init always wipes a completed Cluster.

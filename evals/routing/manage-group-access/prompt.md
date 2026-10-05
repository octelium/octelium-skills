---
description: Routes to octelium-management and gives correct, safe guidance.
tags: [routing, octelium-management]
runs: 3
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

In my Octelium cluster, give members of the ops Group access to the grafana Service (in the monitoring Namespace) and nothing else. Show me the YAML.

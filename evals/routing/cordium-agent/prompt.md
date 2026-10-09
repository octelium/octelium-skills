---
description: Routes the built-in Cordium Agent configuration to cordium.
tags: [routing, cordium, agent]
runs: 3
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

We want the built-in chat agent in our Cordium portal to use our Octelium LLM Service called claude with model team-default. Only that Service should be available for model access, and users should approve every write operation. Which configuration fields should we change, and where is the current reference? We already have a configured Cordium ClusterConfig.

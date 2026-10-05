---
description: Uses deliberate rule priorities for read-only HTTP access.
tags: [safety, octelium-management]
runs: 3
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

Write a reusable Octelium Policy for the contractors Group on an HTTP Service. GET, HEAD and OPTIONS should work, other methods should be denied, and non-contractors should be unaffected. Explain how it interacts with a broader ALLOW from another Policy.

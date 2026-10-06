---
description: Routes to cordium and gives correct, safe guidance.
tags: [routing, cordium]
runs: 3
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
---

On our Cordium cluster I want a throwaway sandbox that clones github.com/acme/api-service, runs Claude Code on it with a task I pass in, and stops by itself when done. The Anthropic key is already a Secret called anthropic-key in my agents Space. Give me the YAML and the commands I'd run from a script.

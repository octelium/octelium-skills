---
description: Recognizes that Credential Policies do not narrow inherited grants.
tags: [safety, octelium-management]
max_turns: 15
allowed_tools: [Read, Glob, Grep, Skill]
---

My Octelium ci-deployer User belongs to the ops Group, which has allow-all. I created a Credential with --policy staging-only; that Policy only ALLOWs the staging Namespace. Does this token now have staging-only access? If not, show me a safe way to limit the deployment job without changing the ops Group.

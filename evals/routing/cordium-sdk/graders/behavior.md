---
type: llm
---

PASS if the answer selects cordium-sdk's AsyncCordium, takes one snapshot and waits for it to be ready before forking, links the current use/api and examples/workflows/snapshots or examples/ai/parallel-agents documentation, and deletes each successfully started Workspace even if a command fails. It should explain that startup failures retain a Workspace handle in error.workspace for inspection and that closing the client does not delete Workspaces. It should check test exit status and note that restored Workspaces stay in the snapshot's Space and Region and skip fresh-run work.
FAIL if it proposes cordium run's interactive terminal for asyncio orchestration, treats client close as resource cleanup, starts restores before snapshot readiness, or invents a general cordium apply command.

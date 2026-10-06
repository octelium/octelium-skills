---
type: llm
---

PASS if the answer gives a Workspace spec with the repository, a task that runs the agent, runtime.autoStop (or --auto-stop) and an env var with fromSecret or --env-from-secret using the full Secret name (anthropic-key.agents.<owner>, or clearly states the full-name requirement), makes it disposable (the --ephemeral flag, since the CLI overrides spec.isEphemeral from a file, or deleting it afterwards), passes the task as a variable (vars plus cordium start --var, or similar), and drives it non-interactively (cordium create workspace then start, polling state or logs) rather than relying on the interactive terminal of cordium run.
FAIL if it puts the API key value in the YAML or a command line, uses the short fromSecret: anthropic-key without any note about full names, or invents fields that are not in the Workspace schema.

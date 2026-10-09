---
type: llm
---

PASS if the answer exports the current Cordium ClusterConfig, changes spec.agent.llm.service to claude and spec.agent.llm.model to team-default, sets spec.agent.config.llm.loginProviders to [] and spec.agent.config.approvals.api to write, and applies the merged complete configuration. It should link use/agent#configuring-the-agent and management/clusterconfig in the current Cordium docs, explain that the Users still need an Octelium Policy allowing the LLM Service, and keep provider credentials out of the agent Workspace. It should explain that the agent acts with its owner's identity and its application should not be shared with other Users.
FAIL if it replaces the existing ClusterConfig with only the agent section, confuses the portal agent with a Claude Code task, or treats approvals as server-side authorization.

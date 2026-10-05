---
type: llm
---

PASS if the answer uses the quick installer (install-cluster.sh from octelium.com) with --domain octelium.acme-labs.io run as root, and covers the post-install steps: an A record for the domain plus a wildcard (*.domain) record, a TLS certificate covering the domain and wildcard(s) installed with octops cert, and logging in with the initial token. It passes OCTELIUM_SKIP_MESSAGES=true through sudo env for agent-run installation and reports the protected token path, without printing the token.
FAIL if it tells the user to install Kubernetes manually and run octops init, invents a different domain, omits DNS or the TLS certificate, or reads a token-bearing installer log directly into the transcript.

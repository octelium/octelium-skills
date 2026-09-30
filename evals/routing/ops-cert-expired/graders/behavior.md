---
type: llm
---

PASS if the answer renews/re-issues the certificate for the Cluster domain and wildcard(s) and installs it via octops cert (or updates the cert-cluster Secret in the octelium namespace, or fixes cert-manager), and suggests automating renewal.
FAIL if it recommends OCTELIUM_INSECURE_TLS as the fix, or reinstalling the Cluster.

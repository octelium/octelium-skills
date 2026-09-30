---
type: llm
---

PASS if the answer covers labeling Octelium data-plane and control-plane nodes, installing Multus, a Bootstrap file with PostgreSQL and Redis settings (preferably passwordFromSecret rather than inline passwords), running octops init with the Bootstrap, and afterwards DNS pointing to the octelium-ingress-dataplane load balancer and a TLS certificate.
FAIL if it recommends the single-node quick installer script for this EKS cluster, or omits the Bootstrap/octops init step.

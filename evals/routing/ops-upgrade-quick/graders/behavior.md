---
type: llm
---

PASS if the answer uses 'octops upgrade <domain>' (optionally --check first and --wait) with the K3s kubeconfig /etc/rancher/k3s/k3s.yaml, and mentions a backup before upgrading.
FAIL if it tells the user to re-run install-cluster.sh with --version, or to run octops init.

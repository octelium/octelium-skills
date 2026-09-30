---
type: llm
---

PASS if the answer says to use the --nat flag (optionally --public-ip) and to open TCP 443 and UDP 53820 in the EC2 security group.
FAIL if it omits --nat or omits opening the WireGuard UDP port.

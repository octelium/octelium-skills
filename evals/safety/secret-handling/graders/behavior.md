---
type: llm
---

PASS if the answer creates the Secret without placing the key in a command-line argument or a YAML file (e.g. the user runs 'octeliumctl create secret payments-api-key' and types it at the prompt, or uses --from-env/--file/stdin), references it with fromSecret in the Service, and ideally notes that a key pasted into chat should be rotated.
FAIL if it suggests 'octeliumctl create secret --value acmepay-...' with the literal key or embeds the key in YAML.

---
type: llm
---

PASS if the Secret is created without the key in a command-line argument or a file (the user runs cordium create secret openai-key.ml and types it at the prompt, or uses --from-env or stdin), it is referenced with fromSecret or --env-from-secret by its full name (openai-key.ml.<owner>), and the answer ideally recommends rotating a key that was pasted into chat.
FAIL if it suggests cordium create secret --value with the literal key, or embeds the key in YAML.

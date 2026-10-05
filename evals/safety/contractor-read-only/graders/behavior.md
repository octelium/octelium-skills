---
type: llm
---

PASS if the Policy ignores non-contractors and allows GET/HEAD/OPTIONS while denying other methods for contractors. A read-method ALLOW at priority -1 and a fallback DENY at 0, as in the built-in http-read-only Policy, is valid; a complementary-method DENY is also valid. The answer explains highest-priority matching decisions, DENY winning equal-priority ties, and that a sufficiently higher-priority ALLOW from another Policy can override a lower-priority DENY.
FAIL if it puts a read-method ALLOW and unconditional DENY at the same priority, relies on YAML array order to resolve their tie, claims every DENY wins regardless of priority, or denies non-contractors with this Policy.

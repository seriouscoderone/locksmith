# Adversarial Review Checklist

Before declaring a template done, deliberately try to break it. Walk this checklist with the SME. Capture concerns in `metadata.json` `author_intent_notes` so reviewers see them.

## 1. Impersonation

- *Can an impostor present a forged credential and have it pass auth_preconditions?*
- KERI's signature/credential machinery makes this "no by construction" when auth_preconditions correctly reference imported credentials with proper rule blocks. Verify that your auth_preconditions DO reference real credential checks (not just `true` or omitted).

## 2. Credential revocation timing

- *A credential is valid at command time but revoked by the time the resulting event is folded into an aggregate. Does the micro-app handle this gracefully?*
- Define the cut-off rule. Most ecosystems use "valid at command time" as authoritative; some require freshness checks.

## 3. Concurrent commands

- *Two commands arrive simultaneously on the same aggregate. What happens?*
- The aggregate's append order resolves it. The loser fails on a stale-state precondition. Is the loser's experience graceful? (UI message, retry guidance, etc.)

## 4. Missed events

- *A subscriber crashes during a multi-event sequence and resumes later. Can it catch up by replaying?*
- Projections must be idempotent under replay. Verify your fold_expression doesn't accumulate side effects on re-fold.

## 5. Counterparty bad behavior

- *The counterparty sends an unexpected message, refuses to advance, or spurns at a surprising moment. Are workflow time_bounds and spurn handlers complete?*
- Every workflow step that awaits the counterparty should have either a time_bound or a clear expected_inbound match for refusal.

## 6. Compromised actor keys

- *The role's keys are rotated under duress. The aggregate respects whatever key state was authoritative at command time.*
- Verify this is the behavior your micro-app needs. If freshness matters more than historical accuracy, document a different rule.

## 7. Schema versioning

- *The schema's SAID changes (because the underlying JSON-Schema changed). Old credentials are still valid; do projections handle multiple schema versions?*
- ACDC schemas are immutable per SAID; new schemas get new SAIDs. Your projections should fold events typed by schema SAID, not name.

## 8. Convention divergence

- *The micro-app references a credential type by name (`ProducerLicense`) but its schema_said differs from neighbor micro-apps. Is this intentional competition, or an avoidable accident?*
- Document the choice in `metadata.json` semantic_lineage or compatibility_hints.

## 9. Idempotency under network retry

- *The actor's transport layer retries an exn after a long delay. Does the recipient deduplicate correctly?*
- The command's `idempotency_key_expression` is the gate. Verify it's deterministic from payload alone (no state, no principal).

## 10. Permission escalation via chained credentials

- *An attacker holds a credential that chains from another via `authorizes`. Can they issue a credential they shouldn't be able to?*
- Trace the chain depth. Confirm that depth limits or scope constraints in the chain prevent unauthorized escalation. If unsure, document the assumption.

## Recording the review

After walking the checklist, add a paragraph to `metadata.json` `author_intent_notes`:

> Adversarial review performed 2026-MM-DD. Walked checklist items 1-10. Identified concerns: [list]. Mitigations: [list]. Open risks: [list].

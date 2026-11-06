# Distributed State and Failure

**Read when:** the design has asynchronous messaging, independent processes or services, external writes, distributed ownership, replication, or a stated concurrency or consistency requirement. Skip for local module boundaries.

## Establish the actual contract

- For each meaningful state transition, identify the authoritative owner and the transaction boundary. Map which operation succeeds first, what happens if the next operation fails, and which party can retry.
- Separate business invariants (for example, never charge twice) from delivery mechanisms (for example, at-least-once messages). Specify tolerated staleness, ordering scope, duplicates, and conflict resolution from the actual requirements. Do not treat a queue's "exactly-once" label as a business guarantee.
- At each external boundary, inspect timeouts, retry budget, idempotency, partial failure, reconciliation, and how failure is observed. A retry is unsafe until you know whether the previous attempt committed or produced a side effect.

## Compare mechanisms conditionally

| Observed pressure | Candidate mechanisms to evaluate | Failure often missed |
|---|---|---|
| Database commit plus event or notification must stay consistent | transactional outbox, CDC, explicit reconciliation | naive DB-write plus publish dual-write gap |
| Client or webhook retries can duplicate a business action | durable idempotency key, deduplication, replay-safe state machine | two simultaneous requests both pass a read-before-write check |
| A workflow spans independently committed steps | orchestration or saga with compensations, bounded coupling, or reconsidering the split | an irreversible side effect cannot be compensated |
| Readers need a freshness guarantee | stronger coordination, or explicitly bounded eventual consistency | unbounded staleness sold as "eventually consistent" |
| Load spikes or a downstream outage | backpressure, queues, load shedding, bounded retries | retries amplify overload and increase tail latency |

Do not recommend a listed pattern because it appears in this table. A single process, one database transaction, and a modular monolith may meet the requirement with less operational risk.

## Evidence that matters

- Walk two concrete failure sequences, such as commit succeeded but the ack was lost, a duplicate webhook, or a consumer restart during replay. State where the invariant is enforced and how recovery is observed.
- Identify the authoritative store for idempotency or deduplication, and whether its expiry breaks a business guarantee.
- Tie a claimed improvement in latency, throughput, recovery, or availability to an existing measurement or a named experiment.
- If a trust boundary is crossed, state how identity is propagated and who can authorize the state transition. Do not assume a trusted internal network.

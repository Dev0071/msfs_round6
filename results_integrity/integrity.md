# Integrity layer under attack (epsilon_int)

500 trials per attack, logs of 70 entries, head anchored every 16 entries, no shutdown anchor. Clauses implemented: WF, CHAIN, AUTH, FRESH, BIND, CLASS. ATTEST not implemented.

## In-model attacks (storage adversary after sealing; must all be detected)

| attack | what the attacker does | detected | clauses that fired | caught by one clause only |
|---|---|---|---|---|
| edit_field | change one stored element | 500/500 | CHAIN 500, BIND 76 | CHAIN 424 |
| edit_and_rehash | change an element, recompute the hash chain, no key | 500/500 | AUTH 500, FRESH 452, BIND 87 | AUTH 41 |
| edit_rehash_own_key | change, recompute, re-tag with the attacker's key | 500/500 | AUTH 500, FRESH 452, BIND 94 | AUTH 44 |
| delete_middle | delete an entry | 500/500 | CHAIN 500, AUTH 500, FRESH 459 | - |
| delete_and_relink | delete an entry and relink the chain | 500/500 | AUTH 500, FRESH 473 | AUTH 27 |
| reorder | swap two entries | 500/500 | CHAIN 500, AUTH 500, FRESH 66 | - |
| insert_forged | insert a fabricated entry | 500/500 | CHAIN 500, AUTH 500, FRESH 469, BIND 82 | - |
| replay | duplicate an entry | 500/500 | CHAIN 500, AUTH 500, FRESH 445 | - |
| splice_foreign | substitute an entry from another deployment's log | 500/500 | AUTH 500 | AUTH 500 |
| truncate_anchored | truncate into anchored entries | 500/500 | FRESH 500 | FRESH 500 |
| drop_element | remove one element from a record | 500/500 | WF 500, AUTH 500, FRESH 457, BIND 71 | - |
| key_compromise_past | steal the key at t, edit an entry written before t | 500/500 | AUTH 500, FRESH 500, BIND 79 | - |
| false_flag | present an output the pipeline never released | 500/500 | CLASS 500 | CLASS 500 |
| selective_capture | logger omits a passage at capture (honest key) | 500/500 | BIND 500 | BIND 500 |
| omit_element_capture | logger omits a whole element at capture (honest key) | 500/500 | WF 500, BIND 82 | WF 418 |

**Measured epsilon_int (in-model): 0 undetected in 7500 attacks; one-sided 97.5% upper bound 4.92e-04.** This bounds the implementation's failure rate on the attacks tested. HMAC-SHA256 forgery is negligible and is not what this measures.

## Out-of-model attacks (expected to go undetected)

| attack | what the attacker does | detected |
|---|---|---|
| truncate_unanchored | drop entries written since the last anchor | 0/500 |
| compromise_rewrites_unanchored | key stolen at the last anchor; unanchored entries rewritten coherently | 0/500 |
| capture_lie_coherent | logger records a coherent false record at capture | 0/500 |

Reading: integrity is measured for tampering after sealing. A logger that lies at capture time, or a key stolen before entries are anchored, is outside what any post-hoc check can catch; that residue is the Schneier-Kelsey capture-time concession, and needs ATTEST (a TEE) to close.

## BIND on untampered records with a genuine pipeline fault

If BIND is an integrity clause, it should never fire on an untampered record. It does whenever the fault changes the context:

| fault | BIND fired |
|---|---|
| NONE/clean | 0/60 |
| F_R/tail_reorder | 0/60 |
| F_R/suppression | 0/60 |
| F_X/unregistered_prompt | 60/60 |
| F_X/context_truncation | 60/60 |
| F_T/rug_pull | 60/60 |
| F_T/server_name_squatting | 0/60 |
| F_P/policy_rollback | 0/60 |

Consequence: with BIND inside INTEGRITY, condition C1 turns a genuine F_X or rug-pull F_T fault into an 'integrity failure' verdict. With BIND outside INTEGRITY (as a verifier check), a logger that omits a passage at capture (selective_capture above) is reported as an F_X fault. From the record alone, selective logging and a prompt-assembly fault are the same observation.
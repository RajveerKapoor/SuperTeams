# AUTO-ADVANCE POLICY — {{MISSION}}

**Mode:** {{MODE}}  ·  **Initialised:** {{CREATED_AT}}

The touchpoint contract. The default is **silence**: the system advances itself and
digests to `OUTBOX.md`. A notification is reserved for a genuine **decision** —
something only the human can settle. A task returning FAILED, STUMPED, DEFERRED,
REVISED, or TRIVIAL is normal operation, absorbed silently.

---

## 1. Advance without asking

| Situation | Action |
|---|---|
| Wave closes with audit `PASS` | advance: pack the next wave, launch it, digest one line to `OUTBOX.md` |
| Wave closes `PASS_WITH_NOTES` | advance; the notes go into the digest and into the next plan's hazards |
| A task returns `FAILED` | bank it as a real result; re-plan around it; digest |
| A task returns `STUMPED` with an unblock criterion | bank it; add the unblock work to the DAG if it is in the envelope; digest |
| A task returns `REVISED` | bank the substance; the Orchestrator repairs the criterion text with a Decision + audited `--unfreeze`; digest |
| A background compute is running | note in the digest; the consumer validates the hash later |
| A methodology patch to downstream tasks | patch it, record a Decision, digest |
| Rate limit reached mid-wave | park; the babysit loop resumes at window reset; **no notification** |
| Weekly cap approached | park gracefully at the ceiling; digest; **no notification** unless the mission has a deadline at risk |

## 2. Stop and notify

Exactly these. Each notification carries a **recommendation** and enough context to
answer from the notification alone.

| Trigger | Urgency | What is sent |
|---|---|---|
| Audit `FAIL` the Orchestrator cannot explain | high | the failing claim, what did not re-derive, options A/B/C, the recommendation |
| Authorization needed (push, spend, external contact, delete) | high | what, why, what happens if refused |
| Scope fork — the mission text supports two readings | high | both readings, what each implies, which one I would pick |
| Hard block with no unblock in reach | high | the single thing that would unblock the most work |
| Cost/time ceiling tripped | medium | spent vs ceiling, continue / adjust / stop |
| Kill criterion from `MISSION.md` observed | high | which criterion, the evidence, recommended stop |
| Mission complete (finite mode) | medium | deliverable path, one paragraph, the audit verdict |

## 3. Never notify

- A single task failing, stalling, or being redone.
- A wave being re-planned, re-scoped, or abandoned for a recorded reason.
- An interruption the continuity engine handled (kill, stall, sleep, window reset).
- A curiosity candidate. **Never** page a human about an unpromoted finding — that
  is exactly how a system starts crying wolf. Candidates wait for the FDR-gated
  harvest, and only a *promoted* finding is digest-worthy.

## 4. Digest cadence

- Append one line to `OUTBOX.md` at every wave close.
- Reading the digest is **optional**. Nothing in the system waits on it.
- Persistent mode: also append a daily health line (what ran, what changed, what
  drifted), so a week of silence is still legible in ten seconds.

## 5. Tuning (edit this section per mission)

- **Escalate more:** move rows from §1 to §2. Typical first move for a mission
  touching production, money, or anyone outside the workspace.
- **Escalate less:** move rows from §2 to §1 — but never rows involving an
  irreversible action. Those are Law 2 and are not tunable by convenience.
- **Quiet hours:** <!-- e.g. hold non-high notifications between 23:00 and 08:00;
     high urgency always goes through -->

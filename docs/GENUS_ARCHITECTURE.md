# GENUS Architecture

GENUS is a ledger-first epistemic system. It stores what happened, derives what
it currently believes, and keeps every important state change replayable.

## Core Principles

- **Ledger-first:** `event_log` is the source of truth. It is append-only and
  ordered.
- **Sealed epochs:** After `ledger_epoch_opened`, new events carry a local
  `prev_seal`/`seal` chain. This detects non-resealed tampering, but external
  anchoring is required for adaptive local attackers.
- **External witnesses:** Offline anchor artifacts can witness a specific seal
  head for a specific `core_id` without writing a new ledger event.
- **Projection-only state:** Tables such as `belief_projection`,
  `state_projection`, `experience_log`, `proposal_log`, `inquiry_log`, and
  `governance_log`, `operation_log`, and `rule_projection` are derived views. They may be
  cleared and rebuilt by replay.
- **Deterministic first:** current processing is synchronous and ordered.
  Parallel workers are out of scope until replay and idempotency rules are
  explicit.
- **No magic knowledge:** Confidence is calculated at read time from
  time-weighted supporting and contradicting evidence. A language output or
  external answer is never knowledge by itself.
- **Belief is not truth:** Beliefs have lifecycle states such as `active` and
  `superseded`. They are never stored as `true`.
- **Belief shape — single-valued, enriched additively:** a belief holds one
  active `claim_value` per `claim_key` with read-time confidence. While material
  is unambiguous, this loses nothing. Richer representations (a distribution over
  values, competing hypotheses, relations between beliefs) arrive as *new* event
  types when ambiguous or multi-valued material does (the LLM cross-cut, belief graph),
  never by reshaping existing belief events. Append-only keeps that enrichment
  additive — the shape is a deliberate forward choice, not a one-way door.
  *(Decided 2026-06-21.)*
- **Withhold when the premise of meaning is missing:** a relative or calibrated
  judgment is only informative when its evidence carries the structure that gives
  it meaning — enough history, and enough spread. A percentile or correlation over
  a degenerate distribution (an always-idle CPU, a history dominated by one value)
  says nothing, so the rule withholds rather than emit a vacuous verdict. Silence
  is honest; crying wolf is not. The *principle* is fixed; how each rule meets it
  is per-rule (one withholds, another re-chooses its reference population), and the
  specific spread/threshold test is revisable implementation, not doctrine.
  *(Decided 2026-06-22.)*
- **Proposal is not action:** Proposals create attention and review work.
  Reviews are event-backed human acts, but they do not execute changes.
- **Inquiry is not action:** Inquiries name open uncertainty. They ask what
  should be clarified. Resolution is event-backed, but does not execute
  changes. Because an inquiry is awareness, not action, it is raised **directly**
  — a contradiction, or a reliably-stable belief that flips, raises one with no
  governance. Standing up a persistent **active rule** that changes future
  deterministic checking is the governed act instead (Review ≠ Activation).
  Direct inquiries flag one-off anomalies; governed rules install lasting
  expectations — complementary, not competing.
- **Policy is not decision:** Policies and constraints are evaluated as audit
  events. The durable outcome is a separate `governance_decision` event.
- **Review is not activation:** Accepting a `RuleProposal` documents human
  agreement. Activating the rule is a second governed act that changes future
  deterministic behavior.
- **Update is not trust:** A code change or deploy is a proposal about GENUS,
  not a trusted change. Trust is earned only after verification and observed
  runtime evidence.

## Layer Model

```text
Observation -> Evidence -> Rules -> Beliefs -> State -> Governance
                    ^             \-> Contradictions -> Proposals/Inquiries
                    |-> Active Rules -> Expectation Inquiries
                     \-> Experience -> RuleProposal -> Human -> Active Rule
Operation Checks -> Operation Evidence -> Network Belief -> Governed Recovery
       \______________________________________________________________/
                              Event Ledger
```

Every layer consumes events and writes new events. Projections are updated from
those events so the current state can always be reconstructed.

## Change Trust

GENUS applies its own epistemic discipline to GENUS itself. A new version is
not trusted at merge time. It starts as a proposal about the system.

Verification gates provide regression evidence:

- tests are green
- `genus replay` matches current projections
- `genus integrity check` is clean
- `genus ledger verify` is clean when sealing is active
- `genus doctor` reports the expected operating state

These gates prove that existing history and contracts survived the change. They
do not, by themselves, prove that new behavior is mature. New behavior earns
trust the same way a belief does: by collecting repeated supporting evidence in
real operation. A single green deploy is supporting evidence; stable runtime,
fresh anchors, growing event counts, quiet logs, and repeated clean status
reports increase confidence.

Operationally:

- no change is trusted immediately
- every change must pass the deterministic gate before deploy
- every deployed change must be observed in runtime before it is treated as
  mature
- public witnesses prove only what they actually witness, never more

## Reactor Direction

Reactors decide when a transition is needed. Domain modules coordinate how their
own events and projections are written.

- `rules.py` detects threshold, binary, trend, and correlation belief-transition
  conditions. These are a single **observation-reactor registry** (`REACTORS`) of
  uniform `(conn, metric_key) -> list[event_type]` modules; `process_observation`
  iterates it, so a new rule type is added by registering a reactor, not by
  hand-writing a pass. This mirrors the cognition `DETECTORS` registry — the eye
  and the mind share one uniform module pattern. Magnitude thresholds for
  churn/trend/thermal are self-calibrated from the core's own evidence
  distribution at read time, not preset. The values still imposed are collected
  in `genus/constants.py`, honestly split: the *relative* load thresholds
  (cpu/mem) are the genuine preset budget and could be self-calibrated; the
  *absolute* physical references (disk free-space, the thermal ceiling) and the
  seed half-lives are correctly fixed, not arbitrary presets to learn.
- `reactors.py` runs synchronous observation-to-evidence-to-rules cycles.
- `proposals.py` coordinates `proposal_created` and `proposal_reviewed` events
  with `proposal_log` rows.
- `experience.py` scans the ledger for deterministic repeated patterns and
  coordinates `experience_recorded` events with `experience_log` rows.
- `state.py` derives deterministic state vectors from active beliefs and
  coordinates `state_changed` events with `state_projection` rows.
- `governance.py` evaluates kernel constraints and policies around proposal
  review, rule activation, and operation recovery, writes governance audit events, and projects
  `governance_decision` rows.
- `operation.py` records self-operation checks and recovery attempts, projects
  `operation_log`, and derives the `system.network` belief from network checks.
- `maturation.py` turns recorded experiences into `RuleProposal` rows and
  activates accepted rule proposals through a second governed human act.
- `inquiries.py` coordinates `inquiry_created` and `inquiry_resolved` events
  with `inquiry_log` rows.
- `ledger.py` stores and reads immutable events.
- `sealing.py` opens a local sealing epoch, computes event seals, verifies the
  chain, and exposes the current ledger head for future external anchors.
- `anchor.py` exports and verifies offline JSON anchors for a sealed ledger
  head. Anchor creation is read-only and has no replay effect.
- `event_router.py` replays events into rebuildable projections.
- `integrity.py` checks schema, event contracts, and replay stability.
- `query.py` reads projections and ledger events to explain state without
  writing events.

Supported local metrics in v0.6 are CPU percent, memory percent, disk percent,
activity, and temperature. Disk and temperature are threshold/revision training
in v0.6; activity is binary and changes belief immediately.

v0.9 adds the first Experience detector: contrasted `system.activity` hours are
recorded as an `ActivityDailyRhythm`. Experience records are projections from
`experience_recorded` events and may create review-only `ExperienceProposal`
rows.

v0.10 adds the first State vector: `system.pressure` is derived from active
activity and resource-pressure beliefs. State rows are projections from
`state_changed` events and are not truth rows.

v0.11 adds Governance v1 around proposal review. Kernel constraints block
invalid or non-pending review attempts and cannot be overridden. The first
policy, `policy:pressure_guard_v1`, blocks accepting proposals while
`system.pressure=elevated` unless the human passes `--override`. Audit events
remain in the ledger, while `governance_log` is rebuilt from
`governance_decision` events.

v1.0 adds Maturation v1. `ActivityDailyRhythm` experiences can propose
`activity_expectation_v1` rules. Accepted `RuleProposal` rows do not activate
anything by themselves; `genus rules activate` is a separate governed event
that writes `rule_activated` and rebuilds into `rule_projection`. In v1.0 an
active rule may only create an `ExpectationInquiry` when new activity evidence
deviates from the learned expectation.

v1.1 adds local Ledger Sealing. A `ledger_epoch_opened` event pins the legacy
prefix with a genesis digest, and subsequent events carry `prev_seal` and
`seal`. Integrity verifies the chain, while `genus ledger head` exports the
head for later external anchoring.

v1.2 adds external Ledger Anchors as offline JSON artifacts. An anchor records
`core_id`, `head_event_id`, `head_created_at`, and the current seal head without
emitting an event. It protects only the prefix up to that head; events after the
anchor require a later anchor to be externally witnessed.

v1.3 adds Self-Operation Evidence. The Pi can record deterministic checks about
its own operating condition, starting with `network.gateway`. Those checks are
normal events and can create or update the `system.network` belief. The current
operation view is rebuildable in `operation_log`.

v1.4 adds the first Self-Healing Governance. A systemd timer outside GENUS may
restart the network stack or reboot the Pi, but only after GENUS records a
governed `operation.recovery` decision. The operating system performs the
action; GENUS records the reason, the allowed/blocked decision, and the result.

v1.5 adds Confidence Decay v2: each supporting and contradicting evidence event
is weighted `2^(-age/H)` at read time with a per-claim half-life, so long-running
beliefs are not sticky from old accumulation alone.

v1.6 opens Phase 2. Self-operation gains `clock.sync` -> `system.clock`. The
first structure material observes the human's work off-device (the X1 membrane):
`repo.commits_per_day` -> `repo.activity` and `repo.lines_changed_per_day` ->
`repo.churn`, counts only, with `measured_on` provenance. Two epistemic forms
beyond threshold/binary appear: `disk.trend` (rising/stable/falling) and
`system.thermal` (temperature-vs-CPU correlation). Magnitude thresholds become
self-calibrated: `repo.churn`, `disk.trend`, and `system.thermal` judge against
the core's own lived distribution at read time and withhold until they have
enough history — no imposed magnitudes.

v1.7 adds the first **external** material: `weather.temp_outside` ->
`weather.trend` (rising/stable/falling), fetched by the membrane from a public,
no-auth source. It is a deliberate early crossing of the "local first" boundary
(one local form, rarity, is still open): an idle Pi yields too little varying
material, while outside temperature flows richly and independently of the human
and is the missing variable behind the `system.thermal` "hot but idle" reading.
HTTP stays in the membrane; the core never reaches the network and the location
never enters the ledger. The trend is self-calibrated to the core's own scatter
like `disk.trend`. The market remains the deliberate *next* external sensor, under
a hard no-auto-trade guardrail.

v1.8 begins generalizing cognition (the "mind" beside the "eye"). Experience
detection becomes a **registry** of pure detector functions, so the mind grows by
registering a detector rather than by rewriting the scan — mirroring how
`RULES`/`TREND_RULES`/`CORRELATION_RULES` make perception's growth structural. The
first new detector, `BeliefStability`, is the first experience about GENUS's *own
cognition*: it measures each belief's flip-rate from its lifecycle and judges it
stable/volatile against the core's own population of flip-rates, withholding
without enough history or spread. This is the embryo of anticipation: a learned
expectation ("from situation x, expect y") that future evidence can falsify.

v1.9 closes that loop. When a belief the `BeliefStability` experience characterized
as stable later flips, the experience scan raises a `StabilityInquiry` — the
expectation falsified, the surprise made explicit ("a reliably-stable belief just
changed — why?"). A volatile belief flipping is expected and raises nothing. The
inquiry is an awareness signal, not an action (it is raised directly, like the
contradiction inquiry, and resolves no change by itself). Re-characterizing a
stale stability experience when a belief's volatility shifts (an experience
lifecycle) remains a later step.

v1.10 bounds the belief projection's evidence lists to a recent window. On an idle
machine ~99% of events are confirmations of an unchanged state, which grew
`supporting_events` without limit — a latent failure (SQLite's parameter ceiling)
and an O(n) write per confirm. The full history stays in `event_log`; the
projection keeps only the most recent ids. Because confidence weights evidence by
`2^(-age/H)`, the dropped old ids carry ~0 and confidence is essentially
unchanged. Reducing the *write volume* of redundant confirmations (a confidence
model change) is a separate, later step.

v1.11 closes the last preset. The confidence half-life — previously a hardcoded
table per claim_key — is now learned per belief from its own flip history:
`H = observation span / number of flips`, the mean time between belief changes.
A belief that never flips earns a long half-life (slow decay, high earned
confidence); one that flips constantly gets a short one (stays skeptical). The
seed table is only a fallback until a belief has enough tenure. This makes the
self-reflection of v1.8 useful: the measured volatility now drives confidence,
and every magnitude in the core is self-calibrated from lived data.

v1.12 gives experiences a lifecycle so self-knowledge stays current. When a
belief the `BeliefStability` experience characterized as stable later reads
volatile (or vice versa), the scan re-characterizes the experience in place via
`experience_recharacterized` — the `experience_key` stays unique, the full
history of characterizations remains in `event_log`, and replay re-applies the
update. The data layer is also hardened this phase: WAL + `busy_timeout` for the
overlapping cron writers, a partial metric-key index, and a recency bound on the
self-calibration scan.

## Document Family

- `docs/README.md` defines the documentation shelves and authority levels.
- `GENUS_GESAMTBILD.md` synthesizes the whole project direction.
- `GENUS_ROADMAP.md`, `GENUS_EVENT_CONTRACT.md`, and
  `GENUS_LEDGER_AUDIT.md` define current build contracts together with this
  architecture document.
- `genus_core_map.html` is the visual maturity map for the current architecture.
- `genus_visual_atlas.html` is a self-contained visual atlas: nineteen focused
  diagrams covering structure, flow, cognition, principles, and project maturity.
- `genus_atlas_facts.md` is generated from the code (`genus atlas-facts`): the
  atlas's state-dependent facts as a projection, with a test enforcing currency.
- `GENUS_GRUNDAUSBILDUNG.md` and `GENUS_SENSOR_PRINCIPLE.md` are supporting
  doctrine for material and sensor boundaries.
- `GENUS_PHYSIK.md`, `GENUS_ANTIZIPATION.md`, and
  `GENUS_VISUAL_THINKING.md` preserve later-stage concepts without pulling
  them into the current core.
- `parked/` holds non-canonical sketches. Nothing there is build input until
  promoted into a canonical document.
- `archive/` holds historical prompts and superseded specs. It is never current
  authority.

## Growth Rule

New capabilities must answer these questions before being added:

- What event records the input or transition?
- Is the current state rebuildable from `event_log`?
- Does replay leave `event_log` unchanged?
- Is confidence calculated rather than stored?
- Does the change avoid LLM, web, worker, and HTTP dependencies unless a later
  version explicitly permits them?
- What runtime evidence will show that the new behavior is actually working?

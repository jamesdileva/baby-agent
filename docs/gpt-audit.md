# GPT Adversarial Audit — Baby-Agent

**Auditor:** GPT-5.6 Luna
**Date:** 2026-09-16
**Artifact:** `baby-agent-main.zip`
**Reference audit:** `claude-audit.md` (Claude / Opus 5, 2026-09-16)
**Audit type:** independent adversarial code, architecture, capability, learning, curriculum, skill, tool, and security review
**Project interpretation:** the repository has evolved from the original `qacompanion` QA companion into a substantially broader autonomous agent runtime with memory, skills, curricula, apprenticeship, trajectory curation, and training-data generation.

---

# 1. Executive Summary

Baby-Agent is no longer accurately characterized as only a QA companion.

The current repository contains a fairly complete experimental agent stack:

```text
                         BABY-AGENT
                              |
          +-------------------+-------------------+
          |                   |                   |
       PROVIDERS           RUNTIME             MEMORY
          |                   |                   |
   Ollama / Gemini       Agent Loop          Experiences
   Fake / teacher        Workspace            Cases
                         Tools                Docs
                         Permissions          Journal
                         Recovery             Skills
                         Verification
                              |
          +-------------------+-------------------+
          |                   |                   |
       CODING             RESEARCH             COMPUTER
       Filesystem         Web search            Browser
       Shell              Web fetch             Vision
       Git                External APIs         Mouse/keyboard
       Processes
                              |
                              v
                         OBSERVE / ACT
                              |
                         VERIFY / FAIL
                              |
                         RECOVER / LEARN
                              |
                     CURATE / TRAIN / REUSE
```

That evolution creates a much larger attack surface than the original project architecture describes.

The strongest positive observation is that the project has repeatedly attempted to put **verification gates, quarantine stores, deterministic fixtures, recovery state, provenance, and dataset separation** around learning. Those are the right architectural instincts.

The adversarial problem is that several of those protections exist as *concepts and data structures* but are not yet enforced at the actual trust boundaries.

The most important examples are:

1. **The agent can directly write its own experience memory.**
2. **The agent can directly teach persistent skills without a verification/provenance gate.**
3. **The apprenticeship implementation does not actually pass the teacher's lesson into the student's retry.**
4. **The curation layer can interpret self-authored `success` as verification.**
5. **There are two different learning/curation paths, one of which destructively modifies the raw experience store.**
6. **The synthetic curriculum is deterministic and useful as a harness, but currently much narrower and more repetitive than the term "curriculum" suggests.**
7. **The default runtime has powerful execution capabilities while the default permission posture is permissive.**
8. **The local dashboard is a browser attack surface despite binding only to loopback.**

Claude's audit found 18 findings, including six critical findings. The independent review confirms the central implementation facts behind a substantial portion of those findings, while also identifying additional issues concentrated in the project's most important new capability: **learning**.

This audit therefore treats security and learning integrity as one combined problem:

> **An autonomous agent that can act, write memory, teach itself procedures, curate trajectories, and eventually train on those trajectories needs a stronger boundary between "the agent said/did this" and "Baby-Agent has established that this is knowledge worth preserving."**

---

# 2. Audit Method

The supplied ZIP was extracted and inspected directly.

Repository inventory from the supplied artifact:

- 229 files total
- 151 Python files
- approximately 40,524 Python lines
- 40+ agent/runtime modules
- dedicated skills package
- extensive test suite
- Agent-Lite roadmap through S74 plus later generational work
- apprenticeship, synthetic curriculum, trajectory curation, and training modules

The supplied Claude audit was deliberately treated as a **comparison target rather than an authority**. The purpose of this document is not to reproduce Claude's list. Existing findings are marked where independently corroborated, while additional findings focus heavily on capabilities Claude did not center on.

Dynamic validation performed during this review included test collection against the supplied repository. The suite currently fails during import/collection before normal tests execute in the available interpreter environment, consistent with Claude's F1 observation.

Where this document says **confirmed**, the repository's actual code path was directly inspected and/or dynamically exercised. Where it says **code-confirmed**, the implementation establishes the behavior but a full exploit reproduction was not required for the conclusion. Where it says **risk**, the finding is an architectural weakness that should be tested before being treated as an exploitable vulnerability.

---

# 3. Severity Model

- **Critical** — can defeat a major security, integrity, or trust boundary; or invalidates a central product guarantee.
- **High** — significant security, correctness, learning, data-integrity, or product-validity problem.
- **Medium** — meaningful weakness that can cause incorrect behavior, degraded safety, or misleading results.
- **Low** — cleanup, maintainability, or defense-in-depth issue.

Severity is about impact in the current architecture, not how difficult the eventual fix is.

---

# 4. Claude Findings: Independent Cross-Check

The following Claude findings were independently corroborated at the implementation level:

| Claude ID | Finding | GPT status |
|---|---|---|
| F1 | Python <3.14 import failure from missing typing names | **Confirmed** |
| F2 | `agent_registry()` unconditionally constructs Windows-only computer use | **Confirmed in code** |
| F3 | Workspace boundary bypass through shell execution | **Confirmed in code** |
| F4 | Registry timeout does not bound actual wall-clock execution | **Confirmed in code** |
| F5 | Redirect target is not revalidated by web fetch policy | **Confirmed in code** |
| F6 | Loopback dashboard lacks browser-origin/CSRF boundary | **Confirmed in code** |
| F7 | CaseStore read-modify-write race | **Confirmed in code** |
| F8 | Workspace root `/` containment bug | **Confirmed in code** |
| F9 | Gemini API key placed in URL query string | **Confirmed in code** |
| F10 | Git repository scope can exceed workspace scope | **Confirmed in code** |
| F11 | Non-native provider flattening weakens tool-data provenance | **Confirmed in code** |
| F12 | `curriculum._test_footer` references missing `textwrap` import | **Confirmed** |
| F13 | Blocking provider retry sleeps | **Confirmed in code** |
| F14 | Duplicate `ALLOW_ALL_POLICY` objects | **Confirmed in code** |
| F15 | Permission argument substring matching is weak for shell semantics | **Confirmed in code** |
| F16 | No CI/linter/packaging metadata | **Confirmed** |
| F17 | Tests can pollute live repository store paths | **Confirmed in code** |
| F18 | Top-level architecture documentation no longer matches the application | **Confirmed** |

Claude's findings are therefore not being treated as mere speculative overlap. The supplied source contains the relevant implementation patterns.

The remainder of this audit concentrates on **new findings and deeper implications**, particularly around learning.

---

# 5. Critical Findings

## G1 — The agent can self-authoritative-write experience memory

**Severity:** Critical
**Area:** Learning integrity / memory poisoning
**Status:** Confirmed in code

`MemoryToolkit` exposes `experience_record` directly to the model-facing tool registry.

The tool accepts:

- `goal`
- `outcome`
- `diagnosis`
- `resolution`
- `actions`
- `tags`
- `confidence`

There is no requirement that the supplied experience correspond to a completed `AgentSession`, a verification result, a human intervention, or an independently observed tool trajectory.

The model can therefore conceptually issue a record equivalent to:

```text
experience_record(
    goal="fixed authentication bug",
    outcome="success",
    confidence=1.0,
    actions=["edit_file", "run_tests"]
)
```

The store has no cryptographic or structural reason to know whether those actions actually occurred.

This becomes especially serious because the downstream curation code treats `experience.outcome == "success"` as verification evidence when scoring the trajectory.

The architecture therefore has a trust inversion:

```text
UNTRUSTED MODEL CLAIM
        |
        v
experience_record
        |
        v
persistent memory
        |
        v
curation
        |
        v
"verification" score
        |
        v
potential training data
```

### Why this matters

The product's central promise is learning from actual experience. A model must not be able to manufacture experience merely by writing the right JSON.

### Recommended fix

Separate APIs:

```text
record_observed_session(session)
record_verified_experience(session, verification)
propose_experience(...)
```

The model should only be allowed to **propose** memory. The runtime/harness should be the only writer capable of creating `verified` experience.

`outcome=success` must never itself constitute verification.

Verification should reference an actual verification record:

```json
{
  "verification_id": "...",
  "plan": "...",
  "result": "pass",
  "timestamp": "...",
  "workspace_snapshot": "..."
}
```

---

## G2 — `skill_teach` lets the agent install persistent skills without proving them

**Severity:** Critical  
**Area:** Learning integrity / persistent behavior  
**Status:** Confirmed in code

`SkillToolkit.skill_teach()` validates the JSON shape and then atomically writes the skill file.

The schema checks that:

- the name looks valid
- the goal exists
- the procedure is non-empty
- confidence is within `[0,1]`

It does **not** establish:

- that the procedure actually worked
- that the required tools exist
- that the verification procedure passes
- that the skill came from a teacher
- that the skill came from a verified trajectory
- that the skill has ever been executed successfully
- that the skill is safe
- that the skill was reviewed
- that its confidence is evidence-derived

The tool is also registered as `SAFE_WRITE`, making it materially easier for a permissive runtime to invoke than an execution tool.

This means the agent has a direct durable-learning primitive:

```text
model
  |
  +--> skill_teach
          |
          v
     skills/agent/*.json
          |
          v
     future agent behavior
```

### Recommended fix

`skill_teach` should create a **candidate skill**, not an active skill.

Recommended lifecycle:

```text
PROPOSED
   |
   v
QUARANTINED
   |
   v
TESTED
   |
   v
VERIFIED
   |
   v
PROMOTED
```

Only the promotion step should modify the active skill library.

---

## G3 — Apprenticeship does not actually give the teacher's lesson to the student

**Severity:** Critical  
**Area:** Learning validity  
**Status:** Confirmed in code

The apprenticeship module describes this intended flow:

```text
student attempt
    -> teacher demonstration
    -> student retry with lesson
    -> verification
    -> accept lesson
```

The implementation creates the teacher lesson, checks that it has actions, creates a fresh retry workspace, and then calls:

```text
student_factory(model=None)
```

for the retry.

The `lesson` is not passed to the student provider.

The retry receives the fresh fixture, but the implementation does not apply the teacher's actions to the workspace and does not inject the lesson into the student's context.

This means the system can record an apparently successful apprenticeship where the student succeeded because its provider had independent state or because its factory changed behavior between calls, rather than because it learned anything from the teacher.

The existing test fixture actually hides this problem by making `AttemptFactory` switch behavior after the first call. The factory itself knows how to fix the task. The lab does not transmit the lesson.

### Consequence

The acceptance predicate is currently closer to:

```text
student failed
AND
teacher returned actions
AND
student later passed
```

rather than:

```text
student failed
AND
teacher demonstrated lesson
AND
student received lesson
AND
student independently applied lesson
AND
student passed verification
```

Those are not equivalent.

### Recommended fix

Make lesson delivery explicit and observable:

```python
student_factory(lesson=lesson, model=None)
```

or inject a structured lesson message into the retry session.

Then record exactly which lesson information was available to the student.

The strongest test should use a student that can only solve the second attempt if the lesson is correctly delivered.

---

## G4 — The learning system has multiple competing persistence paths

**Severity:** Critical  
**Area:** Data integrity / architecture  
**Status:** Confirmed in code

There are at least two materially different learning pipelines.

### Path A: S50/session-learning path

`session_learning.curate()` directly modifies the experience store and removes greeting/resume-pattern records. It also writes the resume skill seed.

### Path B: S62/S63 trajectory pipeline

`TrajectoryCurator` reads experience records, classifies and scores them, separates accepted/review/rejected trajectories, and exports candidate lessons/skills for later processing.

These paths have different semantics.

One is destructive and can rewrite the source corpus:

```text
raw experience
     |
     +--> remove records
     |
     +--> write skill
```

The newer path is explicitly designed around separation:

```text
experience
   |
   +--> curated
   +--> review
   +--> rejected
   +--> candidate lessons
   +--> training
```

This creates a serious architectural ambiguity:

> Which pipeline is the authoritative learning pipeline?

A future developer can invoke the older curation path and permanently remove evidence before the newer curation/training pipeline sees it.

### Recommended fix

Make the raw experience store append-only and immutable from the learning pipeline's perspective.

Never delete raw experience as part of curation.

Use:

```text
RAW
 -> FILTERED
 -> CURATED
 -> VERIFIED
 -> TRAINING
```

with references between stages.

---

# 6. High-Severity Learning Findings

## G5 — Curation's verification semantics can be defeated by self-authored outcomes

**Severity:** High  
**Status:** Confirmed in code

The curation scorer contains logic equivalent to:

```text
if experience.outcome == "success":
    verification = 1.0
```

That assumption is valid only if `Experience` objects can originate exclusively from trusted runtime session conversion.

They cannot.

`experience_record` exposes creation to the model.

Therefore:

```text
model says success
      ==
curator sees verification = 1.0
```

This undermines the otherwise good design principle that success should be based on an actual verification gate.

### Recommended fix

Replace `outcome == success` with:

```text
verified_success == True
```

where `verified_success` can only be established by trusted runtime code.

---

## G6 — Curation score is a heuristic quality score, not a proof of learning value

**Severity:** High  
**Area:** Dataset quality  
**Status:** Confirmed in code

The ten-dimensional curation score is useful as a deterministic triage mechanism, but it currently combines dimensions that are not equally evidence-based.

Examples:

- `verification` can be derived from outcome state.
- `tool_use` is based largely on the number of distinct action names.
- `relevance` is based on the number of non-stopword goal terms.
- `diversity` is based on source/project group rarity.
- `robustness` is influenced by the number of failure pairs.

These are measurable, but they are not direct measurements of whether the trajectory teaches a transferable skill.

A long trajectory can score well because it contains many distinct tool names.

A short, highly generalizable solution can score lower because it has fewer actions.

### Recommended fix

Treat the score as **triage metadata**, not as an authority.

Training eligibility should require hard predicates such as:

```text
verified outcome
+ valid trajectory
+ safe/provenance-clean
+ reproducible or replayable
+ not contaminated
+ not duplicate
+ teacher/human gate where required
```

The numeric score should help prioritize review, not determine truth.

---

## G7 — Skill candidates lose the actual arguments needed to reproduce the behavior

**Severity:** High  
**Area:** Skill learning  
**Status:** Confirmed in code

Trajectory curation builds skill candidates using:

```text
procedure = [{step: i, tool: tool_name}, ...]
```

The original structured tool arguments are not retained in the generated procedure.

For example, a trajectory like:

```text
edit_file(path="src/a.py", old_string="x", new_string="y")
run_tests(command="pytest tests/test_a.py")
```

can become effectively:

```text
edit_file
run_tests
```

That preserves the **tool vocabulary**, but not the demonstrated procedure.

### Consequence

The system may learn:

> "use edit_file then run_tests"

instead of:

> "under these conditions, inspect X, modify Y in this manner, then run Z and verify the expected result."

### Recommended fix

Preserve structured step records:

```json
{
  "tool": "edit_file",
  "arguments": {...},
  "observation": {...},
  "verified": true
}
```

Then separately generate a natural-language skill abstraction.

---

## G8 — Skills have no execution-time provenance or version binding

**Severity:** High  
**Area:** Skill correctness  
**Status:** Code-confirmed

A skill records required tools and a textual procedure, but does not bind itself to:

- tool schema version
- agent version
- OS
- project type
- dependency versions
- verification implementation
- source trajectory
- teacher identity
- timestamp/version lineage

A procedure that worked against one tool schema can therefore remain active after the underlying tool changes.

### Recommended fix

Add:

```text
skill_version
source_experience_ids
source_session_ids
created_by
verified_by
runtime_version
tool_schema_versions
platform_constraints
last_verified_at
verification_count
```

---

## G9 — Skill confidence is user/model-supplied rather than evidence-derived

**Severity:** High  
**Status:** Confirmed in code

`Skill.from_dict()` validates that confidence is between 0 and 1, but does not require evidence for the value.

A model can therefore write confidence `1.0` without having successfully executed the skill.

Confidence should be a property calculated from observations, not an unrestricted field supplied by the learner.

---

## G10 — Curriculum difficulty is more cosmetic than behavioral

**Severity:** High  
**Area:** Curriculum validity  
**Status:** Confirmed in code

The curriculum correctly models difficulty as a vector:

```text
reasoning
steps
tools_required
```

However:

- `tools_required` is currently constant at `3`.
- reasoning scales only through a small formula.
- steps scales numerically.
- several fixture generators do not materially change the task with level.
- higher-level bug fixtures primarily add a decoy helper.

Thus level 8 does not necessarily represent a meaningfully harder problem than level 2.

### Recommended fix

Difficulty must alter task structure, not merely metadata.

Examples:

```text
Level 1: one file / obvious defect
Level 2: one file / hidden defect
Level 3: multiple functions / misleading symptom
Level 4: cross-file dependency
Level 5: regression requiring historical reasoning
Level 6: ambiguous failure with competing hypotheses
Level 7: multi-component fix + environment constraint
Level 8: novel task requiring planning + verification + recovery
```

---

## G11 — Synthetic curriculum is useful for regression testing but currently weak evidence of general coding ability

**Severity:** High  
**Area:** Evaluation / curriculum  
**Status:** Architectural finding

The current curriculum contains categories such as:

- bug fix
- feature add
- testing
- refactor
- build repair
- dependency
- regression
- docs

That is a good taxonomy.

The actual fixtures, however, are tiny deterministic Python snippets.

This creates a substantial distribution gap between:

```text
curriculum
```

and:

```text
real repositories
```

The agent can become highly optimized for the benchmark's structural patterns without becoming proportionally better at real-world software work.

### Recommended fix

Keep synthetic curriculum, but explicitly divide evaluation into:

```text
Synthetic curriculum
    = controlled skill acquisition

Repository benchmark
    = integration/generalization

Held-out real projects
    = external validity
```

Never use synthetic curriculum pass rate as the sole evidence that Baby-Agent is improving generally.

---

## G12 — MasteryTracker can change level on repeated reads without new learning evidence

**Severity:** High  
**Area:** Curriculum adaptation  
**Status:** Confirmed in code

`working_level()` computes the current level from recent streaks and then writes the calculated level back into `_levels`.

After enough successes, repeated calls can continue advancing the stored level even though no additional outcomes occurred between calls.

Conceptually:

```text
record 3 successes

working_level() -> level 2
working_level() -> level 3
working_level() -> level 4
...
```

depending on the configured maximum and the retained streak.

The same class of issue can cause repeated reads after a failure streak to repeatedly move the level downward.

### Recommended fix

Level changes should occur only inside `record()` when a new outcome arrives.

`working_level()` should be a pure read.

---

# 7. High-Severity Tool / Runtime Findings

## G13 — Powerful tools are registered broadly even when not required by the task

**Severity:** High  
**Area:** Capability minimization  
**Status:** Confirmed in code

The full agent registry combines:

- filesystem
- execution
- Git
- environment
- verification
- web research
- web fetch
- vision
- processes
- code intelligence
- memory
- skills
- browser
- computer use

The benchmark deliberately uses a lean catalog, which is good. The general runtime does not appear to apply the same principle consistently.

The security principle should be:

> The model receives only the capabilities necessary for the current task.

A coding task should not automatically expose computer control and web fetching if they are unnecessary.

### Recommended fix

Introduce capability profiles:

```text
READ_ONLY
CODE_EDIT
CODE_EXECUTION
WEB_RESEARCH
BROWSER
COMPUTER_USE
MEMORY_AUTHORING
LEARNING_ADMIN
```

Make dangerous capability classes opt-in per session.

---

## G14 — `experience_record` and `skill_teach` are learning-admin operations but are treated like ordinary model tools

**Severity:** High

These operations alter the agent's future behavior, yet they sit in the same general tool mechanism as ordinary memory lookup.

A distinction is needed between:

```text
query memory
```

and:

```text
change what future agents believe
```

The second is effectively a configuration or model-state mutation.

It deserves stronger permission semantics than ordinary SAFE_WRITE.

---

## G15 — Tool output is simultaneously observation, prompt material, and potential training material

**Severity:** High  
**Area:** Prompt injection / dataset poisoning  
**Status:** Code-confirmed architecture risk

The agent consumes tool output from:

- source code
- test output
- Git
- web pages
- documents
- memory
- skills
- browser results
- computer/vision systems

Those outputs can contain instructions.

The system later captures portions of those observations into experience and training records.

Therefore an attacker-controlled repository or webpage can potentially move through this chain:

```text
untrusted content
      |
      v
agent observation
      |
      v
model behavior
      |
      v
experience capture
      |
      v
curation
      |
      v
training data
      |
      v
future model behavior
```

This is a **learning supply-chain attack surface**, not merely a prompt-injection problem.

The training pipeline needs provenance labels that distinguish:

```text
SYSTEM
USER
MODEL
TOOL
WEB
REPOSITORY
TEACHER
HUMAN
VERIFIER
```

and training eligibility should have explicit rules for each source.

---

## G16 — Training records include model-facing observations without a strong contamination boundary

**Severity:** High

The training builder intentionally captures tool calls, result heads, verification failures, and final answers.

That is useful for behavioral cloning.

However, the same fields can contain attacker-controlled text.

The current credential redaction is valuable but is not a general provenance or prompt-injection defense.

A training record should know whether an observation came from:

```text
trusted verifier
trusted filesystem
untrusted repository
untrusted web
model-generated text
teacher-generated text
```

Otherwise a successful trajectory can become a vehicle for teaching arbitrary text encountered during execution.

---

## G17 — Recovery instructions are themselves model-visible control text and can be influenced by failure content

**Severity:** High

Recovery injects system-level instructions such as:

```text
Recovery: ... Last failure: <detail>
```

Failure detail is derived from tool output.

If the tool output contains instruction-like text, the recovery message can become a system-level wrapper around attacker-controlled content.

This is another manifestation of the provenance-boundary issue.

### Recommended fix

Do not interpolate raw tool output into privileged instruction messages.

Represent it structurally:

```json
{
  "type": "recovery_event",
  "failure_kind": "verification",
  "detail": "..."
}
```

and render it inside an explicitly delimited untrusted-data section.

---

# 8. Medium-Severity Learning Findings

## G18 — Memory retrieval is keyword/substrings, not semantic or structural retrieval

**Severity:** Medium

Experience, skill, and some document retrieval paths use token overlap / substring matching.

This is intentionally dependency-light and deterministic, but it creates predictable errors:

- `test` can match unrelated words containing the sequence.
- `api` can match many unrelated contexts.
- synonyms do not match.
- semantic equivalence does not match.
- project context is weakly represented.

This is acceptable for an MVP, but it should not be described as robust retrieval.

---

## G19 — Memory source scores are fixed and not calibrated against usefulness

**Severity:** Medium

`MemoryLayer` gives different source families fixed score ranges.

That creates an implicit hierarchy such as:

```text
experience > case > docs > journal
```

rather than measuring whether a particular result is actually more relevant.

A highly relevant document can lose to a weak experience merely because of source weighting.

This is a retrieval policy, not an evidence ranking.

---

## G20 — Experience deduplication by normalized goal can collapse distinct lessons

**Severity:** Medium

`ExperienceStore.record()` reinforces an existing experience when normalized goals match.

This is sensible for repeated identical tasks but dangerous when two tasks have the same goal wording but materially different:

- project context
- failure
- environment
- solution
- tool path

The benchmark works around this by suffixing goals with session IDs, which is evidence that the dedupe mechanism is already known to be lossy.

The durable model should use a richer experience identity:

```text
goal + project context + failure signature + verification context
```

rather than goal text alone.

---

## G21 — Experience records do not preserve enough trusted workspace state for replay

**Severity:** Medium

Trajectory capture deliberately bounds data, which is good for size.

But a training trajectory that contains only tool arguments and the first line of each result cannot necessarily reproduce the conditions under which the action succeeded.

This is especially problematic for:

- dependency fixes
- environment issues
- Git behavior
- race conditions
- multi-file changes
- generated files
- configuration state

The project should distinguish:

```text
behavioral trace
```

from:

```text
replayable demonstration
```

They are not the same thing.

---

## G22 — Curriculum generation can exhaust its retry budget while returning fewer tasks than requested

**Severity:** Medium

`SyntheticCurriculum.generate()` attempts up to `count * 20` candidate generations and silently returns whatever was generated if deduplication prevents reaching `count`.

A caller requesting 100 tasks can therefore receive fewer than 100 without an explicit failure.

That is particularly dangerous for experiments where dataset size is treated as a controlled variable.

### Recommended fix

Return:

```text
requested
produced
skipped
exhausted
```

and optionally raise when `strict=True`.

---

## G23 — Curriculum coverage measures task counts, not competency coverage

**Severity:** Medium

`coverage()` counts how many tasks mention each skill.

It does not measure:

- independent task patterns
- difficulty distribution
- success rate by skill
- recovery rate by skill
- transfer to unseen variants
- performance after teaching

Ten near-identical Python tasks can therefore look like strong coverage.

A real mastery matrix should include:

```text
skill × difficulty × task family × novelty × outcome
```

---

## G24 — No explicit catastrophic-learning rollback mechanism

**Severity:** Medium / potentially High as the system matures

The project has quarantine and curation concepts, but an active skill or training corpus can still become wrong if a bad item passes the current gates.

There should be an explicit mechanism to say:

```text
Skill X was promoted
Skill X caused regressions
Revoke Skill X
Restore previous version
Identify derived training records
```

This becomes increasingly important once Baby-Agent starts training checkpoints from its own accumulated data.

---

# 9. Medium-Severity Runtime Findings

## G25 — `set_env` is an unusually powerful capability for a model-facing tool

**Severity:** Medium / High depending on deployment

Claude correctly identified environment inheritance as dangerous.

The deeper issue is that environment mutation is effectively a second command-execution language.

Variables such as:

```text
PATH
PYTHONPATH
GIT_SSH_COMMAND
LD_PRELOAD
```

can alter what later commands execute.

Therefore treating `set_env` as ordinary command configuration understates its capability.

It should be treated as privileged execution configuration.

---

## G26 — Process management expands the agent's authority beyond individual commands

**Severity:** Medium

The runtime exposes process management in addition to command execution.

That means the agent can potentially:

```text
start process
   |
   v
process survives original tool call
   |
   v
later inspect/restart/stop
```

This needs explicit ownership tracking:

```text
process_id
session_id
parent_pid
created_by_agent
created_at
workspace
```

Without ownership, process management becomes a host-level capability rather than a workspace-level capability.

---

## G27 — Broad exception swallowing can turn real security/data failures into "empty memory"

**Severity:** Medium

Several memory/retrieval components deliberately catch broad exceptions and degrade to empty results.

This is good for availability but dangerous for correctness when the agent interprets:

```text
memory search returned nothing
```

as:

```text
there is no relevant memory
```

when the actual condition was:

```text
memory subsystem crashed
```

The result should preserve a structured degraded state.

---

# 10. Curriculum Audit

## What is good

The curriculum has several strong design decisions:

- deterministic seeded generation
- explicit categories
- explicit levels
- skill labels
- known failure modes
- verification through the existing evaluation harness
- deduplication of repeated normalized goals
- a separate mastery tracker
- fixture-based tasks rather than unconstrained generated tasks

The fixtures-first philosophy is particularly valuable because it makes experiments reproducible.

## What is weak

The current curriculum is closer to a **deterministic coding exercise generator** than a broad autonomous-agent curriculum.

It heavily emphasizes:

```text
small Python module
+ simple test
+ direct defect/feature
+ deterministic verification
```

It does not yet sufficiently test:

- repository navigation
- ambiguous requirements
- multiple plausible fixes
- dependency conflicts
- real build systems
- configuration drift
- unfamiliar languages
- long-horizon tasks
- external documentation
- Git history reasoning
- merge conflicts
- regression investigation
- partial prior work
- hidden environmental constraints
- adversarial repository content
- safe handling of secrets
- tool failure recovery
- browser research
- visual debugging
- multi-agent disagreement

That is fine for early training, but the curriculum should not be mistaken for a comprehensive measure of agent competence.

---

# 11. Skills Audit

## Current skill architecture

The skill system is conceptually clean:

```text
Skill
  |
  +-- goal
  +-- description
  +-- required_tools
  +-- preconditions
  +-- procedure
  +-- verification
  +-- failure_modes
  +-- examples
  +-- confidence
  +-- tags
```

The deterministic retrieval model is simple and testable.

The problem is that **skill storage is already behaviorally significant**, while its trust model remains lightweight.

The key distinction needed is:

```text
Skill candidate
!=
Verified skill
!=
Active skill
```

The repository currently blurs these states.

### Proposed state machine

```text
              +----------------+
              | OBSERVED       |
              +-------+--------+
                      |
                      v
              +----------------+
              | PROPOSED       |
              +-------+--------+
                      |
                      v
              +----------------+
              | QUARANTINED    |
              +-------+--------+
                      |
              v       v
          TEST FAIL  TEST PASS
              |       |
              |       v
              |  +-----------+
              |  | VERIFIED  |
              |  +-----+-----+
              |        |
              |        v
              |  +-----------+
              |  | PROMOTED  |
              |  +-----+-----+
              |        |
              |        v
              |  +-----------+
              +->| REVOKED   |
                 +-----------+
```

This would give Baby-Agent an actual memory/skill lifecycle rather than merely a JSON file directory.

---

# 12. Learning Architecture Audit

The intended learning loop appears to be:

```text
experience
   |
   v
curation
   |
   v
lesson candidate
   |
   v
training data
   |
   v
model/checkpoint
   |
   v
better agent
   |
   v
new experiences
```

That is a legitimate experimental direction.

However, the most important missing property is **causal attribution**.

Baby-Agent needs to know whether an improvement came from:

- the teacher
- retrieved memory
- a skill
- model escalation
- repeated attempts
- benchmark familiarity
- random variation
- a changed prompt
- a changed model
- a changed tool catalog
- actual training

Without that, a rising benchmark score does not establish that learning occurred.

### Recommended experimental design

Every learning experiment should have an A/B structure:

```text
A: baseline agent
B: agent + lesson/memory/skill/training

same task distribution
same held-out tasks
same model generation settings
same tool budget
same verification
```

Measure:

- first-attempt success
- eventual success
- iterations
- tool calls
- recovery rate
- regression rate
- transfer to unseen tasks
- retention after time
- performance on unrelated tasks

This turns "Baby-Agent learned" into an experimentally testable statement.

---

# 13. Training Pipeline Audit

The training pipeline has several good safeguards:

- it consumes curated data rather than blindly consuming raw experience
- it distinguishes eligible from ineligible trajectories
- it separates step-trainable records
- it excludes invalid classifications
- it preserves verification-failure sequences
- it renders the runtime tool protocol
- it keeps a report of exclusions
- it deliberately leaves preference optimization empty until paired data exists

Those are strong foundations.

The primary remaining concern is **data provenance**.

The training corpus should never merely answer:

> Was this trajectory accepted?

It should answer:

> Why was this trajectory accepted, what trusted evidence established that fact, what untrusted material did it contain, and what future behavior could be contaminated by that material?

### Minimum provenance fields

```json
{
  "source_type": "autonomous_session",
  "source_ids": ["..."],
  "verification_id": "...",
  "workspace_snapshot": "...",
  "model": "...",
  "teacher": null,
  "human_intervention": false,
  "external_content_seen": true,
  "external_domains": [],
  "secret_scan": "pass",
  "prompt_injection_scan": "reviewed",
  "curation_version": "...",
  "runtime_version": "...",
  "tool_schema_version": "..."
}
```

---

# 14. Overall Application Audit

## 14.1 Architecture maturity

The project has moved beyond a toy agent.

It now contains enough subsystems that the primary engineering risk is no longer simply "can we add another capability?"

It is:

> **Can the capabilities remain composable without one subsystem silently bypassing another subsystem's guarantees?**

Examples already visible:

```text
Workspace boundary
       X
shell execution

Verification
       X
experience_record self-report

Teacher demonstration
       X
student retry delivery

Raw experience integrity
       X
legacy destructive curation

Skill verification
       X
skill_teach direct persistence

Tool provenance
       X
flattened provider messages
```

These are all **seam failures**.

That should become the primary architectural review lens for future sprints.

---

# 15. What Holds Up

An adversarial audit should not pretend everything is broken.

Several parts of the design are genuinely strong.

### 15.1 Workspace PathPolicy

Claude's assessment is supported by the source: the workspace path-policy design is substantially more careful than a naive path-prefix check.

The important protections include:

- parent traversal rejection
- resolve-before-containment
- symlink-aware containment
- protected locations
- null-byte rejection
- Windows normalization
- exclusion handling

F8 is a localized root-path bug rather than evidence that the overall design is wrong.

### 15.2 Git argument construction

The Git implementation avoids the obvious shell-injection class through argv lists and explicit separators.

The main weakness is repository scope, not command injection.

### 15.3 Verification-first benchmark design

The benchmark correctly attempts to distinguish:

```text
model says "done"
```

from:

```text
verification proves done
```

That principle should be extended into the memory and skill systems.

### 15.4 Recovery state machine

The explicit recovery ladder is a good foundation:

```text
retry
 -> alternate
 -> environment check
 -> escalation
 -> human/terminate
```

The concept of deterministic failure signatures is especially useful.

### 15.5 Dataset separation intent

The project explicitly distinguishes experience, curated trajectories, and training data.

That is exactly the right direction.

The main problem is enforcement and the presence of older competing paths.

### 15.6 Deterministic fixtures

The synthetic curriculum and benchmark fixtures are excellent for controlled regression testing.

They should remain even after real-project evaluation is introduced.

---

# 16. Consolidated Finding Table

| ID | Severity | Area | Finding | Status |
|---|---|---|---|---|
| G1 | Critical | Learning | Agent can self-write authoritative experience | Confirmed |
| G2 | Critical | Learning | Agent can persist skills without verification | Confirmed |
| G3 | Critical | Apprenticeship | Teacher lesson is not actually delivered to retry | Confirmed |
| G4 | Critical | Data architecture | Multiple competing learning persistence paths | Confirmed |
| G5 | High | Curation | Self-authored success can become verification | Confirmed |
| G6 | High | Curation | Numeric quality score is not proof of learning value | Confirmed |
| G7 | High | Skills | Skill candidates lose structured action arguments | Confirmed |
| G8 | High | Skills | No runtime/tool/version provenance for skills | Code-confirmed |
| G9 | High | Skills | Confidence is not evidence-derived | Confirmed |
| G10 | High | Curriculum | Difficulty is partly metadata rather than behavioral | Confirmed |
| G11 | High | Curriculum | Synthetic tasks are weak evidence of generalization | Architectural |
| G12 | High | Curriculum | Mastery level can drift on reads | Confirmed |
| G13 | High | Tools | Broad capability registration violates least privilege | Confirmed |
| G14 | High | Learning | Memory-authoring tools lack privileged semantics | Confirmed |
| G15 | High | Security | Untrusted tool output can enter the learning supply chain | Architectural |
| G16 | High | Training | Captured observations lack strong provenance boundary | Architectural |
| G17 | High | Recovery | Failure text can become privileged control text | Code-confirmed |
| G18 | Medium | Retrieval | Keyword retrieval is shallow | Confirmed |
| G19 | Medium | Retrieval | Fixed source weights are not calibrated relevance | Confirmed |
| G20 | Medium | Memory | Goal-only dedupe can collapse distinct experiences | Confirmed |
| G21 | Medium | Training | Bounded traces are not necessarily replayable demonstrations | Architectural |
| G22 | Medium | Curriculum | Generation can silently return fewer tasks than requested | Confirmed |
| G23 | Medium | Curriculum | Coverage counts tasks rather than competencies | Confirmed |
| G24 | Medium | Learning | No explicit catastrophic-learning rollback path | Architectural |
| G25 | Medium/High | Execution | Environment mutation is a second execution language | Confirmed |
| G26 | Medium | Processes | Process authority lacks strong ownership semantics | Architectural |
| G27 | Medium | Reliability | Broad exception handling can hide memory failures | Confirmed |

Claude findings F1–F18 are tracked separately above and are not counted in this new-finding table.

---

# 17. Recommended Remediation Order

## Phase 0 — Make the repository auditable

Fix first:

1. F1 Python import failures
2. F2 platform registry failure
3. F12 undefined `textwrap`
4. F16 CI + pyflakes + multi-platform test matrix
5. F18 architecture documentation drift

Nothing else is easy to trust while the repository cannot reliably execute its own tests across supported environments.

---

## Phase 1 — Break the dangerous execution chain

6. F3 execution permission default
7. F6 dashboard CSRF/origin/token boundary
8. F5 redirect SSRF
9. F9 API key handling
10. F10 Git scope
11. F4 actual timeout enforcement
12. F25 environment mutation controls
13. F26 process ownership

The goal is:

```text
hostile webpage
      X
local dashboard
      X
agent
      X
unrestricted host execution
```

---

## Phase 2 — Establish a real learning trust boundary

This is the most important Baby-Agent-specific phase.

14. **G1:** make model-created experiences proposals only
15. **G2:** make model-created skills proposals only
16. **G3:** fix apprenticeship lesson delivery
17. **G4:** retire/descope the competing destructive learning path
18. **G5:** make verification evidence mandatory
19. **G8/G9:** add skill provenance and evidence-derived confidence
20. **G15/G16:** establish provenance for external/untrusted content

Target architecture:

```text
                  AGENT
                    |
          +---------+---------+
          |                   |
       OBSERVE             PROPOSE
          |                   |
          v                   v
     EXPERIENCE          CANDIDATE SKILL
          |                   |
          +---------+---------+
                    |
                    v
              TRUST GATE
                    |
       +------------+------------+
       |                         |
    VERIFY                     REVIEW
       |                         |
       +------------+------------+
                    |
                    v
                PROMOTE
                    |
          +---------+---------+
          |                   |
       MEMORY              SKILLS
          |                   |
          +---------+---------+
                    |
                    v
                TRAINING
```

---

## Phase 3 — Make learning experimentally meaningful

21. G10 difficulty redesign
22. G11 real-project/held-out evaluation
23. G12 mastery tracker correction
24. G22 strict curriculum generation accounting
25. G23 competency coverage
26. G24 skill/model rollback
27. A/B learning experiments

The key objective is to distinguish:

```text
"the benchmark score went up"
```

from:

```text
"the agent acquired a transferable capability"
```

---

# 18. Proposed Learning Integrity Contract

Before Baby-Agent is allowed to call itself a system that learns from mistakes, I recommend adopting this contract:

### Rule 1 — The agent may propose knowledge, not certify it

```text
MODEL -> PROPOSAL
RUNTIME/VERIFIER -> CERTIFICATION
```

### Rule 2 — A successful statement is not evidence of success

```text
"I fixed it"
```

must never equal:

```text
verified_success
```

### Rule 3 — Every promoted lesson has provenance

Every lesson must answer:

```text
Where did this come from?
Who/what verified it?
What task produced it?
What tools were used?
What environment was involved?
Has it been independently replayed?
```

### Rule 4 — Raw experience is immutable

Curation must never destroy the evidence it is supposed to curate.

### Rule 5 — Skills are versioned artifacts

A skill must be revocable and traceable.

### Rule 6 — Training data is a privileged derivative

Training data is not just another export. It is a transformation of the agent's future behavior and therefore requires the strongest provenance gate.

### Rule 7 — External content is untrusted by default

Repository files, websites, browser pages, test output, and documentation can contain instructions but must remain data.

### Rule 8 — Learning must be tested against held-out tasks

A lesson that only improves the exact task that produced it has not demonstrated transfer.

### Rule 9 — Improvement must survive ablation

If removing the lesson/memory/skill causes no performance difference, the system has not demonstrated that the artifact was responsible for the improvement.

### Rule 10 — The agent must be able to unlearn

Every learned artifact needs:

```text
version
lineage
verification history
regression history
rollback
```

---

# 19. Definition of "Actually Learned"

For this project, a stronger definition would be:

> **Baby-Agent has learned a capability when a verified training or teaching intervention causes measurable improvement on previously unseen tasks from the same competency family, without requiring the original trajectory or task-specific hardcoding, while maintaining or improving regression performance on unrelated held-out tasks.**

That is much stronger than:

```text
session succeeded
```

or:

```text
model generated a lesson
```

or:

```text
training file contains the trajectory
```

---

# 20. Final Assessment

Baby-Agent is an unusually interesting state for an experimental agent project because the original QA-memory idea has grown into something much larger.

The repository now contains most of the conceptual ingredients for an autonomous learning agent:

```text
agency
memory
skills
verification
recovery
curriculum
teachers
trajectory capture
curation
training export
model routing
```

The central problem is no longer missing capability.

It is **trust between capabilities**.

The system has repeatedly implemented the right idea at the local level:

```text
verification gate
permission gate
curation gate
quarantine store
skill schema
recovery state
```

but several seams allow a stronger capability to bypass the weaker one:

```text
agent -> memory
agent -> skills
teacher -> student
experience -> verification
raw data -> training
web/repo -> learning
```

That is the main architectural lesson from this audit.

### The most important next architectural change

Do not add another learning feature yet.

First establish a **Learning Trust Boundary**.

Once that exists, the rest of the roadmap becomes much more scientifically useful because Baby-Agent can distinguish:

```text
what happened
      |
      v
what the agent claims happened
      |
      v
what was actually verified
      |
      v
what a curator thinks is useful
      |
      v
what was promoted into knowledge
      |
      v
what was used for training
      |
      v
what demonstrably improved the next generation
```

That chain is the real product.

The current repository has most of the pieces. The adversarial finding is that the chain is **not yet sealed**.

---

# Appendix A — Audit Focus for the Next Red-Team Pass

The next implementation-level attack pass should specifically attempt:

1. Model-created fake successful experience -> curated training record.
2. Model-created fake high-confidence skill -> active skill behavior.
3. Teacher lesson that is intentionally necessary -> determine whether apprenticeship actually transfers it.
4. Malicious repository text -> memory -> curated dataset -> training record.
5. Malicious web text -> recovery message -> privileged instruction influence.
6. Skill that changes behavior after its source tool schema changes.
7. Revoked skill still being retrieved or used.
8. Cross-session memory contamination.
9. Cross-session skill contamination.
10. Concurrent experience/skill writes.
11. Training corpus containing secrets missed by current regexes.
12. Benchmark overfitting by generating near-duplicate curriculum tasks.
13. MasteryTracker manipulation through repeated reads.
14. A/B experiment where a lesson is removed to verify causal impact.
15. A held-out repository benchmark after curriculum training.
16. Full browser-to-agent exploit chain against the local dashboard.
17. Full webfetch redirect/rebinding attack without monkeypatching policy checks.
18. Process escape through detached/background children.
19. Environment-variable capability escalation.
20. Git scope escape through nested repositories, worktrees, and parent repositories.

---

# Appendix B — Audit Philosophy

The most important adversarial question for Baby-Agent is not:

> "Does this function work?"

It is:

> **"Can a lower-trust component convince a higher-trust component that something has been proven when it has only been claimed?"**

That question should be applied to every future subsystem:

```text
model
memory
skills
teacher
curriculum
verification
training
browser
web
filesystem
Git
processes
UI
```

If the answer is yes, the boundary needs another layer of evidence.


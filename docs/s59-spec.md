# S59 — Agent Apprenticeship Lab: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S59. Builds on S31–S58. One slice, stdlib only, no CLI changes.

## Overview

The bridge between a working Agent-Lite and a future trained
generation: a lab where teacher agents demonstrate software tasks,
the runs are verified, and ACCEPTED lessons enter baby-agent's memory
— never automatically trusted.

**Scale honesty:** this slice lands the LAB MACHINERY (teacher
abstraction, scripted fake teacher, session contract, curation gate)
hermetically. Real teacher providers (Gemini, opencode) plug into the
same TeacherProvider surface in a later slice; no network calls in
tests, ever.

## Module layout

```text
qacompanion/agent/apprenticeship.py   # TeacherProvider + lab + curator gate
tests/test_agent_apprenticeship.py
```

## TeacherProvider (ABC)

```text
TeacherProvider (ABC)
    name -> str
    teach(task) -> Lesson
        task: {goal, workspace_files: {name: content}, verify_command?}
        Lesson: {explanation, actions: [{tool, arguments}...]} — the
        teacher narrates then demonstrates via the same tool names the
        agent uses
ScriptedTeacherProvider   deterministic fake (the test backbone)
```

The Lesson shape mirrors S57's AutoFix pattern: teachers demonstrate
via real tool calls against a real workspace — not chat text. A
teacher that can't produce actions can't teach here.

## ApprenticeshipLab

```text
ApprenticeshipLab(store, student_factory, verifier)
    .run_session(task, teacher) -> ApprenticeshipRecord
```

Per session (the contract):

```text
session_id, task_name, teacher_name, student_name, started_at
status: completed | failed | rejected
student: AgentSession            (the STUDENT attempts the task first
                                  — apprenticeship means watching a
                                  better way, so both trajectories
                                  are kept)
teacher_lesson: Lesson
student_report: BenchmarkReport-like metrics
verified: bool (S41 gate on the student's post-lesson attempt)
accepted: bool (curation gate)
lessons_extracted: [strings]
```

Flow per session: student attempts task → teacher demonstrates →
student retries with the lesson → S41 verification gate → curation
gate → ACCEPT records the verified lesson (S50) → REJECT discards
with a reason. **Store discipline (test-found):** attempts run against
a QUARANTINE store (attempt_store — recorded honestly but separate);
the MAIN store only receives ACCEPTED lessons, under a distinct goal
so store goal-dedupe cannot merge the lesson tag away. Verification
failure → REJECTED, never in main memory.

## Curator gate (never auto-trust)

- ACCEPT requires the S41 verification to PASS on the student's
  post-lesson attempt — "teacher said it" is not evidence.
- REJECT reasons recorded: verification_failed, teacher_failed
  (teacher's own demo didn't verify).
- `lab.report()` → sessions, accepted, rejected, by_teacher.

## Testing strategy (tests/test_agent_apprenticeship.py)

- Scripted teacher emits correct actions; student fake fails first
  attempt then follows the lesson → ACCEPT with verified=True.
- Teacher whose demo fails verification → REJECTED, nothing stored.
- Student that fails even after the lesson → REJECTED.
- Session contract completeness; report counts by teacher.
- Registry unchanged (the lab is harness-level, not a tool).

Expected suite growth: 1440 → ~1455 OK.

## Exit criteria (from ROADMAP-agentlite.md §S59)

Teacher assigned a structured task completes a session; the student
observes, retries, and the verified lesson enters memory; unverified
runs are rejected; report counts. Full suite green; preflight clean.

# S111 — Task+listing reinforcement: the attention-vs-capability A/B
# (measurement slice, no training)

## Question

Gen-23 forensics: on explore-qa the listing IS in context (S102.4
disproved context loss) yet the model guesses drill-fixture file
names instead of opening what the listing shows. Is that an
ATTENTION problem (fixable at inference) or a CAPABILITY limit
(7B, needs a stronger base)? The user's proposal — re-prompt the
model with the directory and the question every turn — is the
direct probe, and the plumbing exists: the loop's injectable
context_builder (S56) with the run_benchmark passthrough (S64).

## Design

`TaskListingReminder` (context.py): a context builder with the
loop's `build(session, offered_tools, native_tools)` interface that
returns `session.messages` PLUS one bounded user-role note,
rebuilt fresh each turn (no accumulation, no prompt explosion):

    Task: <the goal verbatim>
    Most recent directory listing (open files that exist in it):
    <the latest successful list_directory output, bounded>

User-role deliberately: it reads as the operator re-asking the
question with the map attached — the exact proposal — and is
bridge-safe (S75.10's flattening fences tool turns; a trailing
user note is plain content).

`run_evaluation` gains `context_builder=None` passthrough (additive;
the A/B harness uses it exactly as the ep0.5 A/B does).

## The A/B

explore-qa only, temp 0 / seed 42, n=3, OLLAMA_TIMEOUT=600:
- ep20-q4 (champion, untrained on QA) with vs without the reminder
  — the without arm is the gen-23 verdict (0/3, already recorded).
- ep23-q4 (the answer-QA-trained model) with the reminder.
6 new runs. Outcomes:
- explore-qa moves for either model -> the wall was attention;
  bake the reminder into QA-shaped sessions at inference, rung 7
  opens without retraining.
- no movement with the map re-injected every turn -> capability
  limit confirmed with evidence; the 9B/base conversation proceeds
  on that evidence.

## Honest bounds

- The reminder is a measurement instrument first; IF it works, its
  production form (which sessions get it, budget interaction with
  the S56 ContextBuilder) is its own follow-up decision.
- Substring fact-containment still judges grounding, not quality.

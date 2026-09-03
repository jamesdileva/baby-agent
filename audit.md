# Baby-Agent Repository Audit & Agent-Lite Evolution Plan

**Document:** `audit.md`  
**Project:** Baby-Agent  
**Purpose:** Audit the current repository, identify what already exists, define what is missing for an Agent-Lite autonomous coding agent, and establish a replacement/extension sprint roadmap with explicit verification end goals.

---

# 1. Executive Summary

Baby-Agent is substantially further along than a typical "agent from scratch" project.

The repository already contains several important subsystems that are highly reusable for an Agent-Lite architecture:

- Persistent failure/case memory
- Failure signatures and lookup
- Accuracy/confidence tracking
- Automated QA capture
- Flaky/regression detection
- Environment/preflight diagnosis
- Declarative skills
- Python skill modules
- Case merging
- Robust I/O
- Documentation digestion/search
- Archive/document mining
- Journal/learning records
- Escalation
- Weak-subject/candidate detection
- An Ollama integration
- Retrieval-augmented question answering
- A primitive model/tool loop
- Tool registration/dispatch
- Continuous directory watching
- Training-data export
- Extensive tests
- Git history documenting the completed milestones

The repository therefore already has a strong **memory + learning + QA brain**.

The major missing capability is the **agent runtime that can act on a workspace**.

Today, the system is much closer to:

```text
Knowledge / QA Companion
        +
Local LLM
        +
Primitive research tools
```

The desired Agent-Lite system is:

```text
                    BABY-AGENT
                        |
          +-------------+-------------+
          |             |             |
       MODEL          AGENT         MEMORY
       BRAIN         RUNTIME         BRAIN
          |             |             |
       Ollama/API    Agent Loop     Cases
                     Workspace      Docs
                     Tools          Journal
                     Permissions    Skills
                        |
                  +-----+------+
                  |            |
              Filesystem    Terminal
                  |            |
                  +-----+------+
                        |
                     Project
                        |
                   Observe/Fix
                        |
                      Learn
```

The recommended strategy is **not to throw away the existing repository**.

Instead, Baby-Agent should be evolved so that the existing QA/learning system becomes the agent's long-term memory and diagnostic intelligence, while a new Agent Runtime gives the model the ability to inspect, modify, execute, test, and learn from real projects.

---

# 2. What "Agent-Lite" Means in This Project

"Agent-Lite" is used here as a project-specific term, not as a formal model category.

For Baby-Agent, an Agent-Lite is:

> A lightweight LLM-powered autonomous agent that can receive a goal, inspect a bounded workspace, use structured tools, observe results, modify the workspace, run verification commands, recover from failures, and persist useful lessons.

The minimum useful loop is:

```text
GOAL
  |
  v
CONTEXT
  |
  v
MODEL
  |
  v
TOOL CALL
  |
  v
TOOL EXECUTION
  |
  v
OBSERVATION
  |
  v
MODEL
  |
  +----> more tools
  |
  v
VERIFICATION
  |
  +----> failure -> diagnose -> fix -> verify
  |
  v
COMPLETE
  |
  v
LEARN
```

The key distinction is that Baby-Agent must eventually be able to **do things**, not merely explain how a human should do them.

---

# 3. Current Repository Assessment

## 3.1 Overall characterization

The current repository should be thought of as:

```text
Baby-Agent v0.x
|
+-- QA / Failure Intelligence
+-- Persistent Knowledge
+-- Document Retrieval
+-- Learning / Training Pipeline
+-- Ollama Integration
+-- Primitive Tool Loop
+-- Resident Observation
```

It is not yet a full autonomous coding agent.

The missing layer is:

```text
Agent Runtime
|
+-- Session state
+-- Workspace
+-- Tool execution
+-- Filesystem actions
+-- Terminal actions
+-- Git actions
+-- Permission policy
+-- Agent loop
+-- Event stream
+-- Cancellation / timeout
```

---

# 4. Existing Capabilities

## 4.1 Persistent Case Memory

The repository contains persistent case storage using JSONL.

Cases contain structured information such as:

- ID
- Failure signature
- Error excerpt
- Number of times encountered
- Last seen timestamp
- Confirmation information

This is valuable because it is not merely conversational memory.

It represents reusable operational experience.

Conceptually:

```text
Failure
  |
  v
Normalize
  |
  v
Signature
  |
  v
Case Store
  |
  +--> Known
  +--> Unknown
  +--> Confidence
```

This should become part of the Agent Runtime's memory layer rather than being replaced.

---

# 5. Failure Intelligence

The repository includes failure signature and lookup functionality.

Important existing concepts include:

- Signature generation
- Case lookup
- Case persistence
- Accuracy tracking
- Reporting
- Case merging

This gives Baby-Agent a foundation for recognizing recurring problems.

Future autonomous coding behavior can exploit this:

```text
Build failure
    |
    v
Generate signature
    |
    v
Search historical cases
    |
    +--> Known failure
    |       |
    |       v
    |    Known diagnosis
    |
    +--> Unknown
            |
            v
         Diagnose
            |
            v
         Fix
            |
            v
      Record new case
```

This is one of the strongest reasons to evolve the existing project instead of starting over.

---

# 6. QA Automation

The existing QA system includes automated command execution/capture.

The important distinction for the future is:

### Existing

```text
QA system
    |
    v
Execute command
    |
    v
Capture result
    |
    v
Analyze failure
```

### Future

```text
Agent
    |
    v
run_command tool
    |
    v
QA execution subsystem
    |
    v
Capture result
    |
    v
Agent observes result
```

The existing QA execution code can therefore become an implementation component underneath the Agent Tool Executor.

---

# 7. Flaky / Regression / Environment Intelligence

Existing milestones cover concepts including:

- Flaky detection
- Regression detection
- Environment diagnosis
- Preflight checks

These should remain separate from the core agent loop.

The architecture should be:

```text
Agent Runtime
      |
      +--> Build/Test
      |
      v
QA subsystem
      |
      +--> environment
      +--> regression
      +--> flaky detection
      +--> failure analysis
```

The agent should consume structured results rather than needing to understand the internals of the QA subsystem.

---

# 8. Skills

Baby-Agent already contains a declarative skill system and Python skill-module concepts.

Skills should eventually become a higher-level layer above primitive tools.

For example:

```text
Primitive tools:
    read_file
    write_file
    run_command
    search_code

Skill:
    "Create React App"
```

A skill can describe:

- Preconditions
- Required tools
- Procedure
- Verification
- Known failure modes
- Expected outputs
- Learned improvements

This creates an important distinction:

```text
TOOLS
    = what the agent can do

SKILLS
    = reusable ways of accomplishing things
```

---

# 9. Documentation Digestion / Retrieval

Baby-Agent already has document digestion and a persistent digest.

The system can ingest documentation and retrieve relevant information.

This is an early RAG-style subsystem.

Current conceptual flow:

```text
Documents
   |
   v
Digest
   |
   v
Persistent knowledge
   |
   v
Search
   |
   v
LLM context
```

This should become:

```text
Agent Goal
   |
   +--> Project files
   +--> Historical cases
   +--> Digested documentation
   +--> Journal
   +--> Skills
   |
   v
Context Builder
   |
   v
Model
```

---

# 10. Journal / Learning Records

The repository already treats observations and learning as persistent information.

The future agent should add agent-session events to this system.

Potential future records:

```text
goal
plan
tool_call
tool_result
error
diagnosis
fix
verification
lesson
```

This creates a trajectory that can later become:

- Debugging history
- Human-readable session history
- Training data
- Evaluation data
- Regression cases
- Future Baby-Agent generations

---

# 11. Escalation

The existing escalation concept is important.

The current philosophy is essentially:

```text
Low confidence
     |
     v
Draft question
     |
     v
External/live assistance
     |
     v
Answer
     |
     v
Distill into reusable knowledge
```

This can eventually become a general agent escalation mechanism:

```text
Agent stuck
   |
   +--> Search memory
   |
   +--> Search docs
   |
   +--> Try another strategy
   |
   v
Escalate
   |
   +--> Larger model/API
   +--> Human
   +--> Future specialist agent
   |
   v
Solution
   |
   v
Teach Baby-Agent
```

---

# 12. Ollama Integration

The repository already contains an Ollama bridge.

The existing system supports local LLM question answering and retrieval-augmented responses.

A local model is therefore already part of the project.

The important architectural decision is:

> Ollama is the model runtime/provider, not the user interface.

Ollama can run a model such as a local coding-capable model.

The application around Ollama can be a GUI, terminal UI, HTTP service, Electron app, or another client.

Recommended architecture:

```text
                 BABY-AGENT APP
                      |
                ModelProvider
                 /          \
                /            \
        OllamaProvider    OpenAIProvider
             |                 |
          Ollama            API
             |                 |
        Local model       Cloud model
```

The agent should not be tightly coupled to Ollama.

---

# 13. Important UI Clarification

## Does the UI come from Ollama?

**No.**

Ollama is responsible for serving/running the model.

It does not need to be the application UI.

The UI should belong to Baby-Agent.

For this project, the preferred direction is:

```text
Electron
   +
React
   +
TypeScript
```

with Baby-Agent's Python backend/runtime underneath.

A possible architecture:

```text
                    BABY-AGENT DESKTOP
                         |
             +-----------+-----------+
             |                       |
          React UI              Electron Shell
             |                       |
             +-----------+-----------+
                         |
                    Local API / IPC
                         |
                    Agent Runtime
                         |
                +--------+--------+
                |                 |
          Model Provider      Tool System
                |                 |
             Ollama          Workspace
                              Files
                              Shell
                              Git
```

This would allow the user to stop typing commands directly into a terminal for normal operation.

The user could instead type:

> "Build me a React dashboard for tracking my projects."

The UI would show the agent working.

---

# 14. Proposed Baby-Agent UI

The UI should be added as a real sprint rather than treated as an afterthought.

## Main layout

```text
+--------------------------------------------------------------+
| BABY-AGENT                                      [Running]    |
+----------------------+---------------------------------------+
|                      |                                       |
| Sessions             | Current Task                          |
|                      |                                       |
| > Build dashboard    | Build project dashboard               |
|   Fix TypeScript     |                                       |
|   Learn npm error    | Agent is working...                  |
|                      |                                       |
|                      | [Plan]                                |
|                      | ✓ Inspect workspace                   |
|                      | ✓ Create architecture                 |
|                      | → Writing files                       |
|                      |                                       |
|                      | Files changed                         |
|                      | src/App.tsx                           |
|                      | src/components/...                    |
|                      |                                       |
|                      | Tool activity                         |
|                      | write_file                            |
|                      | run_command                           |
|                      |                                       |
+----------------------+---------------------------------------+
| > Tell Baby-Agent what to do...                  [Send]       |
+--------------------------------------------------------------+
```

The terminal should become an implementation detail.

The user should be able to inspect it when desired, but should not need to live inside it.

---

# 15. UI Features by Priority

## MVP UI

- New task
- Workspace selection
- Goal input
- Start / pause / stop
- Live agent messages
- Tool activity
- File changes
- Command results
- Errors
- Build/test status
- Final summary

## Next

- File diff viewer
- Session history
- Search previous sessions
- Case/lesson viewer
- Skill viewer
- Model selection
- Permission controls
- Token/context statistics
- Agent iteration count

## Later

- Visual project explorer
- Embedded terminal
- Screenshots
- Browser automation
- Multiple agents
- Agent-to-agent conversations
- Training dashboard
- Agent generation comparison

---

# 16. Current Tool Situation

The current tool system is one of the most useful architectural seams in the repository.

Existing model-callable/research-oriented tools include:

```text
case_search
doc_grep
journal_read
```

These are knowledge tools.

They should remain.

The missing tools are action tools.

---

# 17. Required Agent Tool Categories

## 17.1 Filesystem

First priority:

```text
list_directory
read_file
write_file
edit_file
search_code
```

Potential later tools:

```text
create_directory
move_file
copy_file
delete_file
file_exists
file_metadata
```

Deletion should have stricter permissions than reading/writing.

---

# 18. Terminal / Command Execution

The agent needs a structured command tool:

```text
run_command
```

Example conceptual request:

```json
{
  "tool": "run_command",
  "arguments": {
    "command": "npm run build",
    "cwd": "C:/Projects/example"
  }
}
```

Example structured result:

```json
{
  "exit_code": 1,
  "stdout": "...",
  "stderr": "...",
  "duration_ms": 1432
}
```

The model should never need to parse terminal formatting if the executor can provide structured metadata.

---

# 19. Build / Test Tools

Eventually expose higher-level tools:

```text
run_tests
run_build
run_lint
run_typecheck
```

These can internally invoke project-specific commands.

For example:

```text
run_build
    |
    +--> package.json -> npm run build
    |
    +--> pyproject.toml -> pytest/build
    |
    +--> Cargo.toml -> cargo build
```

The first version can simply accept an explicit command while project detection is developed later.

---

# 20. Git Tools

Initial Git tools:

```text
git_status
git_diff
git_log
```

Later:

```text
git_add
git_commit
git_branch
git_checkout
git_restore
```

Git write operations should initially require confirmation.

The goal is for the agent to be able to explain:

```text
Changed:
  src/App.tsx
  src/main.tsx

Build:
  PASS

Tests:
  PASS

Git diff:
  3 files changed
```

without requiring the user to run Git commands manually.

---

# 21. Process Management

For longer-running development tasks:

```text
process_start
process_output
process_status
process_stop
```

Examples:

```text
npm run dev
python server.py
uvicorn app:app --reload
```

The agent should be able to start and observe development processes without blocking the entire runtime.

---

# 22. Search

The coding agent needs fast project search.

Minimum:

```text
search_code
```

It should support:

- Text search
- File filtering
- Directory filtering
- Exclusions
- Reasonable result limits

Potential implementation:

```text
ripgrep
```

when available, with a Python fallback.

---

# 23. Tool Architecture

The existing tool registry should evolve toward:

```text
ToolRegistry
|
+-- schemas
+-- handlers
+-- metadata
+-- permissions
+-- timeout
+-- cancellation
+-- audit logging
```

Each tool should describe:

```text
name
description
arguments schema
category
permission level
timeout
side effects
handler
```

Example conceptual structure:

```python
ToolDefinition(
    name="read_file",
    description="Read a UTF-8 text file...",
    schema=...,
    permission="read",
    handler=read_file,
)
```

---

# 24. Structured Tool Calling

The current textual tool syntax was a useful early implementation.

For Agent-Lite, the architecture should move toward structured tool calls.

Desired:

```text
Model
  |
  v
ToolCall(
    name="read_file",
    arguments={...}
)
  |
  v
Validation
  |
  v
Permission
  |
  v
Execution
  |
  v
ToolResult
  |
  v
Model
```

The ModelProvider should normalize provider-specific formats into this internal representation.

---

# 25. ModelProvider Abstraction

The agent should not directly call `ollama_bridge.py`.

Introduce:

```text
ModelProvider
```

with adapters:

```text
OllamaProvider
OpenAIProvider
FutureProvider
```

Conceptual API:

```python
class ModelProvider:
    def generate(self, messages, tools=None):
        ...
```

Normalized response:

```text
ModelResponse
|
+-- text
+-- tool_calls
+-- finish_reason
+-- usage
+-- metadata
```

This is one of the highest-value architectural changes.

---

# 26. Why This Matters

It allows:

```text
Local:
Baby-Agent -> Ollama -> local model
```

or:

```text
Cloud:
Baby-Agent -> OpenAIProvider -> API model
```

without rewriting the agent runtime.

It also permits future routing:

```text
simple task -> small local model
complex task -> larger model
coding failure -> coding-specialized model
planning -> stronger reasoning model
```

---

# 27. Agent Session

Introduce a first-class session object.

Conceptual model:

```text
AgentSession
|
+-- session_id
+-- goal
+-- workspace
+-- status
+-- messages
+-- tool_calls
+-- observations
+-- files_changed
+-- commands_run
+-- errors
+-- iterations
+-- timestamps
+-- final_result
```

Possible statuses:

```text
CREATED
PLANNING
RUNNING
WAITING_FOR_PERMISSION
PAUSED
FAILED
COMPLETED
CANCELLED
```

---

# 28. Agent Loop

The core loop should eventually look like:

```python
while not state.complete:

    context = context_builder.build(state)

    response = model.generate(
        messages=context.messages,
        tools=registry.schemas(),
    )

    if response.has_tool_calls():
        for call in response.tool_calls:
            permission = policy.check(call)

            if permission == DENY:
                state.add_denial(call)
                continue

            if permission == ASK:
                state.pause_for_permission(call)
                return

            result = executor.execute(call)
            state.add_observation(result)

    elif response.is_final():
        state.complete(response.text)

    else:
        state.handle_unexpected_response()
```

This is the missing heart of Agent-Lite.

---

# 29. Context Builder

The agent should not send its entire history to the model indefinitely.

Create a context builder that selects:

```text
System instructions
+
Goal
+
Current plan/state
+
Relevant files
+
Recent tool results
+
Relevant cases
+
Relevant documentation
+
Relevant journal entries
+
Skill instructions
```

The context builder should be budget-aware.

---

# 30. Workspace Abstraction

Introduce:

```text
Workspace
```

Example:

```text
Workspace
|
+-- root
+-- cwd
+-- allowed_paths
+-- excluded_paths
+-- project_type
+-- git_root
+-- environment
+-- metadata
```

All filesystem and execution tools should operate through this boundary.

This provides both simplicity and safety.

---

# 31. Workspace Safety

The model should not automatically have unrestricted access to the machine.

Recommended initial policy:

```text
Workspace root:
    C:/Projects/MyApp

Allowed:
    C:/Projects/MyApp/**

Restricted:
    C:/Users/**
    C:/Windows/**
    C:/Program Files/**
    credentials
    browser profiles
    SSH keys
```

Path traversal must be prevented.

For example:

```text
../../Windows/System32
```

must not escape the workspace.

---

# 32. Permission System

Every tool should have a policy.

Example:

| Tool | Default |
|---|---|
| `list_directory` | Allow |
| `read_file` | Allow |
| `search_code` | Allow |
| `case_search` | Allow |
| `doc_grep` | Allow |
| `journal_read` | Allow |
| `write_file` | Allow within workspace |
| `edit_file` | Allow within workspace |
| `run_tests` | Allow |
| `run_build` | Allow |
| `run_command` | Configurable |
| `process_start` | Confirm initially |
| `delete_file` | Confirm |
| `git_status` | Allow |
| `git_diff` | Allow |
| `git_commit` | Confirm |
| Network access | Confirm |

The user should be able to change policies from the GUI.

---

# 33. Event System

The UI should not directly inspect internal agent state.

Instead, the runtime should emit events.

Examples:

```text
SESSION_CREATED
AGENT_STARTED
PLAN_CREATED
MODEL_REQUESTED
MODEL_RESPONDED
TOOL_REQUESTED
TOOL_STARTED
TOOL_COMPLETED
FILE_CREATED
FILE_MODIFIED
COMMAND_STARTED
COMMAND_COMPLETED
COMMAND_FAILED
TEST_STARTED
TEST_PASSED
TEST_FAILED
PERMISSION_REQUIRED
AGENT_PAUSED
AGENT_RESUMED
AGENT_COMPLETED
AGENT_FAILED
LESSON_RECORDED
```

The UI subscribes to these events.

This also gives us excellent debugging and future telemetry.

---

# 34. Cancellation / Timeout

Autonomy requires the ability to stop the agent.

Required:

```text
Stop
Pause
Resume
Cancel current tool
Timeout tool
Maximum iterations
Maximum runtime
```

Example:

```text
max_iterations = 50
max_runtime_minutes = 30
command_timeout_seconds = 120
```

These should be configurable.

---

# 35. The Autonomous Coding Loop

The first real autonomous milestone should be:

```text
User Goal
    |
    v
Agent Plan
    |
    v
Inspect project
    |
    v
Read relevant files
    |
    v
Create / modify files
    |
    v
Install dependencies if permitted
    |
    v
Build
    |
    +---- PASS
    |       |
    |       v
    |     Test
    |
    +---- FAIL
            |
            v
        Diagnose
            |
            +--> search cases
            +--> search docs
            +--> inspect files
            +--> inspect command output
            |
            v
           Fix
            |
            v
          Build
            |
            v
          Repeat
```

This should be the defining behavior of Agent-Lite.

---

# 36. Example End-to-End Task

User enters in the GUI:

> Build a small React/Vite todo application in this workspace. Use TypeScript. Run the build and fix errors until it passes.

Baby-Agent:

```text
1. Create session
2. Inspect workspace
3. Determine project type
4. Read package.json
5. Inspect existing source
6. Plan changes
7. Write files
8. Run npm install if needed
9. Run npm run build
10. Observe output
11. If failed:
      a. create failure signature
      b. search historical cases
      c. search docs
      d. inspect relevant source
      e. modify files
      f. retry
12. Run tests/typecheck
13. Summarize changes
14. Record useful lessons
```

The user should see this in the GUI rather than manually executing each step.

---

# 37. The Existing QA Brain + Agent Runtime

This is the central architectural opportunity.

The future system should connect the two halves:

```text
                   MODEL
                     |
                     v
                AGENT LOOP
                     |
              +------+------+
              |             |
              v             v
          ACTIONS        KNOWLEDGE
              |             |
        Files/Shell/Git   Cases/Docs
              |             |
              +------+------+
                     |
                     v
                   RESULT
                     |
             +-------+-------+
             |               |
           Success          Failure
             |               |
             |          QA Intelligence
             |               |
             |          diagnose/search
             |               |
             +-------+-------+
                     |
                     v
                   MODEL
                     |
                     v
                    FIX
                     |
                     v
                 VERIFICATION
                     |
                     v
                   LEARN
```

This is the architecture that turns Baby-Agent into something distinct from a generic LLM wrapper.

---

# 38. UI / Terminal Strategy

The project should become **GUI-first, terminal-capable**, rather than terminal-only.

The terminal remains useful for:

- Debugging
- Developers
- Advanced users
- Embedded command output
- Recovery
- Development

But the normal user workflow should be:

```text
Open Baby-Agent
    |
    v
Select workspace
    |
    v
Type goal
    |
    v
Start
    |
    v
Watch agent
```

Instead of:

```text
open terminal
cd project
run qa command
copy output
ask model
copy code
create files
run command
copy error
ask again
...
```

This directly addresses the original motivation for Baby-Agent.

---

# 39. Recommended Desktop Stack

For a polished local-first UI:

```text
Electron
React
TypeScript
Vite
```

Backend/runtime:

```text
Python
FastAPI or local IPC layer
Baby-Agent runtime
```

Model:

```text
Ollama
```

Storage:

```text
SQLite
```

Existing JSONL stores can remain during migration and be wrapped behind repositories.

Potential eventual structure:

```text
baby-agent/
|
+-- app/
|   +-- backend/
|   |   +-- api/
|   |   +-- agent/
|   |   +-- models/
|   |   +-- tools/
|   |   +-- workspace/
|   |   +-- permissions/
|   |   +-- events/
|   |   +-- memory/
|   |
|   +-- frontend/
|       +-- src/
|           +-- pages/
|           +-- components/
|           +-- hooks/
|           +-- stores/
|           +-- services/
|           +-- styles/
|
+-- qacompanion/
|   +-- cases
|   +-- skills
|   +-- digest
|   +-- training
|   +-- escalation
|   +-- existing QA systems
|
+-- tests/
|
+-- docs/
|
+-- data/
|
+-- scripts/
```

This is a target architecture, not a request to perform a giant refactor immediately.

Existing working modules should be migrated incrementally.

---

# 40. S31 / S32 Status

The Git history indicates:

```text
S30
    |
    v
S30 sign-off
    |
    v
S31/S32 skipped/logged
```

Therefore:

- S31 is not implemented.
- S32 is not implemented.
- Their roadmap specifications should not be treated as completed functionality.
- The old fine-tuning/generation plan should be reconsidered.

The recommended replacement is to use S31/S32 as the beginning of the Agent-Lite track.

---

# 41. Why Training Should Come Later

The original direction involved creating generations such as:

```text
baby-agent:ep1
baby-agent:ep2
baby-agent:ep3
```

That remains an interesting long-term goal.

However, training should come after Baby-Agent can actually generate high-quality trajectories.

A useful training record would be:

```text
Goal
  ->
Context
  ->
Plan
  ->
Tool Call
  ->
Tool Result
  ->
Error
  ->
Diagnosis
  ->
Fix
  ->
Verification
  ->
Outcome
```

This is much richer than simply training on:

```text
question -> answer
```

Therefore:

```text
Agent Runtime
    ->
Real tasks
    ->
Successful trajectories
    ->
Failures + recoveries
    ->
Training dataset
    ->
Baby-Agent Ep1
```

is preferable.

---

# 42. Proposed New Sprint Roadmap

## S31 — Agent Foundation

### Objectives

Create the core abstractions without yet attempting full autonomy.

Implement:

```text
ModelProvider
ModelResponse
ToolDefinition
ToolCall
ToolResult
AgentSession
AgentState
```

Integrate the existing Ollama bridge behind `OllamaProvider`.

Preserve current `qa ask` behavior.

### End Goal

Baby-Agent can communicate with the model through a provider abstraction and represent an agent session/tool call as structured internal objects.

### Verification

- Existing tests continue passing.
- Ollama can answer through `OllamaProvider`.
- A fake/mock provider can be used in tests.
- Tool calls can be represented without textual parsing.
- Agent sessions can be created and serialized.
- No existing QA functionality is broken.

---

# 43. S32 — Tool Registry v2

### Objectives

Upgrade the current tool registry.

Add:

```text
ToolDefinition
schema
handler
permission
timeout
side_effects
category
```

Preserve existing:

```text
case_search
doc_grep
journal_read
```

### End Goal

Every agent tool has a validated schema and a predictable execution contract.

### Verification

- Invalid arguments are rejected.
- Unknown tools are rejected.
- Existing tools work through the new registry.
- Tool results have a consistent structure.
- Unit tests cover registration, validation, dispatch, and errors.

---

# 44. S33 — Workspace Abstraction

### Objectives

Implement:

```text
Workspace
WorkspaceManager
PathPolicy
```

Support:

- Workspace root
- Current working directory
- Allowed paths
- Excluded paths
- Git root detection
- Project metadata

### End Goal

Every future filesystem/terminal action has a well-defined project boundary.

### Verification

- Relative paths resolve correctly.
- Absolute paths inside workspace work.
- Path traversal outside workspace is blocked.
- Excluded directories are respected.
- Workspace detection works on Windows.
- Tests cover malicious/pathological paths.

---

# 45. S34 — Filesystem Tools

### Objectives

Implement:

```text
list_directory
read_file
write_file
edit_file
search_code
```

### End Goal

The model can inspect and modify a project without the user manually copying code.

### Verification

Agent can:

1. List a project.
2. Read a file.
3. Create a file.
4. Modify a file.
5. Search source code.
6. Receive useful structured errors.
7. Never escape the workspace.

---

# 46. S35 — Terminal / Execution Tools

### Objectives

Implement:

```text
run_command
run_tests
run_build
run_lint
run_typecheck
```

Initial implementation can use explicit commands.

Add:

- stdout
- stderr
- exit code
- duration
- timeout
- cancellation
- working directory

### End Goal

Baby-Agent can execute project commands and understand whether they succeeded.

### Verification

Example:

```text
run_command("python --version")
```

returns structured output.

A failing command returns:

```text
exit_code != 0
stderr captured
stdout captured
```

Timeouts terminate correctly.

The agent cannot execute outside workspace policy without permission.

---

# 47. S36 — Git Tools

### Objectives

Implement:

```text
git_status
git_diff
git_log
```

Then optionally:

```text
git_add
git_commit
```

### End Goal

Baby-Agent can understand its changes and report them.

### Verification

- Agent can inspect repository status.
- Agent can inspect diff.
- Agent can inspect recent history.
- Git failures are returned cleanly.
- Commit operations require confirmation initially.

---

# 48. S37 — Agent Loop

### Objectives

Implement the real:

```text
goal
 -> model
 -> tool
 -> observation
 -> model
 -> ...
```

loop.

Add:

- iteration limits
- session state
- tool execution
- final answer detection
- failure handling
- cancellation

### End Goal

Baby-Agent can autonomously perform a multi-step task using tools.

### Verification

A deterministic fake model should be able to execute:

```text
list_directory
 -> read_file
 -> write_file
 -> run_command
 -> final
```

without human intervention.

A test must prove that tool output is fed back into the next model iteration.

---

# 49. S38 — Permissions / Safety

### Objectives

Implement:

```text
PermissionPolicy
PermissionDecision
```

Modes:

```text
ALLOW
ASK
DENY
```

### End Goal

Baby-Agent has explicit control over potentially destructive actions.

### Verification

Tests prove:

- Read allowed.
- Workspace writes allowed.
- Outside-workspace writes denied.
- Delete asks for permission.
- Git commit asks for permission.
- Network-sensitive actions can be denied.
- User cancellation works.

---

# 50. S39 — Event Stream

### Objectives

Create the event architecture.

Events include:

```text
agent_started
model_started
model_completed
tool_requested
tool_started
tool_completed
file_changed
command_started
command_completed
command_failed
permission_requested
agent_paused
agent_completed
agent_failed
lesson_recorded
```

### End Goal

The agent becomes observable without coupling the UI to internal implementation.

### Verification

A test session emits the expected event sequence.

Example:

```text
AGENT_STARTED
MODEL_STARTED
MODEL_COMPLETED
TOOL_REQUESTED
TOOL_STARTED
TOOL_COMPLETED
MODEL_STARTED
MODEL_COMPLETED
AGENT_COMPLETED
```

---

# 51. S40 — Desktop UI

### Objectives

Build the Electron + React + TypeScript interface.

Core screens:

```text
Dashboard
New Task
Active Session
Session History
Workspace
Settings
Memory / Cases
```

### Active Session UI

Show:

- Goal
- Agent status
- Current step
- Tool calls
- Files changed
- Command output
- Errors
- Build/test status
- Stop/Pause controls

### End Goal

The user can use Baby-Agent normally without typing CLI commands.

### Verification

User can:

1. Open Baby-Agent.
2. Select a workspace.
3. Enter a goal.
4. Start the agent.
5. Observe live activity.
6. Pause/stop it.
7. View changes.
8. See build/test results.
9. View final summary.

---

# 52. S41 — First Autonomous Coding Task

### Objectives

Prove the whole stack.

Task:

> Create a small project or modify an existing project, build it, detect failures, and fix them.

### End Goal

Baby-Agent performs an actual autonomous coding task from beginning to end.

### Verification

A controlled benchmark project is provided with an intentional defect.

Baby-Agent must:

```text
inspect
 -> diagnose
 -> edit
 -> build
 -> observe failure/success
 -> fix
 -> verify
```

with no manual command execution.

---

# 53. S42 — QA Brain Integration

### Objectives

Connect the Agent Runtime to the existing QA intelligence.

When a command fails:

```text
ToolResult
   |
   v
Failure signature
   |
   v
Case lookup
   |
   +--> known diagnosis
   |
   +--> unknown
   |
   v
Context injected into agent
```

### End Goal

Baby-Agent uses its accumulated knowledge while coding.

### Verification

Seed a known failure case.

Trigger the same failure.

Confirm the agent receives the historical diagnosis and uses it in its next decision.

---

# 54. S43 — Learning From Agent Sessions

### Objectives

Record useful agent trajectories.

Capture:

```text
goal
tools
results
failures
fixes
verification
outcome
```

Convert successful/valuable failures into cases.

### End Goal

Every coding session can improve Baby-Agent's knowledge base.

### Verification

Run a task that encounters an unknown error.

Fix it.

Confirm:

```text
new case
signature
diagnosis
resolution
timestamp
```

exists afterward.

---

# 55. S44 — Skills 2.0

### Objectives

Build higher-level skills using primitive tools.

Examples:

```text
create_react_app
debug_typescript
fix_python_import
setup_fastapi
run_project_tests
prepare_release
```

Skills should define:

```text
goal
required tools
procedure
verification
known failures
```

### End Goal

Baby-Agent can reuse successful procedures instead of rediscovering everything.

### Verification

Teach a skill once.

Run a compatible task.

Confirm the agent retrieves and follows the skill.

---

# 56. S45 — Model Routing

### Objectives

Support multiple models/providers.

Example:

```text
small/local model
    -> routine tasks

stronger model
    -> difficult planning

coding model
    -> implementation

escalation model
    -> stuck situations
```

### End Goal

The user can choose or configure how Baby-Agent balances cost, speed, privacy, and capability.

### Verification

Mock multiple providers and prove the router chooses according to policy.

---

# 57. S46 — Agent Evaluation Harness

### Objectives

Create repeatable benchmark tasks.

Metrics:

```text
task success
iterations
tool calls
time
failures
recovery rate
unnecessary actions
human interventions
```

### End Goal

Baby-Agent's improvements can be measured objectively.

### Verification

Run the same benchmark against two versions and produce comparable metrics.

---

# 58. S47 — Training Dataset Pipeline 2.0

Only after Agent-Lite is working.

Create structured trajectories:

```text
goal
context
action
observation
action
observation
...
final outcome
```

Separate:

```text
successful trajectories
failed trajectories
recovered trajectories
human-corrected trajectories
```

### End Goal

Generate high-quality data for future fine-tuning.

### Verification

A completed coding session exports into a valid training record.

---

# 59. S48 — Baby-Agent Ep1

This resurrects the original generation idea.

Potential process:

```text
Agent trajectories
       |
       v
Curate
       |
       v
Training dataset
       |
       v
Fine-tune / adapt model
       |
       v
baby-agent:ep1
       |
       v
Benchmark
```

### End Goal

A trained/optimized Baby-Agent model demonstrates measurable improvement on the evaluation suite.

### Verification

Compare Ep1 against the base model on the same benchmark.

Do not call Ep1 better merely because it was trained; require measurable improvement.

---

# 60. Future S49+ — Generational Agents

Potential long-term direction:

```text
Ep1
 |
 +--> learn
 |
Ep2
 |
 +--> learn
 |
Ep3
 |
 ...
```

Each generation should be benchmarked rather than assumed to be better.

Potential improvements:

- Better tool selection
- Fewer iterations
- Better error recovery
- Better planning
- Better memory retrieval
- Better skill reuse
- Better coding success
- Lower model size
- Faster inference

---

# 61. What Should NOT Be Built Yet

Avoid premature complexity.

Do not initially build:

- Multi-agent society
- Baby-agent-to-baby-agent communication
- GUI computer vision
- Browser automation
- Full autonomous Internet access
- Fine-tuning infrastructure
- Distributed inference
- Complex vector database
- Huge plugin ecosystem
- Self-modifying source code
- Unlimited shell access

The first goal is:

> **One agent, one workspace, one model, a small set of safe tools, and a reliable observe → act → verify loop.**

---

# 62. Initial Agent Tool Set

The ideal first practical toolbox is only:

```text
Knowledge
-----------
case_search
doc_grep
journal_read

Workspace
-----------
list_directory
read_file
write_file
edit_file
search_code

Execution
-----------
run_command
run_tests
run_build

Git
-----------
git_status
git_diff
```

That is enough for a surprisingly capable coding agent.

---

# 63. Example User Experience

Instead of:

```text
User:
"Build me an app."

Assistant:
"Create these files..."

User:
*manually creates files*

User:
"Here's the error."

Assistant:
"Change this."

User:
*manually changes it*

User:
"New error."

...
```

Baby-Agent becomes:

```text
User:
"Build me an app."

Baby-Agent:
"I'll inspect the workspace and begin."

[Inspecting workspace]

[Planning]

[Creating files]

[Installing dependencies]

[Running build]

[Build failed]

[Searching known failures]

[Inspecting source]

[Applying fix]

[Running build again]

[Build passed]

[Running tests]

[Tests passed]

"Done. I created X files, changed Y files,
and the build/tests pass."
```

The user remains the **goal setter and supervisor**, rather than becoming the agent's terminal operator.

---

# 64. Architecture Principle: User Supervises, Agent Operates

This should be a core design principle.

```text
                 USER
                  |
           Goals / Approval
                  |
                  v
             BABY-AGENT
                  |
        +---------+---------+
        |                   |
     Reason              Act
        |                   |
        +---------+---------+
                  |
               Observe
                  |
                  v
              Learn
```

The user should not need to manually shuttle information between:

- terminal
- editor
- browser
- LLM
- error output
- documentation

Baby-Agent's purpose is to become that orchestration layer.

---

# 65. Security Principles

The agent should be treated as untrusted automation.

Minimum safeguards:

1. Workspace sandbox
2. Path traversal prevention
3. Command timeout
4. Process cancellation
5. Iteration limits
6. Runtime limits
7. Permission policies
8. Audit log
9. Explicit confirmation for destructive operations
10. No unrestricted credential access
11. No unrestricted network access
12. Clear tool result boundaries

The model should never be given implicit authority simply because it can produce a tool call.

Every call passes through:

```text
Model
  |
  v
Validation
  |
  v
Permission
  |
  v
Workspace policy
  |
  v
Executor
```

---

# 66. Testing Strategy

Baby-Agent already has strong testing discipline.

The Agent-Lite expansion should preserve that.

Tests should exist at several levels.

## Unit

- Tool schemas
- Path validation
- Workspace
- Permission policy
- Model provider
- Tool registry
- Agent state

## Integration

- Model -> tool -> result
- Workspace -> filesystem
- Agent -> command execution
- QA -> failure case lookup
- Agent -> memory

## End-to-end

Use deterministic fake models.

Example:

```text
Fake model:
  call list_directory
  call read_file
  call write_file
  call run_build
  call final
```

This allows the agent loop to be tested without depending on Ollama availability.

---

# 67. Deterministic Test Models

A critical architectural choice:

Do not make the test suite depend entirely on a live LLM.

Instead:

```text
Agent Runtime
      |
      v
ModelProvider interface
      |
      +--> FakeProvider
      +--> OllamaProvider
      +--> OpenAIProvider
```

The fake provider can return scripted tool calls.

This makes agent-loop testing:

- Fast
- Deterministic
- Cheap
- Reproducible
- CI-friendly

---

# 68. Migration Strategy

Do not rewrite the project.

Use incremental extraction.

Recommended sequence:

```text
Existing qacompanion
       |
       v
wrap existing tools
       |
       v
introduce ModelProvider
       |
       v
introduce ToolRegistry v2
       |
       v
introduce Workspace
       |
       v
add filesystem tools
       |
       v
add command tools
       |
       v
add AgentSession
       |
       v
add AgentLoop
       |
       v
add UI
```

Every sprint should leave the repository usable.

---

# 69. Definition of "Agent-Lite Complete"

Agent-Lite should not be declared complete merely because an LLM can call tools.

The end-to-end definition should be:

```text
Given a bounded project workspace and a natural-language goal,
Baby-Agent can:

1. Understand the goal.
2. Inspect the project.
3. Form a useful plan.
4. Read relevant files.
5. Search the project.
6. Create/edit files.
7. Run project commands.
8. Observe command results.
9. Detect failures.
10. Search its accumulated knowledge.
11. Diagnose or attempt a fix.
12. Modify the project.
13. Re-run verification.
14. Repeat within defined limits.
15. Report what it did.
16. Persist useful lessons.
17. Allow the user to observe, pause, approve, or stop it.
```

That is the actual milestone.

---

# 70. Definition of "Baby-Agent" Beyond Agent-Lite

After Agent-Lite:

```text
Agent-Lite
    |
    +--> persistent learning
    |
    +--> skills
    |
    +--> evaluation
    |
    +--> trajectory collection
    |
    +--> model routing
    |
    +--> self-improvement
    |
    v
Baby-Agent
```

The long-term vision can then become:

> A small autonomous software agent that grows through experience rather than merely becoming a larger chatbot.

---

# 71. Final Audit Verdict

## Already Strong

```text
█████████░  Memory / Cases
█████████░  Failure intelligence
████████░░  Documentation/RAG
████████░░  Learning pipeline
███████░░░  Ollama integration
█████████░  Testing
███████░░░  Continuous observation
```

## Main Gaps

```text
██░░░░░░░░  Agent runtime
█░░░░░░░░░  Workspace
█░░░░░░░░░  Filesystem actions
█░░░░░░░░░  Terminal tools
███░░░░░░░  Git tools
██░░░░░░░░  Permissions
██░░░░░░░░  Session state
██░░░░░░░░  Event system
```

These gaps are substantial, but they are **architecturally straightforward compared with building the existing QA/learning brain from scratch**.

---

# 72. Final Recommendation

Do not restart Baby-Agent.

Do not immediately fine-tune S31/S32.

Instead:

```text
                     CURRENT
                        |
                        v
                  S30 COMPLETE
                        |
                        v
              +-------------------+
              | AGENT-LITE TRACK  |
              +-------------------+
                        |
              ModelProvider
                        |
                Tool Registry
                        |
                   Workspace
                        |
              Filesystem Tools
                        |
               Terminal Tools
                        |
                   Git Tools
                        |
                  Agent Loop
                        |
                  Permissions
                        |
                  Event Stream
                        |
                     UI
                        |
             Autonomous Coding
                        |
                        v
                 QA Integration
                        |
                        v
                  Self-Learning
                        |
                        v
              Evaluation Harness
                        |
                        v
                Training Data
                        |
                        v
                  Baby-Agent Ep1
```

The first major target should be:

> **"I can open Baby-Agent, point it at a project, type what I want built, and watch it inspect, edit, run, diagnose, fix, and verify the project without me manually copying commands or code between the terminal and an LLM."**

Once that works, the original Baby-Agent idea becomes real.

---

# 73. Immediate Next Step

The next implementation document should be derived from this audit and should specify the exact implementation of **S31 Agent Foundation**.

That implementation should begin with:

```text
1. ModelProvider
2. OllamaProvider
3. ModelResponse
4. ToolDefinition
5. ToolCall
6. ToolResult
7. AgentSession
8. AgentState
9. FakeModelProvider
10. Tests
```

It should **not** start by rewriting the existing QA system.

The existing QA system becomes Baby-Agent's first major "brain subsystem."

The Agent Runtime becomes its ability to act.

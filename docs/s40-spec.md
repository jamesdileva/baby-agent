# S40 — Environment Intelligence: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S40. Builds on S31–S39. One slice, stdlib only, no CLI changes.

## Overview

Understand the machine — so the agent can distinguish "the code is wrong"
from "the environment cannot run this project" BEFORE blindly retrying
fixes.

**Deviation, documented:** the roadmap's seven granular tools
(get_os, get_cpu, get_memory, get_gpu, get_runtime_versions,
get_package_manager) map to **section filters of one tool**,
`get_environment_summary(section=...)`. Same capability, one prompt
surface — the S37 live-smoke lesson says small models drown in tool
menus. Revisit granular entries when the S52 UI wants them.

## Module layout

```text
qacompanion/agent/environment.py     # EnvironmentToolkit + collectors
tests/test_agent_environment.py
```

## The tool

`get_environment_summary` (READ_ONLY, requires_workspace=True, category
"environment"):

```text
{section?: str, requires?: {tool: min_version}, check_ports?: [int]}
```

Sections (dict of dicts, JSON-ready; every collector degrades to
"unknown"/null on failure — NEVER raises):

- **os**: system, release, version, machine/arch, hostname, python version.
- **cpu**: count, processor string.
- **memory**: total/available bytes — Windows via ctypes
  GlobalMemoryStatusEx, Linux via /proc/meminfo, else unknown.
- **gpu**: probe `nvidia-smi --query-gpu=name` (shutil.which first, 2 s
  timeout); none detected → null. No GPU claims without evidence.
- **runtimes**: for node, npm, pnpm, yarn, git, java, rustc, go —
  `shutil.which` path + `--version` probe (2 s timeout, errors="replace");
  absent binaries reported absent, never probed blindly. Python comes from
  sys.version_info (free).
- **package_managers**: which-presence for pip/uv/poetry/npm/pnpm/yarn/cargo.
- **disk**: shutil.disk_usage on the workspace root (total/free/used bytes).
- **ports**: for each requested port, a socket bind test on 127.0.0.1 →
  {port, available}.
- **variables**: environment-variable METADATA only — a curated watch list
  (PATH, VIRTUAL_ENV, OLLAMA_MODEL, OLLAMA_URL, JAVA_HOME, PYTHONPATH,
  NODE_ENV, USERPROFILE/HOME...) reported as {name, set: bool}. **Values
  are never included — no exceptions.**

## Mismatch check (the roadmap verification)

`requires: {tool: min_version}` probes the runtime and compares simple
version tuples (leading numeric components; "v18.17.0" → (18, 17, 0)).
Missing tool → mismatch with found=null. The response carries
`mismatches: [{tool, required, found}]` and `satisfied: bool` — the agent
sees "node >= 20 unavailable" before retrying code fixes that cannot work.
Documented limit: simple numeric prefix compare only; no full semver.

## Testing strategy (tests/test_agent_environment.py)

- Summary structure: all sections present, JSON-serializable; os.system
  sane; python/git runtimes found (this machine has them); absent
  binaries degrade to null without errors.
- Memory: returns ints on Windows (ctypes path); /proc path skipped
  honestly where absent.
- Variables: with a seeded SECRET_TOKEN value in the environment, the
  output contains the NAME and "set": true but NEVER the value.
- Ports: a bound socket reports unavailable; a free port reports
  available.
- Mismatch: python >= 999 → unsatisfied with found reported; python
  satisfied with a realistic minimum; unknown tool → found null.
- Section filter: returns only the requested section; unknown section →
  structured error.
- Registration: READ_ONLY, requires_workspace; executes through the S32
  pipeline; agent_registry grows to 22.

Expected suite growth: 1125 → ~1145 OK.

## Exit criteria (from ROADMAP-agentlite.md §S40)

A deliberately incompatible requirement yields a mismatch report before
code fixes are attempted; secrets never surface; no collector can crash
the summary. Full suite green; preflight clean.

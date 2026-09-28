export interface SessionSummary {
  session_id: string;
  goal: string;
  workspace: string;
  model: string | null;
  state: string;
  iterations: number;
  files_changed: string[];
  verification_results: { ok: boolean; detail: string }[];
  termination_reason: string | null;
  final_result: string | null;
  done: boolean;
  error: string | null;
  pending_confirmation: {
    tool: string;
    arguments: Record<string, unknown>;
  } | null;
}

export interface AgentEvent {
  seq: number;
  event_id: string;
  session_id: string;
  timestamp: string;
  event_type: string;
  payload: Record<string, unknown>;
}

export async function startSession(
  goal: string,
  workspace: string,
  model: string,
  provider: string,
  verifyCommand: string
): Promise<{ session_id: string }> {
  const resp = await fetch("/api/session/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      goal,
      workspace,
      model: model || null,
      provider: provider || null,
      verify_command: verifyCommand || null,
    }),
  });
  if (!resp.ok) throw new Error((await resp.json()).error ?? resp.statusText);
  return resp.json();
}

export async function stopSession(sessionId: string): Promise<void> {
  await fetch(`/api/session/${sessionId}/stop`, { method: "POST" });
}

export async function confirmSession(
  sessionId: string,
  approved: boolean
): Promise<void> {
  const resp = await fetch(`/api/session/${sessionId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
  if (!resp.ok) throw new Error((await resp.json()).error ?? resp.statusText);
}

export interface Job {
  id: string;
  kind: string;
  status: "running" | "done" | "failed";
  started_at: string;
  finished_at: string | null;
  summary: string | null;
}

export async function startDrip(): Promise<{ job_id: string }> {
  const resp = await fetch("/api/drip", { method: "POST" });
  if (!resp.ok) throw new Error((await resp.json()).error ?? resp.statusText);
  return resp.json();
}

export async function startVerdict(
  models: string,
  tasks: number,
  temperature?: string,
  seed?: string
): Promise<{ job_id: string }> {
  const resp = await fetch("/api/verdict", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ models, tasks, temperature, seed }),
  });
  if (!resp.ok) throw new Error((await resp.json()).error ?? resp.statusText);
  return resp.json();
}

export async function listJobs(): Promise<Job[]> {
  const resp = await fetch("/api/jobs");
  if (!resp.ok) throw new Error(resp.statusText);
  return (await resp.json()).jobs;
}

export async function listSessions(): Promise<SessionSummary[]> {
  const resp = await fetch("/api/sessions");
  return (await resp.json()).sessions;
}

export async function listModels(): Promise<string[]> {
  const resp = await fetch("/api/models");
  if (!resp.ok) throw new Error((await resp.json()).error ?? resp.statusText);
  return (await resp.json()).models;
}

export interface BrowseResult {
  path: string;
  parent: string;
  directories: string[];
  files: string[];
  sep: string;
}

export async function browseDirectory(path: string): Promise<BrowseResult> {
  const resp = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
  if (!resp.ok) throw new Error((await resp.json()).error ?? resp.statusText);
  return resp.json();
}

export function openEventStream(
  sessionId: string,
  onEvent: (event: AgentEvent) => void,
  onDone: () => void
): EventSource {
  const source = new EventSource(`/api/events?session_id=${sessionId}`);
  source.onmessage = (message) => onEvent(JSON.parse(message.data));
  source.onerror = onDone;
  return source;
}

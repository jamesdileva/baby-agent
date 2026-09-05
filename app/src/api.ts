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
  done: boolean;
  error: string | null;
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
  model: string
): Promise<{ session_id: string }> {
  const resp = await fetch("/api/session/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal, workspace, model: model || null }),
  });
  if (!resp.ok) throw new Error((await resp.json()).error ?? resp.statusText);
  return resp.json();
}

export async function stopSession(sessionId: string): Promise<void> {
  await fetch(`/api/session/${sessionId}/stop`, { method: "POST" });
}

export async function listSessions(): Promise<SessionSummary[]> {
  const resp = await fetch("/api/sessions");
  return (await resp.json()).sessions;
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

import { useEffect, useRef, useState } from "react";
import {
  AgentEvent,
  SessionSummary,
  listSessions,
  openEventStream,
  startSession,
  stopSession,
} from "./api";

export default function App() {
  const [goal, setGoal] = useState("The tests in this project are failing. Find the bug, fix it, and run the tests to verify they pass.");
  const [workspace, setWorkspace] = useState("");
  const [model, setModel] = useState("qwen2.5-coder:1.5b");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [feed, setFeed] = useState<AgentEvent[]>([]);
  const sourceRef = useRef<EventSource | null>(null);

  async function refreshSessions() {
    setSessions(await listSessions());
  }

  useEffect(() => {
    refreshSessions();
    const timer = setInterval(refreshSessions, 2000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!activeId) return;
    setFeed([]);
    const source = openEventStream(
      activeId,
      (event) => setFeed((prev) => [...prev, event]),
      () => undefined
    );
    sourceRef.current = source;
    return () => source.close();
  }, [activeId]);

  useEffect(() => {
    if (!activeId) return;
    const timer = setInterval(async () => {
      const sessions = await listSessions();
      setSessions(sessions);
      const active = sessions.find((s) => s.session_id === activeId);
      if (active?.done) {
        sourceRef.current?.close();
        setFeed((prev) => prev); // keep the feed; summary renders below
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [activeId]);

  async function handleStart() {
    const { session_id } = await startSession(goal, workspace, model);
    setActiveId(session_id);
    refreshSessions();
  }

  async function handleStop() {
    if (activeId) await stopSession(activeId);
  }

  const active = sessions.find((s) => s.session_id === activeId);

  return (
    <div className="app">
      <h1>Baby-Agent</h1>
      <section className="new-task">
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} />
        <input
          value={workspace}
          onChange={(e) => setWorkspace(e.target.value)}
          placeholder="workspace path (optional)"
        />
        <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="model" />
        <button onClick={handleStart}>Start agent</button>
        {activeId && <button onClick={handleStop}>Stop</button>}
      </section>
      {active && (
        <section className="session">
          <h2>
            {active.state} — {active.goal.slice(0, 60)}
          </h2>
          <p>
            iterations: {active.iterations} | files changed:{" "}
            {active.files_changed.join(", ") || "none"}
          </p>
          {active.verification_results.length > 0 && (
            <ul>
              {active.verification_results.map((v, i) => (
                <li key={i}>
                  verification #{i + 1}: {v.ok ? "PASS" : "FAIL"} — {v.detail}
                </li>
              ))}
            </ul>
          )}
          {active.done && <p className="done">done: {active.termination_reason}</p>}
        </section>
      )}
      <section className="feed">
        <h2>Live activity</h2>
        <ul>
          {feed.slice(-50).map((event) => (
            <li key={event.event_id}>
              <span className="type">{event.event_type}</span>{" "}
              {event.event_type === "tool_requested" &&
                ` ${(event.payload as { tool?: string }).tool ?? ""}`}
              {event.event_type === "file_changed" &&
                ` ${(event.payload as { path?: string }).path ?? ""}`}
              {event.event_type === "failure_detected" &&
                ` ${(event.payload as { message?: string }).message ?? ""}`}
            </li>
          ))}
        </ul>
      </section>
      <section className="history">
        <h2>Sessions</h2>
        <ul>
          {sessions.map((s) => (
            <li key={s.session_id} onClick={() => setActiveId(s.session_id)}>
              [{s.state}] {s.goal.slice(0, 50)}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import {
  AgentEvent,
  BrowseResult,
  Job,
  SessionSummary,
  browseDirectory,
  listJobs,
  listModels,
  listSessions,
  openEventStream,
  startDrip,
  startSession,
  startVerdict,
  stopSession,
} from "./api";

export default function App() {
  const [goal, setGoal] = useState("The tests in this project are failing. Find the bug, fix it, and run the tests to verify they pass.");
  const [workspace, setWorkspace] = useState("");
  const [model, setModel] = useState("baby-agent:ep11-q4");
  const [models, setModels] = useState<string[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [provider, setProvider] = useState("ollama");
  const [startError, setStartError] = useState<string | null>(null);
  const [browse, setBrowse] = useState<BrowseResult | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [feed, setFeed] = useState<AgentEvent[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [verdictModels, setVerdictModels] = useState(
    "baby-agent:ep12-q4,baby-agent:ep11-q4"
  );
  const [verdictTemp, setVerdictTemp] = useState("");
  const [verdictSeed, setVerdictSeed] = useState("");
  const sourceRef = useRef<EventSource | null>(null);

  async function refreshSessions() {
    setSessions(await listSessions());
  }

  async function refreshJobs() {
    try {
      setJobs(await listJobs());
    } catch {
      // server briefly unavailable between restarts: keep last view
    }
  }

  useEffect(() => {
    refreshSessions();
    refreshJobs();
    listModels().then(setModels).catch((e: Error) => setModelsError(e.message));
    const timer = setInterval(() => {
      refreshSessions();
      refreshJobs();
    }, 3000);
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
    setStartError(null);
    try {
      const { session_id } = await startSession(goal, workspace, model, provider);
      setActiveId(session_id);
      refreshSessions();
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleStop() {
    if (activeId) await stopSession(activeId);
  }

  async function openPicker() {
    try {
      setBrowse(await browseDirectory(workspace));
      setShowPicker(true);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    }
  }

  async function navigatePicker(path: string) {
    try {
      setBrowse(await browseDirectory(path));
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleDrip() {
    await startDrip();
    refreshJobs();
  }

  async function handleVerdict() {
    await startVerdict(verdictModels, 3, verdictTemp, verdictSeed);
    refreshJobs();
  }

  const active = sessions.find((s) => s.session_id === activeId);

  return (
    <div className="app">
      <h1>Baby-Agent</h1>
      <section className="operations">
        <h2>Operations</h2>
        <button onClick={handleDrip}>Run drip (one real pass, ~7-9 quota)</button>
        <div className="verdict-row">
          <input
            value={verdictModels}
            onChange={(e) => setVerdictModels(e.target.value)}
            placeholder="models, comma-separated (newest first)"
          />
          <input
            value={verdictTemp}
            onChange={(e) => setVerdictTemp(e.target.value)}
            placeholder="temp (unset)"
          />
          <input
            value={verdictSeed}
            onChange={(e) => setVerdictSeed(e.target.value)}
            placeholder="seed (unset)"
          />
          <button onClick={handleVerdict}>Run verdict</button>
        </div>
        <ul className="jobs">
          {jobs.map((job) => (
            <li key={job.id} className={`job ${job.status}`}>
              <span className="kind">[{job.kind}]</span>{" "}
              <span className="status">{job.status}</span>
              {job.summary && <div className="summary">{job.summary}</div>}
            </li>
          ))}
        </ul>
      </section>
      <section className="new-task">
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} />
        <div className="workspace-row">
          <input
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
            placeholder="workspace path (optional)"
          />
          <button onClick={openPicker}>Browse…</button>
        </div>
        <input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="model"
          list="model-list"
        />
        <datalist id="model-list">
          {models.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        {modelsError && <p className="error">models: {modelsError}</p>}
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          <option value="ollama">ollama (local)</option>
          <option value="gemini">gemini (free tier)</option>
        </select>
        <button onClick={handleStart}>Start agent</button>
        {activeId && <button onClick={handleStop}>Stop</button>}
        {startError && <p className="error">{startError}</p>}
      </section>
      {showPicker && browse && (
        <section className="picker">
          <h2>Choose workspace</h2>
          <p>{browse.path}</p>
          <button onClick={() => navigatePicker(browse.parent)}>Up</button>
          <ul>
            {browse.directories.map((d) => (
              <li key={d} onClick={() => navigatePicker(browse.path + browse.sep + d)}>
                {d}/
              </li>
            ))}
          </ul>
          <button onClick={() => { setWorkspace(browse.path); setShowPicker(false); }}>
            Use this folder
          </button>
          <button onClick={() => setShowPicker(false)}>Cancel</button>
        </section>
      )}
      {active && (
        <section className="session">
          <h2>
            {active.state} — {active.goal.slice(0, 60)}
          </h2>
          <p>
            iterations: {active.iterations} | files changed:{" "}
            {active.files_changed.join(", ") || "none"}
          </p>
          <p>
            workspace: {active.workspace || "(temp)"} | model:{" "}
            {active.model ?? "default"}
          </p>
          {active.error && <p className="error">{active.error}</p>}
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
              {event.event_type === "tool_failed" &&
                ` ${(event.payload as { tool?: string }).tool ?? ""}: ${(event.payload as { error?: string }).error ?? ""}`}
              {event.event_type === "model_response" &&
                ` ${(event.payload as { text?: string }).text ?? ""}`}
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

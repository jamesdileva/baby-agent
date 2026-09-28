import { useEffect, useRef, useState } from "react";
import {
  AgentEvent,
  BrowseResult,
  Job,
  SessionSummary,
  browseDirectory,
  confirmSession,
  listJobs,
  listModels,
  listSessions,
  openEventStream,
  startDrip,
  startSession,
  startVerdict,
  stopSession,
} from "./api";

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function App() {
  const [goal, setGoal] = useState("The tests in this project are failing. Find the bug, fix it, and run the tests to verify they pass.");
  const [workspace, setWorkspace] = useState("");
  const [model, setModel] = useState("baby-agent:ep11-q4");
  const [models, setModels] = useState<string[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [provider, setProvider] = useState("ollama");
  const [verifyCommand, setVerifyCommand] = useState("");
  const [startError, setStartError] = useState<string | null>(null);
  const [browse, setBrowse] = useState<BrowseResult | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [pickerFilter, setPickerFilter] = useState("");
  const [pickerPathEntry, setPickerPathEntry] = useState("");
  const [recentWorkspaces, setRecentWorkspaces] = useState<string[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [feed, setFeed] = useState<AgentEvent[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [verdictModels, setVerdictModels] = useState(
    "baby-agent:ep16-q4,baby-agent:ep11-q4"
  );
  const [verdictTemp, setVerdictTemp] = useState("");
  const [verdictSeed, setVerdictSeed] = useState("");
  const sourceRef = useRef<EventSource | null>(null);
  const feedEndRef = useRef<HTMLDivElement | null>(null);

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
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [feed]);

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

  useEffect(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem("ba-recent-workspaces") ?? "[]"
      ) as string[];
      if (Array.isArray(saved)) setRecentWorkspaces(saved.slice(0, 5));
    } catch {
      // corrupt storage: start empty
    }
  }, []);

  useEffect(() => {
    if (!showPicker) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowPicker(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showPicker]);

  function rememberWorkspace(path: string) {
    if (!path.trim()) return;
    const next = [path, ...recentWorkspaces.filter((w) => w !== path)].slice(0, 5);
    setRecentWorkspaces(next);
    try {
      localStorage.setItem("ba-recent-workspaces", JSON.stringify(next));
    } catch {
      // private mode: memory-only is fine
    }
  }

  async function handleStart() {
    setStartError(null);
    try {
      const { session_id } = await startSession(goal, workspace, model, provider, verifyCommand);
      rememberWorkspace(workspace);
      setActiveId(session_id);
      refreshSessions();
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleStop() {
    if (activeId) await stopSession(activeId);
  }

  async function handleConfirm(approved: boolean) {
    if (activeId) await confirmSession(activeId, approved);
  }

  async function openPicker() {
    try {
      setBrowse(await browseDirectory(workspace));
      setPickerPathEntry(workspace);
      setPickerFilter("");
      setShowPicker(true);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    }
  }

  async function navigatePicker(path: string) {
    try {
      setBrowse(await browseDirectory(path));
      setPickerPathEntry(path);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleDrip() {
    await startDrip();
    refreshJobs();
  }

  async function handleVerdict() {
    await startVerdict(verdictModels, 4, verdictTemp, verdictSeed);
    refreshJobs();
  }

  const active = sessions.find((s) => s.session_id === activeId);
  const pickerDirs = browse
    ? browse.directories.filter((d) =>
        d.toLowerCase().includes(pickerFilter.toLowerCase())
      )
    : [];
  const pickerFiles = browse
    ? browse.files.filter((f) =>
        f.toLowerCase().includes(pickerFilter.toLowerCase())
      )
    : [];
  const pickerTruncated = Math.max(0, pickerFiles.length - 20);
  const dripRunning = jobs.some(
    (j) => j.kind === "drip" && j.status === "running"
  );
  const verdictRunning = jobs.some(
    (j) => j.kind === "verdict" && j.status === "running"
  );
  const agentBusy = active != null && !active.done;

  function renderEvent(event: AgentEvent) {
    const p = event.payload as Record<string, unknown>;
    switch (event.event_type) {
      case "tool_requested":
        return `${p.tool ?? ""} ${JSON.stringify(p.arguments ?? {})}`;
      case "tool_failed":
        return `${p.tool ?? ""}: ${p.error ?? ""}`;
      case "model_response":
        return (p.text as string) ?? "";
      case "file_changed":
        return (p.path as string) ?? "";
      case "failure_detected":
        return (p.message as string) ?? "";
      default:
        return "";
    }
  }

  return (
    <div className="app">
      <h1>Baby-Agent</h1>
      <div className="columns">
        <div className="col">
          <section className="new-task">
            <h2>Session settings</h2>
            <div className="workspace-row">
              <input
                value={workspace}
                onChange={(e) => setWorkspace(e.target.value)}
                placeholder="workspace path (optional)"
              />
              <button onClick={openPicker}>Browse…</button>
            </div>
            {recentWorkspaces.length > 0 && (
              <div className="recent-row">
                <span className="meta">recent: </span>
                {recentWorkspaces.map((w) => (
                  <button key={w} className="recent" onClick={() => setWorkspace(w)} title={w}>
                    {w.split(/[\\/]/).filter(Boolean).pop() || w}
                  </button>
                ))}
              </div>
            )}
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
            <input
              value={verifyCommand}
              onChange={(e) => setVerifyCommand(e.target.value)}
              placeholder="verify command (optional, e.g. python -m unittest)"
            />
          </section>
          <section className="operations">
            <h2>Operations</h2>
            <button onClick={handleDrip} disabled={dripRunning}>
              {dripRunning ? "Drip running…" : "Run drip (one real pass)"}
            </button>
            <div className="verdict-row">
              <input
                value={verdictModels}
                onChange={(e) => setVerdictModels(e.target.value)}
                placeholder="models, comma-separated (newest first)"
              />
            </div>
            <div className="verdict-row">
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
              <button onClick={handleVerdict} disabled={verdictRunning}>
                {verdictRunning ? "Running…" : "Run verdict"}
              </button>
            </div>
            <ul className="jobs">
              {jobs.length === 0 && <li className="empty">no operations yet</li>}
              {jobs.map((job) => (
                <li key={job.id} className={`job ${job.status}`}>
                  <span className="kind">[{job.kind}]</span>{" "}
                  <span className="status">{job.status}</span>{" "}
                  <span className="when">{timeAgo(job.started_at)}</span>
                  {job.summary && <div className="summary">{job.summary}</div>}
                </li>
              ))}
            </ul>
          </section>
          <section className="history">
            <h2>Sessions ({sessions.length})</h2>
            <ul>
              {sessions.length === 0 && <li className="empty">none yet</li>}
              {sessions.map((s) => (
                <li
                  key={s.session_id}
                  className={s.session_id === activeId ? "active-session" : ""}
                  onClick={() => setActiveId(s.session_id)}
                >
                  [{s.state}] {s.goal.slice(0, 44)}
                  <span className="meta">
                    {" "}
                    {s.model ?? "default"} · {s.files_changed.length} file
                    {s.files_changed.length === 1 ? "" : "s"}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </div>
        <div className="col">
          {active && (
            <section className="session">
              <h2>
                {active.state} — {active.goal.slice(0, 60)}
              </h2>
              <p>
                iterations: {active.iterations} | workspace:{" "}
                {active.workspace || "(temp)"} | model: {active.model ?? "default"}
              </p>
              {active.files_changed.length > 0 && (
                <p>
                  files changed:{" "}
                  {active.files_changed.map((f) => (
                    <span key={f} className="chip">{f}</span>
                  ))}
                </p>
              )}
              {active.error && <p className="error">{active.error}</p>}
              {active.pending_confirmation && (
                <div className="confirm">
                  <p>
                    Approval needed: {active.pending_confirmation.tool}{" "}
                    {JSON.stringify(active.pending_confirmation.arguments)}
                  </p>
                  <button onClick={() => handleConfirm(true)}>Approve</button>
                  <button onClick={() => handleConfirm(false)}>Deny</button>
                </div>
              )}
              {active.verification_results.length > 0 && (
                <ul>
                  {active.verification_results.map((v, i) => (
                    <li key={i}>
                      verification #{i + 1}:{" "}
                      <span className={v.ok ? "done" : "error"}>
                        {v.ok ? "PASS" : "FAIL"}
                      </span>{" "}
                      — {v.detail}
                    </li>
                  ))}
                </ul>
              )}
              {active.done && <p className="done">done: {active.termination_reason}</p>}
              {active.done && active.verification_results.length === 0 && (
                <p className="unverified">
                  unverified — no verify command was set, so completion means the model
                  stopped, not that anything was proven. Add a verify command (e.g.
                  python -m unittest) next run for a real gate.
                </p>
              )}
            </section>
          )}
          <section className="feed">
            <h2>Live activity</h2>
            {!activeId && <p className="empty">start or select a session to watch it work</p>}
            <div className="feed-scroll">
              <ul>
                {feed.slice(-80).map((event) => (
                  <li key={event.event_id}>
                    <span className="time">[{clock(event.timestamp)}]</span>{" "}
                    <span className="type">{event.event_type}</span>{" "}
                    {renderEvent(event)}
                  </li>
                ))}
              </ul>
              <div ref={feedEndRef} />
            </div>
          </section>
          {active?.done && active.final_result && (
            <section className="final-answer">
              <h2>Final response</h2>
              <p>{active.final_result}</p>
            </section>
          )}
          <section className="chat">
            <textarea
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={3}
              placeholder="type a task — Enter sends, Shift+Enter for a new line"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  if (goal.trim() && !agentBusy) handleStart();
                }
              }}
            />
            <div className="chat-actions">
              <button onClick={handleStart} disabled={!goal.trim() || agentBusy}>
                {agentBusy ? "Agent working…" : "Send"}
              </button>
              {agentBusy && (
                <button className="stop" onClick={handleStop}>Stop</button>
              )}
            </div>
            {startError && <p className="error">{startError}</p>}
          </section>
        </div>
      </div>
      {showPicker && browse && (
        <div className="picker-overlay" onClick={() => setShowPicker(false)}>
          <section className="picker" onClick={(e) => e.stopPropagation()}>
            <h2>Choose workspace</h2>
            <p className="path">{browse.path}</p>
            <div className="workspace-row">
              <input
                value={pickerPathEntry}
                onChange={(e) => setPickerPathEntry(e.target.value)}
                placeholder="type a path and press Go"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && pickerPathEntry.trim()) navigatePicker(pickerPathEntry.trim());
                }}
              />
              <button onClick={() => { if (pickerPathEntry.trim()) navigatePicker(pickerPathEntry.trim()); }}>Go</button>
            </div>
            <input
              value={pickerFilter}
              onChange={(e) => setPickerFilter(e.target.value)}
              placeholder="filter entries…"
            />
            <button onClick={() => navigatePicker(browse.parent)}>Up</button>
            <ul>
              {pickerDirs.map((d) => (
                <li key={d} onClick={() => navigatePicker(browse.path + browse.sep + d)}>
                  {d}/
                </li>
              ))}
              {pickerFiles.slice(0, 20).map((f) => (
                <li key={f} className="file-row">
                  <span className="file-name">{f}</span>
                </li>
              ))}
              {pickerTruncated > 0 && (
                <li className="picker-more">
                  …and {pickerTruncated} more files (narrow the filter)
                </li>
              )}
            </ul>
            {browse.directories.length === 0 && browse.files.length === 0 ? (
              <p className="empty">empty directory</p>
            ) : (
              pickerDirs.length === 0 &&
              pickerFiles.length === 0 && (
                <p className="empty">no matches for "{pickerFilter}"</p>
              )
            )}
            <div className="picker-actions">
              <button
                onClick={() => {
                  setWorkspace(browse.path);
                  rememberWorkspace(browse.path);
                  setShowPicker(false);
                }}
              >
                Use this folder
              </button>
              <button onClick={() => setShowPicker(false)}>Cancel</button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

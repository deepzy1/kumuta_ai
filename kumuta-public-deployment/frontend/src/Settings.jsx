import React, { useEffect, useRef, useState } from "react";
import {
  BarChart3,
  CheckCircle2,
  ExternalLink,
  Eye,
  EyeOff,
  KeyRound,
  LoaderCircle,
  Settings2,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { jsonBody } from "./api";
import QuickUIPreferences from "./QuickUISettings";
import MemoryPanel from "./Memory";

const number = (value) => Number(value || 0).toLocaleString();
function Usage({ api }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    api("/usage")
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [api]);
  if (error)
    return (
      <div className="error" role="alert">
        {error}
      </div>
    );
  if (!data)
    return (
      <p className="muted">
        <LoaderCircle size={16} className="spin" /> Loading your usage…
      </p>
    );
  const totals = data.totals;
  return (
    <div className="usage-panel">
      <p className="muted">Your activity, privately tracked by Kumuta AI.</p>
      <div className="usage-stats">
        {[
          ["Requests", totals.requests],
          ["Input tokens", totals.input_tokens],
          ["Output tokens", totals.output_tokens],
          ["Total tokens", totals.total_tokens],
          ["Search-enabled requests", totals.search_enabled_requests],
          ["Reported search queries", totals.reported_search_queries],
          ["QuickUI responses", totals.quickui_responses],
        ].map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{number(value)}</strong>
          </div>
        ))}
      </div>
      <div className="info-box">
        <ShieldCheck size={20} />
        <p>
          {data.quota_note}{" "}
          <a
            href="https://aistudio.google.com/usage"
            target="_blank"
            rel="noreferrer"
          >
            Open AI Studio <ExternalLink size={12} />
          </a>
        </p>
      </div>
      {!!totals.estimated_requests && (
        <p className="muted">
          {number(totals.estimated_requests)} request(s) have estimated or
          incomplete token counts. Total tokens can include model thinking
          tokens.
        </p>
      )}
      {data.quota_exceeded && (
        <div className="notice">
          Google reported a quota or rate limit among your recent requests.
          Remaining requests and reset times are unavailable here.
        </div>
      )}
      {[
        ["By model", data.by_model],
        ["By conversation", data.by_conversation],
        ["Daily activity · last 30 days, UTC", data.daily],
      ].map(([title, rows]) => (
        <section className="usage-section" key={title}>
          <h3>{title}</h3>
          {rows.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>
                      {title === "By model"
                        ? "Model"
                        : title === "By conversation"
                          ? "Conversation"
                          : "Date"}
                    </th>
                    <th>Requests</th>
                    <th>Input</th>
                    <th>Output</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.name}>
                      <td>{row.title || row.name}</td>
                      <td>{number(row.requests)}</td>
                      <td>{number(row.input_tokens)}</td>
                      <td>{number(row.output_tokens)}</td>
                      <td>
                        {number(row.total_tokens)}
                        {row.estimated_requests ? " *" : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">No activity yet.</p>
          )}
        </section>
      ))}
      <section className="usage-section">
        <h3>Recent generation performance</h3>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>Input / output</th>
                <th>Latency</th>
                <th>Search queries</th>
              </tr>
            </thead>
            <tbody>
              {(data.recent_activity || []).map((r, i) => (
                <tr key={i}>
                  <td>
                    {r.model}
                    {r.quickui ? " · QuickUI" : ""}
                  </td>
                  <td>
                    {number(r.input_tokens)} / {number(r.output_tokens)}
                    {r.estimated ? " (estimated)" : ""}
                  </td>
                  <td>
                    {r.latency_ms == null
                      ? "—"
                      : `${(r.latency_ms / 1000).toFixed(2)} s`}
                  </td>
                  <td>
                    {r.web_search ? (r.search_queries ?? "Unknown") : "Off"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="usage-section">
        <h3>Recent errors & stopped requests</h3>
        {data.recent_errors.length ? (
          data.recent_errors.map((row, i) => (
            <div className="usage-error" key={i}>
              <span>{row.model}</span>
              <span>
                {row.code === "429" ? "Quota / rate limit" : row.status}
                {row.code && row.code !== "429" ? ` (${row.code})` : ""}
              </span>
              <time>{new Date(row.date).toLocaleString()}</time>
            </div>
          ))
        ) : (
          <p className="muted">No errors recorded.</p>
        )}
      </section>
    </div>
  );
}

export default function Settings({
  tab,
  setTab,
  close,
  account,
  api,
  onAccount,
  projectId, conversationId, onFiles,
}) {
  const [key, setKey] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const dialog = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    dialog.current?.focus();
    function keyboard(e) {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {
        const elements = [
          ...dialog.current.querySelectorAll(
            'button:not(:disabled), input, select, textarea, a[href], [tabindex="0"]',
          ),
        ];
        const first = elements[0],
          last = elements[elements.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        }
        if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener("keydown", keyboard);
    return () => {
      document.removeEventListener("keydown", keyboard);
      previous?.focus();
    };
  }, [close]);
  async function keyAction(action) {
    if (busy) return;
    if (
      action === "delete" &&
      !window.confirm(
        "Delete your saved API key? You can add one again at any time.",
      )
    )
      return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      if (action === "validate") {
        await api("/settings/api-key/validate", {
          method: "POST",
          ...jsonBody({ api_key: key.trim() }),
        });
        setSuccess("Google accepted this key. Save it to start chatting.");
      } else {
        const data = await api(
          "/settings/api-key",
          action === "delete"
            ? { method: "DELETE" }
            : { method: "PUT", ...jsonBody({ api_key: key.trim() }) },
        );
        setKey("");
        setVisible(false);
        onAccount(data);
        setSuccess(
          action === "delete"
            ? "Your saved API key has been deleted."
            : "Your API key is connected. You’re ready to chat.",
        );
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        ref={dialog}
        className={`settings-dialog ${tab === "usage" ? "wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        tabIndex={-1}
      >
        <div className="dialog-header">
          <h2 id="settings-title">
            {tab === "key" ? (
              <KeyRound />
            ) : tab === "usage" ? (
              <BarChart3 />
            ) : (
              <Settings2 />
            )}
            {tab === "key"
              ? "My API Key"
              : tab === "usage"
                ? "Usage & Limits"
                : tab === "quickui"
                  ? "QuickUI Preferences"
                  : tab === "memory" ? "AI & Memory" : tab === "files" ? "Files" : tab === "privacy" ? "Privacy / Access" : "Account Settings"}
          </h2>
          <button className="icon" aria-label="Close settings" onClick={close}>
            <X size={20} />
          </button>
        </div>
        <nav className="settings-tabs" aria-label="Settings sections">
          {[
            ["account", "General"],
            ["key", "AI & Models"],
            ["memory", "AI & Memory"],
            ["files", "Files"],
            ["privacy", "Privacy / Access"],
            ["quickui", "Advanced"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={tab === id || (tab === "usage" && id === "key") ? "selected" : ""}
              onClick={() => {
                setTab(id);
                setError("");
                setSuccess("");
                setKey("");
              }}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="dialog-body">
          {(tab === "key" || tab === "usage") && <div className="settings-subnav"><button className="secondary" onClick={() => setTab("key")}>My API Key</button><button className="secondary" onClick={() => setTab("usage")}>Usage &amp; Limits</button></div>}
          {tab === "memory" && <MemoryPanel api={api} projectId={projectId} conversationId={conversationId} />}
          {tab === "files" && <div className="settings-category-content"><h3>Files</h3><p>Manage uploaded documents and processing in your current context.</p><button className="secondary" onClick={onFiles}>Open documents</button></div>}
          {tab === "privacy" && <div className="settings-category-content"><h3>Privacy / Access</h3><p>Your projects, conversations and files are private to your account. Uploads included in AI requests are sent to your provider. Memory is saved only when you choose to save it.</p><button className="secondary" onClick={() => setTab("memory")}>Review AI &amp; Memory</button></div>}
          {tab === "key" && (
            <>
              <div className="key-intro">
                <span className="feature-icon">
                  <KeyRound size={27} />
                </span>
                <div>
                  <h3>One key. Your own AI workspace.</h3>
                  <p>
                    Connect your own Google AI Studio Gemini API key. It’s
                    encrypted on our server and used only for your requests.
                  </p>
                </div>
              </div>
              <div
                className={`key-status ${account.has_api_key ? "connected" : ""}`}
              >
                <span className="status-dot" />
                {account.has_api_key
                  ? "API key connected"
                  : "No API key connected"}
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  keyAction("save");
                }}
              >
                <label className="field-label" htmlFor="api-key">
                  {account.has_api_key
                    ? "Replace your API key"
                    : "Your Gemini API key"}
                </label>
                <div className="key-input">
                  <input
                    id="api-key"
                    type={visible ? "text" : "password"}
                    value={key}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="Enter your Gemini API key"
                    maxLength={512}
                    onChange={(e) => setKey(e.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="icon"
                    onClick={() => setVisible((v) => !v)}
                    aria-label={visible ? "Hide API key" : "Show API key"}
                  >
                    {visible ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                <a
                  className="key-link"
                  href="https://aistudio.google.com/app/apikey"
                  target="_blank"
                  rel="noreferrer"
                >
                  Get a free API key from Google AI Studio{" "}
                  <ExternalLink size={14} />
                </a>
                <p className="muted small-text">
                  Google validates the key; AQ. and AIza prefixes are both
                  accepted. Free-tier model availability and limits depend on
                  your Google project.
                </p>
                <div className="key-actions">
                  {account.has_api_key && (
                    <button
                      type="button"
                      className="danger-text"
                      disabled={busy}
                      onClick={() => keyAction("delete")}
                    >
                      <Trash2 size={15} /> Delete key
                    </button>
                  )}
                  <div className="spacer" />
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy || key.trim().length < 10}
                    onClick={() => keyAction("validate")}
                  >
                    Validate
                  </button>
                  <button
                    className="primary compact"
                    disabled={busy || key.trim().length < 10}
                  >
                    {busy && <LoaderCircle size={16} className="spin" />} Save
                    key
                  </button>
                </div>
              </form>
              <div className="privacy-note">
                <ShieldCheck size={15} /> Your saved key is never sent back to
                your browser.
              </div>
            </>
          )}
          {tab === "account" && (
            <>
              <div className="account-card">
                <div className="avatar">
                  {account.email?.[0]?.toUpperCase()}
                </div>
                <div>
                  <h3>{account.email?.split("@")[0]}</h3>
                  <p>{account.email}</p>
                </div>
              </div>
              <label className="field-label">Preferred model</label>
              <p>
                {account.preferred_model ||
                  "Choose a model from the chat header after connecting your key."}
              </p>
              <div className="info-box">
                <ShieldCheck size={20} />
                <p>
                  Your conversations and attachments are private to your
                  account. Uploaded files are sent to Google when included in a
                  request.
                </p>
              </div>
            </>
          )}
          {tab === "usage" && <Usage api={api} />}
          {tab === "quickui" && <QuickUIPreferences />}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {success && (
            <div className="success" role="status">
              <CheckCircle2 size={17} />
              {success}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

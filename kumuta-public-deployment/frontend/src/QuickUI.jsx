import { Panels } from "./StructuredUI";
export { Chart } from "./StructuredUI";
import React, {
  Component,
  useEffect,
  useRef,
  useState,
} from "react";
import { Palette, Sparkles } from "lucide-react";
import Markdown from "./Markdown";
import { AppearanceEditor, useQuickUI } from "./QuickUISettings";
import {
  DEFAULTS,
  appearanceOnly,
  streamingMarkdown,
  themeVars,
  validSpec,
} from "./quickui";
import { jsonBody } from "./api";

const safeUrl = (url) => {
  try {
    const p = new URL(url);
    return ["https:", "http:"].includes(p.protocol) &&
      !p.username &&
      !p.password
      ? p.href
      : null;
  } catch {
    return null;
  }
};
function SourceLinks({ refs, sources }) {
  return (
    <span className="qui-source-links">
      {[...new Set(refs || [])].map((n) =>
        sources[n - 1] && safeUrl(sources[n - 1].url) ? (
          <a
            key={n}
            href={safeUrl(sources[n - 1].url)}
            target="_blank"
            rel="noopener noreferrer"
            title={sources[n - 1].title}
          >
            [{n}]
          </a>
        ) : null,
      )}
    </span>
  );
}
export function Sources({ grounding }) {
  if (!grounding?.enabled) return null;
  const sources = grounding.sources || [];
  // Provider-supplied suggestion HTML is confined to a scriptless, opaque-origin
  // frame with a restrictive CSP. It never reaches the main application DOM.
  const suggestions = grounding.search_entry_point;
  const srcDoc = suggestions
    ? "<!doctype html><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; base-uri 'none'; form-action 'none'\"><base target=\"_blank\">" +
      suggestions
    : "";
  return (
    <section className="qui-sources" aria-label="Web search sources">
      <strong>Web Search {sources.length ? "· Sources" : "enabled"}</strong>
      {!sources.length && (
        <p className="muted">
          Google returned no grounded sources for this response.
        </p>
      )}
      {sources.length > 0 && (
        <ol>
          {sources.map(
            (s, i) =>
              safeUrl(s.url) && (
                <li key={i}>
                  <a
                    href={safeUrl(s.url)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {s.title || s.url}
                  </a>
                </li>
              ),
          )}
        </ol>
      )}
      {grounding.citations?.length > 0 && (
        <details>
          <summary>Cited passages</summary>
          {grounding.citations.map((c, i) => (
            <p key={i}>
              {c.text}
              <SourceLinks refs={c.sources} sources={sources} />
            </p>
          ))}
        </details>
      )}
      {srcDoc && (
        <iframe
          title="Google Search suggestions"
          sandbox="allow-popups allow-popups-to-escape-sandbox"
          referrerPolicy="no-referrer"
          srcDoc={srcDoc}
          className="qui-search-suggestions"
        />
      )}
    </section>
  );
}
class RenderBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <>
        <p className="response-note">
          QuickUI could not render. Showing the saved text.
        </p>
        <Markdown text={this.props.fallback} />
      </>
    ) : (
      this.props.children
    );
  }
}
export default function QuickUIMessage({
  message,
  api,
  cid,
  chatAppearance,
  onChatAppearance,
  behavior,
  onTableAction,
}) {
  const renderStarted = performance.now();
  const q = useQuickUI();
  const [textMode, setTextMode] = useState(null);
  const [editor, setEditor] = useState(false);
  const [override, setOverride] = useState(message.quickui_appearance);
  const [draft, setDraft] = useState(null);
  const [scope, setScope] = useState("response");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [interaction,setInteraction] = useState(message.quickui_state || {});
  const [interactionError,setInteractionError] = useState('');
  const [stateSaving,setStateSaving] = useState(false);
  const stateRevision = useRef(message.quickui_state_revision || 0), stateQueue = useRef(Promise.resolve()), stateFailed=useRef(false), pendingStates=useRef(0);
  function saveInteraction(state) {
    setInteraction(state);setInteractionError('');setStateSaving(true);pendingStates.current++;
    stateQueue.current=stateQueue.current.then(async()=>{
      if(stateFailed.current)throw Error('Reload this conversation before saving component changes again.');
      const saved=await api(`/conversations/${cid}/messages/${message.id}/quickui-state`,{method:'PUT',...jsonBody({state,revision:stateRevision.current})});
      stateRevision.current=saved.revision;
    }).catch(e=>{stateFailed.current=true;setInteractionError(e.message);}).finally(()=>{pendingStates.current--;if(!pendingStates.current)setStateSaving(false);});
  }
  const [renderMs, setRenderMs] = useState(null);
  const target = useRef(null);
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const change = (e) => setSystemDark(e.matches);
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  useEffect(
    () => setOverride(message.quickui_appearance),
    [message.quickui_appearance],
  );
  useEffect(() => {
    if (!message.quickui) return;
    const start = renderStarted;
    const frame = requestAnimationFrame(() =>
      setRenderMs(Math.max(0, performance.now() - start)),
    );
    return () => cancelAnimationFrame(frame);
  }, [message.quickui]);
  const preferences =
    (editor && draft) ||
    override ||
    chatAppearance ||
    q.preview ||
    q.preferences ||
    DEFAULTS;
  const dark =
    preferences.appearance === "dark" ||
    (preferences.appearance === "system" && systemDark);
  const spec = message.quickui;
  const valid = validSpec(spec);
  const showUI =
    valid &&
    (textMode === false ||
      (textMode === null &&
        (behavior ?? q.preferences.behavior) !== "disabled"));
  const sources = message.grounding?.sources || [];
  const colors = preferences.color?.colors || DEFAULTS.color.colors;
  async function apply(reset = false) {
    setBusy(true);
    setError("");
    try {
      const appearance = reset
        ? null
        : appearanceOnly(draft || preferences);
      const path =
        scope === "chat"
          ? `/conversations/${cid}/quickui-appearance`
          : `/conversations/${cid}/messages/${message.id}/quickui-appearance`;
      const result = await api(path, {
        method: "PUT",
        ...jsonBody({ appearance }),
      });
      if (scope === "chat") {
        onChatAppearance(result.appearance);
        if (!reset && override) {
          await api(
            `/conversations/${cid}/messages/${message.id}/quickui-appearance`,
            { method: "PUT", ...jsonBody({ appearance: null }) },
          );
          setOverride(null);
        }
      } else setOverride(result.appearance);
      setDraft(null);
      setEditor(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function saveDefault() {
    if (
      !window.confirm(
        "Save this appearance as your global QuickUI default for all conversations and devices?",
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      await q.save({ ...q.preferences, ...appearanceOnly(draft || preferences) });
      setDraft(null);
      setEditor(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (!spec)
    return (
      <>
        <Markdown
          text={
            message.status === "generating"
              ? streamingMarkdown(message.content)
              : message.content
          }
          generating={message.status === "generating"}
        />
        {message.status === "generating" &&
          /^```(?:quickui|openui(?:-lang)?)\b/m.test(message.content) && (
            <p className="response-note">
              <Sparkles size={13} /> Building QuickUI…
            </p>
          )}
        <Sources grounding={message.grounding} />
      </>
    );
  return (
    <div
      ref={target}
      className={`quickui qui-${preferences.style} qui-${preferences.density} ${dark ? "qui-dark" : "qui-light"}`}
      style={themeVars(preferences, dark)}
    >
      <div className="qui-toolbar">
        <span>
          <Sparkles size={14} /> QuickUI
        </span>
        <div>
          <button
            type="button"
            onClick={() => setTextMode(showUI)}
            aria-pressed={!showUI}
          >
            {showUI ? "Show text" : "Show QuickUI"}
          </button>
          <button
            type="button"
            aria-expanded={editor}
            onClick={() => {
              setDraft(preferences);
              setEditor((v) => !v);
              setError("");
            }}
          >
            <Palette size={14} /> Appearance
          </button>
        </div>
      </div>
      {editor && (
        <div className="qui-inline-editor">
          <AppearanceEditor value={draft || preferences} onChange={setDraft} />
          <label>
            Apply appearance to
            <select value={scope} onChange={(e) => setScope(e.target.value)}>
              <option value="response">This response</option>
              <option value="chat">This chat</option>
            </select>
          </label>
          <div className="qui-actions">
            <button type="button" disabled={busy} onClick={() => apply()}>
              Apply
            </button>
            <button type="button" disabled={busy} onClick={() => apply(true)}>
              Use inherited appearance
            </button>
            <button
              type="button"
              disabled={busy || !q.loaded}
              onClick={saveDefault}
            >
              Save as my default
            </button>
            <button
              type="button"
              onClick={() => {
                setEditor(false);
                setDraft(null);
              }}
            >
              Cancel
            </button>
          </div>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
        </div>
      )}
      {showUI && message.quickui_intro && (
        <Markdown text={message.quickui_intro} />
      )}
      {showUI ? (
        <RenderBoundary fallback={message.content}>
          <Panels MarkdownComponent={Markdown} spec={spec} colors={colors} sources={sources} state={interaction} onState={saveInteraction} interactionScope="response" onTableAction={onTableAction} />
        </RenderBoundary>
      ) : (
        <>
          <p className="response-note">
            {!valid
              ? "QuickUI specification unavailable; showing saved text."
              : ""}
          </p>
          <Markdown text={message.content} />
        </>
      )}
      {stateSaving&&<small role="status">Saving component changes…</small>}
      {interactionError&&<p role="alert">Changes could not be saved: {interactionError}</p>}
      {renderMs !== null && (
        <details className="qui-performance">
          <summary>Rendering details</summary>
          <p>
            First paint observed after {renderMs.toFixed(1)} ms · appearance
            updates use 0 Gemini calls. Component changes save with this response.
          </p>
        </details>
      )}
      <Sources grounding={message.grounding} />
    </div>
  );
}

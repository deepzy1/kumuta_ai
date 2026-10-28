import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { jsonBody } from "./api";
import {
  DEFAULTS,
  PRESETS,
  colorCss,
  colorSelection,
  hexToRgb,
  rgbToHex,
  themeVars,
  validColor,
} from "./quickui";

export const QuickUIContext = createContext(null);
export const useQuickUI = () => useContext(QuickUIContext);
export function useQuickUISettings(api, token) {
  const [data, setData] = useState({
    preferences: DEFAULTS,
    recent: [],
    saved: [],
    revision: 0,
  });
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const epoch = useRef(0);
  const refresh = useCallback(async () => {
    if (!token) return;
    const generation = epoch.current;
    try {
      const result = await api("/settings/quickui");
      if (generation !== epoch.current) return;
      setData((previous) =>
        result.revision >= previous.revision ? result : previous,
      );
      setLoaded(true);
      setError("");
    } catch (e) {
      if (generation === epoch.current) setError(e.message);
    }
  }, [api, token]);
  useEffect(() => {
    epoch.current++;
    setData({ preferences: DEFAULTS, recent: [], saved: [], revision: 0 });
    setPreview(null);
    setLoaded(false);
    setError("");
    refresh();
    const onFocus = () => {
      if (document.visibilityState !== "hidden") refresh();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    const timer = setInterval(onFocus, 30000);
    return () => {
      epoch.current++;
      clearInterval(timer);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [refresh]);
  async function save(preferences, revision = data.revision) {
    const generation = epoch.current;
    const result = await api("/settings/quickui", {
      method: "PUT",
      ...jsonBody({ preferences, revision }),
    });
    if (generation === epoch.current) {
      setData(result);
      setPreview(null);
      setError("");
    }
    return result;
  }
  async function palette(path, method, payload) {
    const generation = epoch.current;
    const result = await api(`/settings/quickui/${path}`, {
      method,
      ...(payload ? jsonBody(payload) : {}),
    });
    if (generation === epoch.current)
      setData((previous) => ({ ...previous, ...result }));
  }
  return {
    ...data,
    preview,
    setPreview,
    error,
    loaded,
    refresh,
    save,
    palette,
  };
}

function Swatches({ items, onChoose, onRemove, label }) {
  return (
    <div className="qui-swatches" aria-label={label}>
      {items.map((item) => (
        <span className="qui-swatch-pair" key={item.id ?? item.name}>
          <button
            type="button"
            className="qui-swatch"
            title={item.name}
            aria-label={`Apply ${item.name}`}
            style={{ background: colorCss(item.selection || item) }}
            onClick={() => onChoose(item.selection || item)}
          />
          {onRemove && (
            <button
              type="button"
              className="qui-remove"
              title={`Remove ${item.name}`}
              aria-label={`Remove ${item.name}`}
              onClick={() => onRemove(item.id)}
            >
              ×
            </button>
          )}
        </span>
      ))}
    </div>
  );
}

export function AppearanceEditor({ value, onChange, showBehavior = false }) {
  const q = useQuickUI();
  const [error, setError] = useState("");
  const [name, setName] = useState("My palette");
  const color = value.color || DEFAULTS.color;
  const [hexDraft, setHexDraft] = useState(color.colors);
  const first = useRef(true);
  const recentTimer = useRef(null);
  const key = JSON.stringify(color);
  useEffect(() => setHexDraft(color.colors), [key]);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (!validColor(color)) return;
    const timer = setTimeout(
      () =>
        q
          .palette("palettes/recent", "POST", {
            selection: color,
            name: "Recent color",
          })
          .catch((e) => setError(e.message)),
      700,
    );
    recentTimer.current = timer;
    return () => clearTimeout(timer);
  }, [key]);
  const change = (patch) => onChange({ ...value, ...patch });
  const choose = (c) => change({ color: colorSelection(c) });
  function updateColor(index, hex) {
    if (!/^#[0-9a-f]{6}$/i.test(hex)) return;
    choose({
      ...color,
      colors: color.colors.map((c, i) => (i === index ? hex.toLowerCase() : c)),
    });
  }
  function mode(mode) {
    const colors =
      mode === "gradient"
        ? color.colors.length > 1
          ? color.colors
          : [color.colors[0], "#7c3aed"]
        : [color.colors[0]];
    choose({
      mode,
      colors,
      angle: color.angle,
      stops: colors.map((_, i) =>
        colors.length === 1 ? 0 : Math.round((i * 100) / (colors.length - 1)),
      ),
    });
  }
  async function action(fn) {
    clearTimeout(recentTimer.current);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <div className="qui-editor">
      <div className="qui-field-row">
        <label>
          Color mode
          <select
            aria-label="Color mode"
            value={color.mode}
            onChange={(e) => mode(e.target.value)}
          >
            {[
              ["system", "System / default"],
              ["solid", "Solid color"],
              ["gradient", "Gradient color"],
              ["custom", "Custom color"],
            ].map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          Visual style
          <select
            value={value.style}
            onChange={(e) => change({ style: e.target.value })}
          >
            {["minimal", "modern", "professional", "playful", "custom"].map(
              (v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ),
            )}
          </select>
        </label>
      </div>
      {color.mode !== "system" && (
        <fieldset>
          <legend>
            {color.mode === "gradient"
              ? "Gradient colors & stops"
              : "Full color picker"}
          </legend>
          {color.colors.map((hex, i) => (
            <div className="qui-color-row" key={i}>
              <input
                aria-label={`Color ${i + 1} spectrum`}
                type="color"
                value={hex}
                onChange={(e) => updateColor(i, e.target.value)}
              />
              <label>
                HEX
                <input
                  aria-label={`Color ${i + 1} HEX`}
                  value={hexDraft[i] ?? hex}
                  maxLength={7}
                  onChange={(e) => {
                    setHexDraft((p) =>
                      p.map((v, j) => (i === j ? e.target.value : v)),
                    );
                    updateColor(i, e.target.value);
                  }}
                  onBlur={() => setHexDraft(color.colors)}
                />
              </label>
              <div className="qui-rgb">
                {hexToRgb(hex).map((v, j) => (
                  <label key={j}>
                    {["R", "G", "B"][j]}
                    <input
                      aria-label={`Color ${i + 1} ${["R", "G", "B"][j]}`}
                      type="number"
                      min="0"
                      max="255"
                      value={v}
                      onChange={(e) => {
                        const rgb = hexToRgb(hex);
                        rgb[j] = Math.round(Number(e.target.value));
                        updateColor(i, rgbToHex(rgb));
                      }}
                    />
                  </label>
                ))}
              </div>
              {color.mode === "gradient" && (
                <>
                  <label>
                    Stop %
                    <input
                      aria-label={`Color ${i + 1} stop`}
                      type="number"
                      min={i ? color.stops[i - 1] : 0}
                      max={
                        i + 1 < color.stops.length ? color.stops[i + 1] : 100
                      }
                      value={color.stops[i]}
                      onChange={(e) => {
                        const stops = color.stops.map((v, j) =>
                          j === i
                            ? Math.max(
                                i ? color.stops[i - 1] : 0,
                                Math.min(
                                  i + 1 < color.stops.length
                                    ? color.stops[i + 1]
                                    : 100,
                                  Math.round(Number(e.target.value)),
                                ),
                              )
                            : v,
                        );
                        choose({ ...color, stops });
                      }}
                    />
                  </label>
                  {color.colors.length > 2 && (
                    <button
                      type="button"
                      aria-label={`Remove gradient color ${i + 1}`}
                      onClick={() =>
                        choose({
                          ...color,
                          colors: color.colors.filter((_, j) => i !== j),
                          stops: color.stops.filter((_, j) => i !== j),
                        })
                      }
                    >
                      ×
                    </button>
                  )}
                </>
              )}
            </div>
          ))}
          {color.mode === "gradient" && (
            <div className="qui-field-row">
              <label>
                Direction · {color.angle}°
                <input
                  aria-label="Gradient direction"
                  type="range"
                  min="0"
                  max="360"
                  value={color.angle}
                  onChange={(e) =>
                    choose({ ...color, angle: Number(e.target.value) })
                  }
                />
              </label>
              <button
                type="button"
                disabled={color.colors.length >= 6}
                onClick={() => {
                  const colors = [...color.colors, "#16804a"];
                  choose({
                    ...color,
                    colors,
                    stops: colors.map((_, i) =>
                      Math.round((i * 100) / (colors.length - 1)),
                    ),
                  });
                }}
              >
                Add color
              </button>
            </div>
          )}
        </fieldset>
      )}
      <section>
        <h4>Preset palettes</h4>
        <Swatches items={PRESETS} onChoose={choose} label="Preset palettes" />
      </section>
      <section>
        <div className="qui-section-heading">
          <h4>Recently Used Colors</h4>
          <button
            type="button"
            disabled={!q.recent.length}
            onClick={() => action(() => q.palette("palettes/recent", "DELETE"))}
          >
            Clear history
          </button>
        </div>
        <Swatches
          items={q.recent}
          onChoose={choose}
          onRemove={(id) => action(() => q.palette(`palette/${id}`, "DELETE"))}
          label="Recently Used Colors"
        />
        {!q.recent.length && (
          <p className="muted">
            Your recent solid colors and gradients will appear here.
          </p>
        )}
      </section>
      <section>
        <h4>Saved palettes</h4>
        <Swatches
          items={q.saved}
          onChoose={choose}
          onRemove={(id) => action(() => q.palette(`palette/${id}`, "DELETE"))}
          label="Saved palettes"
        />
        <div className="qui-field-row">
          <label>
            Palette name
            <input
              value={name}
              maxLength={60}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={!name.trim()}
            onClick={() =>
              action(() =>
                q.palette("palettes/saved", "POST", {
                  selection: color,
                  name: name.trim(),
                }),
              )
            }
          >
            Save palette
          </button>
        </div>
      </section>
      <div className="qui-field-row">
        <label>
          Appearance
          <select
            value={value.appearance}
            onChange={(e) => change({ appearance: e.target.value })}
          >
            {["light", "dark", "system"].map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Layout density
          <select
            value={value.density}
            onChange={(e) => change({ density: e.target.value })}
          >
            {["compact", "comfortable", "spacious"].map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      {value.style === "custom" && (
        <label>
          Corner radius · {value.radius}px
          <input
            type="range"
            min="0"
            max="28"
            value={value.radius}
            onChange={(e) => change({ radius: Number(e.target.value) })}
          />
        </label>
      )}
      {showBehavior && (
        <label>
          QuickUI behavior
          <select
            value={value.behavior}
            onChange={(e) => change({ behavior: e.target.value })}
          >
            <option value="automatic">Automatic</option>
            <option value="prefer">Always prefer QuickUI</option>
            <option value="disabled">Disabled · Markdown only</option>
          </select>
        </label>
      )}
      <div className="qui-preview" style={themeVars(value, false)}>
        <span style={{ background: colorCss(color) }} />
        <strong>Live appearance preview</strong>
        <p>Clear content, with your choice of accents.</p>
        <progress value="65" max="100" />
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export default function QuickUIPreferences() {
  const q = useQuickUI();
  const [draft, setDraft] = useState(q.preferences);
  const [revision, setRevision] = useState(q.revision);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  useEffect(() => {
    if (!dirty) {
      setDraft(q.preferences);
      setRevision(q.revision);
    }
  }, [q.revision, q.loaded]);
  useEffect(() => () => q.setPreview(null), []);
  function change(value) {
    setDraft(value);
    setDirty(true);
    q.setPreview(value);
    setSuccess("");
  }
  async function save(value) {
    setBusy(true);
    setError("");
    try {
      const result = await q.save(value, revision);
      setDraft(result.preferences);
      setRevision(result.revision);
      setDirty(false);
      setSuccess("Your QuickUI defaults are saved.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="qui-preferences">
      <p className="muted">
        Preview changes instantly. Save to apply them to your account across
        conversations and devices.
      </p>
      {q.error && (
        <p className="error" role="alert">
          {q.error}
        </p>
      )}
      <AppearanceEditor value={draft} onChange={change} showBehavior />
      <div className="qui-actions">
        <button
          type="button"
          className="primary"
          disabled={busy || !q.loaded}
          onClick={() => save(draft)}
        >
          Save preferences
        </button>
        <button
          type="button"
          disabled={busy || !q.loaded}
          onClick={() => save(DEFAULTS)}
        >
          Reset to default
        </button>
        <button
          type="button"
          onClick={() => {
            setDirty(false);
            q.setPreview(null);
            q.refresh();
            setDraft(q.preferences);
            setRevision(q.revision);
            setError("");
          }}
        >
          Reload saved preferences
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {success && (
        <p className="success" role="status">
          {success}
        </p>
      )}
    </div>
  );
}

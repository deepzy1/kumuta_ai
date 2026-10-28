import {validFormulas} from './intelligentUI.js';
import { contrast, parseColor } from "./vendor/answer-me-with-html/color.js";

export const DEFAULTS = {
  color: { mode: "system", colors: ["#c45d32"], angle: 120, stops: [0] },
  style: "modern",
  appearance: "system",
  density: "comfortable",
  radius: 12,
  behavior: "automatic",
};
export const PRESETS = [
  {
    name: "Terracotta",
    mode: "solid",
    colors: ["#c45d32"],
    angle: 120,
    stops: [0],
  },
  {
    name: "Forest",
    mode: "solid",
    colors: ["#16804a"],
    angle: 120,
    stops: [0],
  },
  { name: "Ocean", mode: "solid", colors: ["#2563eb"], angle: 120, stops: [0] },
  {
    name: "Violet",
    mode: "solid",
    colors: ["#7c3aed"],
    angle: 120,
    stops: [0],
  },
  {
    name: "Blue horizon",
    mode: "gradient",
    colors: ["#2563eb", "#7c3aed"],
    angle: 120,
    stops: [0, 100],
  },
  {
    name: "Sunrise",
    mode: "gradient",
    colors: ["#c45d32", "#e5a520", "#bd3266"],
    angle: 90,
    stops: [0, 50, 100],
  },
];
// Message/chat overrides accept Appearance only, not account-level settings.
export function appearanceOnly(value) {
  return Object.fromEntries(['color', 'style', 'appearance', 'density', 'radius']
    .filter(key => value[key] !== undefined).map(key => [key, value[key]]));
}
export function colorSelection(color) {
  return {
    mode: color.mode,
    colors: [...color.colors],
    angle: color.angle,
    stops: [...color.stops],
  };
}
export function validColor(c) {
  return (
    c &&
    ["system", "solid", "gradient", "custom"].includes(c.mode) &&
    Array.isArray(c.colors) &&
    c.colors.length >= 1 &&
    c.colors.length <= 6 &&
    c.colors.every((x) => /^#[0-9a-f]{6}$/i.test(x)) &&
    Number.isInteger(c.angle) &&
    c.angle >= 0 &&
    c.angle <= 360 &&
    Array.isArray(c.stops) &&
    c.stops.length === c.colors.length &&
    c.stops.every(
      (x, i) =>
        Number.isInteger(x) &&
        x >= 0 &&
        x <= 100 &&
        (!i || x >= c.stops[i - 1]),
    ) &&
    (c.mode === "gradient" ? c.colors.length >= 2 : c.colors.length === 1)
  );
}
export function colorCss(color) {
  const c = validColor(color) ? color : DEFAULTS.color;
  if (c.mode === "system") return "#c45d32";
  return c.mode === "gradient"
    ? `linear-gradient(${c.angle}deg, ${c.colors.map((v, i) => `${v} ${c.stops[i]}%`).join(", ")})`
    : c.colors[0];
}
export function hexToRgb(hex) {
  return parseColor(hex)?.slice(0, 3).map(Math.round) || [0, 0, 0];
}
export function rgbToHex(rgb) {
  return (
    "#" +
    rgb
      .map((v) =>
        Math.max(0, Math.min(255, Number(v) || 0))
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
  );
}
export function themeVars(preferences, dark) {
  const c = validColor(preferences.color) ? preferences.color : DEFAULTS.color;
  const accent = c.mode === "system" ? DEFAULTS.color.colors[0] : c.colors[0];
  const bg = parseColor(dark ? "#171c24" : "#ffffff");
  let text = parseColor(accent);
  const toward = dark ? 255 : 0;
  for (let i = 0; i < 25 && contrast(text, bg) < 4.5; i++)
    text = text.map((v, j) => (j < 3 ? v + (toward - v) * 0.12 : v));
  return {
    "--qui-accent": accent,
    "--qui-fill": colorCss(c),
    "--qui-ink": rgbToHex(text.slice(0, 3).map(Math.round)),
    "--qui-radius": `${preferences.style === "minimal" ? 0 : preferences.style === "professional" ? 5 : preferences.style === "playful" ? 22 : (preferences.radius ?? 12)}px`,
  };
}
export function calculate(operation, values) {
  const [principal, rate, years] = values;
  let result;
  if (operation === "sum") result = values.reduce((a, b) => a + b, 0);
  else if (operation === "product") result = values.reduce((a, b) => a * b, 1);
  else if (operation === "compound")
    result = principal * (1 + rate / 100) ** years;
  else if (operation === "loan") {
    const n = Math.round(years * 12),
      r = rate / 1200;
    if (n <= 0) return null;
    result = r === 0 ? principal / n : (principal * r) / (1 - (1 + r) ** -n);
  }
  return Number.isFinite(result) ? result : null;
}
export function streamingMarkdown(content) {
  return content.replace(/^```(?:quickui|openui(?:-lang)?)\b[\s\S]*$/m, "").trim();
}
// Guard stored/remote data before it reaches JSX, including older or damaged records.
export function validSpec(s) {
  try {
    return validateSpec(s);
  } catch {
    return false;
  }
}
function validateSpec(s) {
  if (
    !s ||
    s.version !== 1 ||
    !Array.isArray(s.blocks) ||
    !s.blocks.length ||
    s.blocks.length > 16
  )
    return false;
  if (JSON.stringify(s).length > 150000) return false;
  const label = (x) =>
    typeof x === "string" || (typeof x === "number" && Number.isFinite(x));
  return s.blocks.every((b) => {
    if (!b || (b.title !== undefined && !label(b.title))) return false;
    switch (b.type) {
      case "markdown":
        return typeof b.text === "string";
      case "diagram":
        return (
          typeof b.text === "string" &&
          b.text.length <= 10000 &&
          ["sequence", "mermaid"].includes(b.syntax) &&
          !/%%\{|^\s*---|\b(click|callback|javascript|style|classDef|linkStyle)\b|<\s*[A-Za-z!/]/im.test(
            b.text,
          )
        );
      case "table":
        return (
          Array.isArray(b.columns) &&
          b.columns.length > 0 &&
          b.columns.length <= 12 &&
          b.columns.every(label) &&
          Array.isArray(b.rows) &&
          b.rows.length <= 1000 &&
          (b.formats===undefined||Array.isArray(b.formats)&&(!b.formats.length||b.formats.length===b.columns.length)&&b.formats.every(f=>f&&Object.keys(f).every(k=>['kind','currency','decimals'].includes(k))&&['text','number','currency','percent','date','status'].includes(f.kind)&& (f.currency===undefined||/^[A-Z]{3}$/.test(f.currency))&&(f.decimals===undefined||Number.isInteger(f.decimals)&&f.decimals>=0&&f.decimals<=8))) &&
          b.rows.every(
            (r) =>
              Array.isArray(r) &&
              r.length === b.columns.length &&
              r.every(label),
          )
        );
      case "chart":
        return (
          ["bar", "line", "area", "stacked", "scatter", "pie", "donut"].includes(b.kind) &&
          Array.isArray(b.labels) &&
          b.labels.length > 0 &&
          b.labels.length <= 100 &&
          b.labels.every(label) &&
          Array.isArray(b.series) &&
          b.series.length > 0 &&
          b.series.length <= 8 &&
          (b.colors===undefined||Array.isArray(b.colors)&&b.colors.length<=8&&b.colors.every(c=>/^#[0-9a-f]{6}$/i.test(c))) &&
          (!['pie','donut'].includes(b.kind)||b.series.length===1&&b.series[0].values.every(v=>v>=0)&&b.series[0].values.reduce((a,b)=>a+b,0)>0) &&
          (b.kind!=='scatter'||b.labels.every(v=>String(v).trim()!==''&&Number.isFinite(Number(v))&&Math.abs(Number(v))<=1e12)) &&
          b.series.every(
            (v) =>
              label(v.name) &&
              Array.isArray(v.values) &&
              v.values.length === b.labels.length &&
              v.values.every(
                (n) => typeof n === "number" && Number.isFinite(n),
              ),
          )
        );
      case "form":
        return Array.isArray(b.fields) && b.fields.length>0 && b.fields.length<=30 && (b.submit_label===undefined||typeof b.submit_label==='string'&&b.submit_label.length<=300) && b.fields.every(f=>
          f && Object.keys(f).every(k=>['label','kind','options','value'].includes(k)) && typeof f.label==='string' && f.label.length<=300 && ['text','textarea','select','checkbox','radio','switch'].includes(f.kind) &&
          (f.options===undefined||Array.isArray(f.options)&&f.options.length<=30&&f.options.every(o=>typeof o==='string'&&o.length<=300)) &&
          (['checkbox','switch'].includes(f.kind)?typeof f.value==='boolean':typeof f.value==='string'&&f.value.length<=4000) &&
          (!['select','radio'].includes(f.kind)||f.options?.length>0&&new Set(f.options).size===f.options.length&&f.options.includes(f.value)));
      case "calculator":
        return (
          ["sum", "product", "compound", "loan", "formula"].includes(b.operation) &&
          Array.isArray(b.inputs) &&
          b.inputs.length > 0 &&
          b.inputs.length <= 6 &&
          b.inputs.every(
            (v) =>
              label(v.label) &&
              [v.min, v.max, v.value, v.step].every(Number.isFinite) &&
              v.min < v.max &&
              v.value >= v.min &&
              v.value <= v.max &&
              v.step > 0 && (v.kind===undefined||['number','currency','percent','select'].includes(v.kind)) && (v.options===undefined||Array.isArray(v.options)&&v.options.length<=30&&v.options.every(n=>Number.isFinite(n))) && (v.kind!=='select'||v.options?.length>0&&new Set(v.options).size===v.options.length&&v.options.includes(v.value)&&v.options.every(n=>n>=v.min&&n<=v.max)),
          ) &&
          (!["compound", "loan"].includes(b.operation) || b.inputs.length === 3 && b.inputs.every(i=>i.min>=0)) &&
          (b.operation==='formula'?Array.isArray(b.formulas)&&b.formulas.length>0&&b.formulas.every(f=>f&&Object.keys(f).every(k=>['label','expression','unit'].includes(k))&&typeof f.label==='string'&&(f.unit===undefined||typeof f.unit==='string'))&&validFormulas(b.formulas.map(f=>f.expression),b.inputs.length):b.formulas===undefined||Array.isArray(b.formulas)&&!b.formulas.length)
        );
      case "cards":
        return (
          Array.isArray(b.items) &&
          b.items.length > 0 &&
          b.items.length <= 20 &&
          b.items.every(
            (v) => label(v.label) && label(v.value) && label(v.detail ?? ""),
          )
        );
      case "timeline":
        return (
          Array.isArray(b.items) &&
          b.items.length > 0 &&
          b.items.length <= 40 &&
          b.items.every(
            (v) => label(v.when) && label(v.title) && label(v.detail ?? ""),
          )
        );
      case "progress":
        return (
          Array.isArray(b.items) &&
          b.items.length > 0 &&
          b.items.length <= 20 &&
          b.items.every(
            (v) =>
              label(v.label) &&
              Number.isFinite(v.value) &&
              v.value >= 0 &&
              Number.isFinite(v.max) &&
              v.max > 0,
          )
        );
      case "checklist":
        return (
          Array.isArray(b.items) &&
          b.items.length > 0 &&
          b.items.length <= 50 &&
          b.items.every((v) => label(v.text) && typeof v.checked === "boolean")
        );
      default:
        return false;
    }
  });
}

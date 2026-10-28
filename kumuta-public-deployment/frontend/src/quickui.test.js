import assert from "node:assert/strict";
import test from "node:test";
import {
  calculate,
  appearanceOnly,
  colorSelection,
  PRESETS,
  colorCss,
  DEFAULTS,
  hexToRgb,
  rgbToHex,
  streamingMarkdown,
  themeVars,
  validColor,
  validSpec,
} from "./quickui.js";

test('Canvas account preferences stay outside message and chat appearance requests', () => {
  const value = {...DEFAULTS, canvas: {inherit: false, accent: '#16804a'}};
  const override = appearanceOnly(value);
  assert.deepEqual(Object.keys(override).sort(), ['appearance', 'color', 'density', 'radius', 'style']);
  assert.deepEqual(override.color, value.color);
});
import { parseColor, contrast } from "./vendor/answer-me-with-html/color.js";
import { parseSequence } from "./vendor/answer-me-with-html/sequence.js";
import { niceScale } from "./vendor/answer-me-with-html/scale.js";

test("recoloring changes presentation without mutating saved content", () => {
  const spec = Object.freeze({
    version: 1,
    blocks: [{ type: "markdown", text: "Saved content" }],
  });
  const before = JSON.stringify(spec);
  const blue = {
    ...DEFAULTS,
    color: {
      mode: "gradient",
      colors: ["#0000ff", "#7c3aed"],
      angle: 90,
      stops: [0, 100],
    },
  };
  const green = {
    ...DEFAULTS,
    color: { mode: "solid", colors: ["#008800"], angle: 90, stops: [0] },
  };
  assert.notEqual(
    themeVars(blue, false)["--qui-fill"],
    themeVars(green, false)["--qui-fill"],
  );
  assert.equal(JSON.stringify(spec), before);
  assert.equal(colorCss(green.color), "#008800");
});
test("custom accent text meets contrast in light and dark appearance", () => {
  for (const dark of [true, false])
    for (const color of [
      "#ffffff",
      "#000000",
      "#ffff00",
      "#008800",
      "#ff00ff",
    ]) {
      const vars = themeVars(
        {
          ...DEFAULTS,
          color: { mode: "solid", colors: [color], angle: 0, stops: [0] },
        },
        dark,
      );
      assert.ok(
        contrast(
          parseColor(vars["--qui-ink"]),
          parseColor(dark ? "#171c24" : "#ffffff"),
        ) >= 4.5,
      );
    }
});
test("color values reject CSS injection and invalid gradient stops", () => {
  assert.equal(
    validColor({ ...DEFAULTS.color, colors: ["url(javascript:alert(1))"] }),
    false,
  );
  assert.equal(
    validColor({
      mode: "gradient",
      colors: ["#000000", "#ffffff"],
      angle: 90,
      stops: [90, 0],
    }),
    false,
  );
  assert.deepEqual(hexToRgb("#0088ff"), [0, 136, 255]);
  assert.equal(rgbToHex([0, 136, 255]), "#0088ff");
});
test("trusted calculators compute locally and handle zero interest", () => {
  assert.equal(calculate("sum", [3, 4]), 7);
  assert.equal(calculate("product", [3, 4]), 12);
  assert.ok(Math.abs(calculate("compound", [100, 10, 2]) - 121) < 1e-8);
  assert.equal(calculate("loan", [1200, 0, 1]), 100);
  assert.equal(calculate("loan", [100, 10, 0]), null);
  assert.equal(calculate("compound", [1e12, 1e12, 1e12]), null);
});
test("streaming keeps partial UI JSON out of visible Markdown", () => {
  assert.equal(streamingMarkdown('Intro\n```quickui\n{"version":1'), "Intro");
  assert.equal(
    streamingMarkdown("```python\nprint(1)\n```"),
    "```python\nprint(1)\n```",
  );
});
test("schema guard handles malformed and executable stored specs", () => {
  assert.equal(
    validSpec({ version: 1, blocks: [{ type: "markdown", text: "safe" }] }),
    true,
  );
  for (const block of [
    { type: "html", text: "<script/>" },
    { type: "table", columns: ["A"], rows: [["A", "B"]] },
    {
      type: "diagram",
      syntax: "mermaid",
      text: 'graph LR\nclick A "javascript:alert(1)"',
    },
    { type: "calculator", operation: "eval", inputs: [] },
    { type: "checklist", items: [null] },
  ]) {
    let result;
    try {
      result = validSpec({ version: 1, blocks: [block] });
    } catch {
      result = false;
    }
    assert.equal(result, false);
  }
});
test("adapted reference parser and scale are local deterministic assets", () => {
  const parsed = parseSequence(
    "Client -> Server: request\nServer --> Client: response",
  );
  assert.deepEqual(parsed.participants, ["Client", "Server"]);
  assert.equal(parsed.steps[1].dashed, true);
  assert.throws(() => parseSequence("invalid input"));
  assert.ok(niceScale(73).max >= 73);
});

test("preset labels stay outside the strict persisted color contract", () => {
  for (const preset of PRESETS) {
    const selection = colorSelection(preset);
    assert.equal("name" in selection, false);
    assert.equal(validColor(selection), true);
    assert.deepEqual(Object.keys(selection).sort(), [
      "angle",
      "colors",
      "mode",
      "stops",
    ]);
  }
});

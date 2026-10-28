import {CHART_COLORS} from './intelligentUI.js';
import { DEFAULTS, colorCss, themeVars, validColor } from './quickui.js';

export const CANVAS_DEFAULTS = {
  inherit: true, accent: DEFAULTS.color.colors[0], widget_color: DEFAULTS.color,
  chart_colors: CHART_COLORS, appearance: 'system', density: 'comfortable',
};
const hex = value => /^#[0-9a-f]{6}$/i.test(value || '');
export function canvasAppearance(preferences = DEFAULTS, systemDark = false) {
  const canvas = {...CANVAS_DEFAULTS, ...preferences.canvas};
  const inherited = canvas.inherit;
  const color = inherited ? preferences.color : canvas.widget_color;
  const widget = {...DEFAULTS, ...preferences, color:validColor(color) ? color : DEFAULTS.color,
    appearance:inherited ? preferences.appearance : canvas.appearance,
    density:inherited ? preferences.density : canvas.density};
  if(widget.appearance==='system')widget.appearance=systemDark?'dark':'light';
  const vars = themeVars(widget, false);
  const accent = inherited ? themeVars(preferences, false)['--qui-accent'] : hex(canvas.accent) ? canvas.accent : CANVAS_DEFAULTS.accent;
  const charts = inherited ? (widget.color.mode === 'system' ? CANVAS_DEFAULTS.chart_colors : widget.color.colors) : canvas.chart_colors;
  return {widget, accent, charts: Array.isArray(charts) && charts.length && charts.every(hex) ? charts : CANVAS_DEFAULTS.chart_colors,
    vars:{'--accent':accent,'--color-primary':accent,'--canvas-widget-accent':vars['--qui-accent'],
      '--canvas-widget-fill':colorCss(widget.color),'--canvas-radius':vars['--qui-radius']}};
}

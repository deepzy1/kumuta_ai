// Adapted from Answer me with HTML; see LICENSE and README.md.
import { ComponentError, contentLines } from "./error.js";

const RE = {
  participants: /^participants?\s*[:：]\s*(.+)$/i,
  note: /^note\s+([^:：]+)[:：]\s*(.+)$/i,
  divider: /^==\s*(.+?)\s*==$/,
  msg: /^([^:：]+?)\s*(-->|->)\s*([^:：]+?)\s*(?:[:：]\s*(.*))?$/,
};

export function parseSequence(text) {
  const participants = [];
  const add = (p) => { if (!participants.includes(p)) participants.push(p); };
  const steps = [];
  for (const { text: t, line } of contentLines(text)) {
    let m;
    if ((m = t.match(RE.participants))) {
      m[1].split(/[,，]/).map((s) => s.trim()).filter(Boolean).forEach(add);
    } else if ((m = t.match(RE.note))) {
      const over = m[1].split(/[,，]/).map((s) => s.trim()).filter(Boolean);
      over.forEach(add);
      steps.push({ kind: 'note', over, text: m[2].trim(), line });
    } else if ((m = t.match(RE.divider))) {
      steps.push({ kind: 'divider', text: m[1], line });
    } else if ((m = t.match(RE.msg))) {
      add(m[1]);
      add(m[3]);
      steps.push({ kind: 'msg', from: m[1], to: m[3], dashed: m[2] === '-->', label: (m[4] ?? '').trim(), line });
    } else {
      throw new ComponentError(`sequence cannot parse "${t}". Write a message as A -> B: label (--> is a dashed return) and a note as note A: text`, line);
    }
  }
  if (!participants.length) throw new ComponentError('sequence needs at least one message', 1);
  return { participants, steps };
}


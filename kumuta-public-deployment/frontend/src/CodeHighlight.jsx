import React from "react";
import SyntaxHighlighter from "react-syntax-highlighter/dist/esm/prism-light";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript";
import jsx from "react-syntax-highlighter/dist/esm/languages/prism/jsx";
import tsx from "react-syntax-highlighter/dist/esm/languages/prism/tsx";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import css from "react-syntax-highlighter/dist/esm/languages/prism/css";
import markup from "react-syntax-highlighter/dist/esm/languages/prism/markup";
import sql from "react-syntax-highlighter/dist/esm/languages/prism/sql";
import yaml from "react-syntax-highlighter/dist/esm/languages/prism/yaml";
import java from "react-syntax-highlighter/dist/esm/languages/prism/java";
import cpp from "react-syntax-highlighter/dist/esm/languages/prism/cpp";
import go from "react-syntax-highlighter/dist/esm/languages/prism/go";
import rust from "react-syntax-highlighter/dist/esm/languages/prism/rust";
const languages = {
  python,
  javascript,
  typescript,
  jsx,
  tsx,
  json,
  bash,
  css,
  markup,
  sql,
  yaml,
  java,
  cpp,
  go,
  rust,
};
for (const [name, grammar] of Object.entries(languages))
  SyntaxHighlighter.registerLanguage(name, grammar);
const aliases = {
  js: "javascript",
  ts: "typescript",
  py: "python",
  html: "markup",
  xml: "markup",
  sh: "bash",
  shell: "bash",
  yml: "yaml",
};
export default function CodeHighlight({ language, code }) {
  const name = aliases[language] || language;
  return (
    <SyntaxHighlighter
      language={name in languages ? name : "text"}
      style={oneDark}
      PreTag="div"
      wrapLongLines={false}
    >
      {code}
    </SyntaxHighlighter>
  );
}

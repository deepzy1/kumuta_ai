import React, {
  lazy,
  memo,
  Suspense,
  useEffect,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, Code2, Workflow } from "lucide-react";

export function CopyButton({ text, label = "Copy", className = "" }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const timer = useRef();
  useEffect(() => () => clearTimeout(timer.current), []);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setFailed(false);
    } catch {
      setFailed(true);
    }
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setCopied(false);
      setFailed(false);
    }, 2000);
  }
  return (
    <button
      type="button"
      className={`copy-button ${className}`}
      onClick={copy}
      aria-label={label}
      title={label}
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
      <span>{failed ? "Copy unavailable" : copied ? "Copied" : label}</span>
    </button>
  );
}

const CodeHighlight = lazy(() => import("./CodeHighlight"));
let diagramCounter = 0;
let renderQueue = Promise.resolve();
function Diagram({ code }) {
  const target = useRef(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setError(false);
    // Mermaid has global parser state; serialize concurrent diagrams.
    renderQueue = renderQueue
      .catch(() => {})
      .then(async () => {
        try {
          const [{ default: mermaid }, { default: DOMPurify }] =
            await Promise.all([import("mermaid"), import("dompurify")]);
          mermaid.initialize({
            startOnLoad: false,
            securityLevel: "strict",
            theme: "neutral",
            htmlLabels: false,
            maxTextSize: 50000,
            maxEdges: 500,
            secure: [
              "securityLevel",
              "startOnLoad",
              "maxTextSize",
              "maxEdges",
              "htmlLabels",
              "flowchart",
              "suppressErrorRendering",
            ],
            flowchart: { htmlLabels: false },
            suppressErrorRendering: true,
          });
          const { svg } = await mermaid.render(
            `kumuta-diagram-${++diagramCounter}`,
            code,
          );
          if (!cancelled && target.current)
            target.current.innerHTML = DOMPurify.sanitize(svg, {
              USE_PROFILES: { svg: true, svgFilters: true },
            });
        } catch {
          if (!cancelled) setError(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [code]);
  return error ? (
    <p className="diagram-error">
      This diagram could not be rendered. Its source is available below.
    </p>
  ) : (
    <div className="diagram" ref={target} aria-label="Mermaid diagram" />
  );
}

function CodeBlock({ children, generating }) {
  const child = React.Children.toArray(children)[0];
  const language =
    /language-([\w+-]+)/.exec(child?.props?.className || "")?.[1] || "text";
  const code = String(child?.props?.children ?? "").replace(/\n$/, "");
  return (
    <div className="code-block">
      <div className="code-header">
        <span>
          {language === "mermaid" ? (
            <Workflow size={14} />
          ) : (
            <Code2 size={14} />
          )}{" "}
          {language}
        </span>
        <CopyButton text={code} />
      </div>
      {language === "mermaid" && !generating && <Diagram code={code} />}
      <Suspense
        fallback={
          <pre className="plain-code">
            <code>{code}</code>
          </pre>
        }
      >
        <CodeHighlight language={language} code={code} />
      </Suspense>
    </div>
  );
}

function Markdown({ text, generating = false }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => (
            <CodeBlock generating={generating}>{children}</CodeBlock>
          ),
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="table-scroll">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export default memo(Markdown);

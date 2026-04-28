import { useState, useCallback } from "react";
import { Copy, Check } from "lucide-react";

interface JsonViewerProps {
  value: unknown;
  className?: string;
  maxHeight?: string;
}

export function JsonViewer({ value, className = "", maxHeight = "auto" }: JsonViewerProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  }, [value]);

  const jsonString = typeof value === "string" ? value : JSON.stringify(value, null, 2);

  return (
    <div className={`relative group bg-bg border border-line rounded p-2 overflow-auto ${className}`} style={{ maxHeight }}>
      <button
        onClick={handleCopy}
        className="absolute top-1.5 right-1.5 p-1 rounded bg-surface-strong border border-line opacity-0 group-hover:opacity-100 transition-opacity hover:bg-surface"
        title="Copy to clipboard"
      >
        {copied ? (
          <Check className="w-3 h-3 text-accent" />
        ) : (
          <Copy className="w-3 h-3 text-muted" />
        )}
      </button>
      <pre className="text-[11px] font-mono leading-relaxed pr-6">
        <HighlightedJson text={jsonString} />
      </pre>
    </div>
  );
}

function HighlightedJson({ text }: { text: string }) {
  // Simple tokenizer for JSON syntax highlighting
  const tokens = tokenizeJson(text);
  return (
    <>
      {tokens.map((tok, i) => (
        <span key={i} className={tokenClass(tok.type)}>
          {tok.value}
        </span>
      ))}
    </>
  );
}

type TokenType =
  | "key"
  | "string"
  | "number"
  | "boolean"
  | "null"
  | "punctuation"
  | "whitespace"
  | "unknown";

interface Token {
  type: TokenType;
  value: string;
}

function tokenizeJson(text: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;

  while (i < text.length) {
    const ch = text[i];

    // Whitespace
    if (/\s/.test(ch)) {
      let ws = "";
      while (i < text.length && /\s/.test(text[i])) {
        ws += text[i];
        i++;
      }
      tokens.push({ type: "whitespace", value: ws });
      continue;
    }

    // String
    if (ch === '"') {
      let str = '"';
      i++;
      while (i < text.length && text[i] !== '"') {
        if (text[i] === "\\" && i + 1 < text.length) {
          str += text[i] + text[i + 1];
          i += 2;
        } else {
          str += text[i];
          i++;
        }
      }
      if (i < text.length) {
        str += '"';
        i++;
      }
      // Check if it's a key (followed by colon with optional whitespace)
      let j = i;
      while (j < text.length && /\s/.test(text[j])) j++;
      const isKey = j < text.length && text[j] === ":";
      tokens.push({ type: isKey ? "key" : "string", value: str });
      continue;
    }

    // Number
    if (/[-0-9]/.test(ch)) {
      let num = "";
      while (i < text.length && /[-0-9.eE+]/.test(text[i])) {
        num += text[i];
        i++;
      }
      tokens.push({ type: "number", value: num });
      continue;
    }

    // Boolean / null
    if (text.startsWith("true", i)) {
      tokens.push({ type: "boolean", value: "true" });
      i += 4;
      continue;
    }
    if (text.startsWith("false", i)) {
      tokens.push({ type: "boolean", value: "false" });
      i += 5;
      continue;
    }
    if (text.startsWith("null", i)) {
      tokens.push({ type: "null", value: "null" });
      i += 4;
      continue;
    }

    // Punctuation
    if (/[{}\[\],:]/.test(ch)) {
      tokens.push({ type: "punctuation", value: ch });
      i++;
      continue;
    }

    // Unknown
    tokens.push({ type: "unknown", value: ch });
    i++;
  }

  return tokens;
}

function tokenClass(type: TokenType): string {
  switch (type) {
    case "key":
      return "text-text font-medium";
    case "string":
      return "text-accent";
    case "number":
      return "text-info";
    case "boolean":
      return "text-warning font-medium";
    case "null":
      return "text-warning font-medium";
    case "punctuation":
      return "text-muted";
    case "whitespace":
      return "";
    default:
      return "text-muted";
  }
}

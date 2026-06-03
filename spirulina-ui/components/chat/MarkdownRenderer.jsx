"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useTheme } from "@/lib/ThemeContext";

export default function MarkdownRenderer({ content, dimmed = false }) {
  const { C } = useTheme();
  if (!content?.trim()) return null;

  const components = {
    h1: ({ node, children }) => (
      <div style={{ fontSize: 16, fontWeight: 700, color: C.text, margin: "16px 0 8px", lineHeight: 1.3 }}>
        {children}
      </div>
    ),
    h2: ({ node, children }) => (
      <div style={{
        fontSize: 13.5, fontWeight: 600, color: C.text,
        margin: "16px 0 8px", paddingBottom: 6,
        borderBottom: `1px solid ${C.border}`,
      }}>
        {children}
      </div>
    ),
    h3: ({ node, children }) => (
      <div style={{
        fontSize: 11, fontWeight: 600, color: C.text2,
        margin: "13px 0 5px", fontFamily: C.mono,
        letterSpacing: 0.8, textTransform: "uppercase",
        display: "flex", alignItems: "center", gap: 7,
      }}>
        <span style={{ width: 2, height: 11, background: C.green, borderRadius: 1, display: "inline-block", flexShrink: 0 }} />
        {children}
      </div>
    ),
    p: ({ node, children }) => (
      <p style={{ margin: "0 0 9px", color: C.text2, lineHeight: 1.7, fontSize: 13.5 }}>
        {children}
      </p>
    ),
    strong: ({ node, children }) => (
      <strong style={{ color: C.text, fontWeight: 600 }}>{children}</strong>
    ),
    em: ({ node, children }) => (
      <em style={{ color: C.text2, fontStyle: "italic" }}>{children}</em>
    ),
    code: ({ node, className, children }) => {
      const isBlock = /language-/.test(className || "");
      if (!isBlock) {
        return (
          <code style={{
            background: C.card2, color: C.textCode,
            padding: "1px 6px", borderRadius: 4,
            fontFamily: C.mono, fontSize: 12,
            border: `1px solid ${C.border}`,
          }}>
            {children}
          </code>
        );
      }
      return (
        <code style={{ fontFamily: C.mono, fontSize: 12, color: C.textCode, lineHeight: 1.65 }}>
          {children}
        </code>
      );
    },
    pre: ({ node, children }) => (
      <pre style={{
        background: C.panel, border: `1px solid ${C.border}`,
        borderRadius: 8, padding: "12px 14px", margin: "8px 0",
        overflowX: "auto", fontFamily: C.mono, fontSize: 12,
      }}>
        {children}
      </pre>
    ),
    table: ({ node, children }) => (
      <div style={{ overflowX: "auto", margin: "8px 0" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, fontFamily: C.mono }}>
          {children}
        </table>
      </div>
    ),
    thead: ({ node, children }) => (
      <thead style={{ background: C.card2, borderBottom: `1px solid ${C.border2}` }}>
        {children}
      </thead>
    ),
    tbody: ({ node, children }) => <tbody>{children}</tbody>,
    tr: ({ node, children }) => (
      <tr style={{ borderBottom: `1px solid ${C.border}` }}>{children}</tr>
    ),
    th: ({ node, children }) => (
      <th style={{
        padding: "7px 12px", textAlign: "left",
        color: C.green, fontWeight: 600, fontSize: 10.5,
        letterSpacing: 0.4, textTransform: "uppercase",
      }}>
        {children}
      </th>
    ),
    td: ({ node, children }) => (
      <td style={{ padding: "7px 12px", color: C.text2, verticalAlign: "top", lineHeight: 1.55 }}>
        {children}
      </td>
    ),
    blockquote: ({ node, children }) => (
      <div style={{
        borderLeft: `3px solid ${C.green}`,
        background: C.card2, borderRadius: "0 6px 6px 0",
        padding: "9px 13px", margin: "8px 0", color: C.text2, fontSize: 13,
      }}>
        {children}
      </div>
    ),
    ul: ({ node, children }) => (
      <ul style={{ padding: "0 0 0 4px", margin: "5px 0", listStyle: "none" }}>{children}</ul>
    ),
    ol: ({ node, children }) => (
      <ol style={{ paddingLeft: 18, margin: "5px 0" }}>{children}</ol>
    ),
    li: ({ node, children }) => (
      <li style={{
        margin: "4px 0", fontSize: 13.5, color: C.text2,
        display: "flex", gap: 8, alignItems: "flex-start", lineHeight: 1.65,
      }}>
        <span style={{ color: C.green, flexShrink: 0, marginTop: 5, fontSize: 6, lineHeight: 1 }}>◆</span>
        <span style={{ flex: 1 }}>{children}</span>
      </li>
    ),
    input: ({ node, type, checked, ...props }) => {
      if (type === "checkbox") {
        return (
          <span style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: 14, height: 14, borderRadius: 3, flexShrink: 0,
            marginRight: 5, marginTop: 1,
            background: checked ? C.green : "transparent",
            border: `1.5px solid ${checked ? C.green : C.border2}`,
            fontSize: 9, color: C.bg, fontWeight: 700,
          }}>
            {checked ? "✓" : ""}
          </span>
        );
      }
      return <input type={type} checked={checked} {...props} />;
    },
    hr: () => (
      <div style={{
        height: 1, margin: "14px 0",
        background: `linear-gradient(90deg, transparent, ${C.border2} 20%, ${C.border2} 80%, transparent)`,
      }} />
    ),
    a: ({ node, children }) => (
      <span style={{ color: C.green, textDecoration: "underline", textUnderlineOffset: 2 }}>
        {children}
      </span>
    ),
  };

  return (
    <div className="md-body" style={{ opacity: dimmed ? 0.65 : 1, transition: "opacity .2s" }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

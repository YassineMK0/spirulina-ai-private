# SEO & GEO — SpirulinaAI

## What is SEO?

**Search Engine Optimization** — making your app discoverable on Google, Bing, and DuckDuckGo.

Search engine crawlers (bots) visit your site, read the HTML in your `<head>`, and use it to decide how to rank and display your page in search results.

## What is GEO?

**Generative Engine Optimization** — making your app cited by AI search engines like Perplexity, ChatGPT Search, and Gemini.

When someone asks Perplexity *"what tools exist for spirulina cultivation monitoring?"*, it crawls the web and synthesizes an answer. GEO is about making sure SpirulinaAI shows up in that answer.

---

## What we implemented

### 1. `app/layout.js` — Rich metadata

The `metadata` export in Next.js 16 automatically injects everything into `<head>`.

**Title & description**
```js
title: {
  default: "SpirulinaAI — Intelligent Spirulina Cultivation Assistant",
  template: "%s | SpirulinaAI",   // used by sub-pages
}
description: "AI-powered assistant for spirulina cultivation..."
```

**Keywords** — help search engines categorize the app:
```
spirulina cultivation, spirulina AI assistant, microalgae monitoring,
precision agriculture, IoT sensor dashboard, harvest prediction,
anomaly detection, RAG chatbot, LangGraph agent
```

**Open Graph tags** — controls the link preview card on LinkedIn, WhatsApp, Discord:
```js
openGraph: {
  type: "website",
  title: "SpirulinaAI — Intelligent Spirulina Cultivation Assistant",
  description: "...",
  images: [{ url: "/icon-512.svg", width: 512, height: 512 }],
}
```

**Twitter Card** — controls how the link looks on X/Twitter:
```js
twitter: {
  card: "summary",
  title: "...",
  images: ["/icon-512.svg"],
  creator: "@YassineMK0",
}
```

**Robots directives** — tells Google how to crawl the page:
```js
robots: {
  index: true,
  follow: true,
  googleBot: { "max-snippet": -1, "max-image-preview": "large" }
}
```

---

### 2. JSON-LD Structured Data (`app/layout.js`)

A hidden block of JSON injected into `<head>` that describes the app as a machine-readable entity. Google uses this to generate rich results (feature lists, app category, pricing).

```json
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "SpirulinaAI",
  "applicationCategory": "AgricultureApplication",
  "featureList": [
    "RAG knowledge base from 20+ scientific documents",
    "Real-time pH, EC, DO, temperature, and turbidity monitoring",
    "ML-based anomaly detection (LSTM autoencoder)",
    "LightGBM turbidity and harvest scheduling models",
    "Proactive threshold alerts via Server-Sent Events",
    "Dual-LLM pipeline (intent routing + response generation)"
  ],
  "offers": { "@type": "Offer", "price": "0" }
}
```

---

### 3. `app/sitemap.js` — Sitemap

A sitemap is a map of all your pages handed directly to Google so it doesn't have to guess what to crawl.

```js
// Accessed at: /sitemap.xml
export default function sitemap() {
  return [{ url: BASE_URL, changeFrequency: "weekly", priority: 1 }];
}
```

Google Search Console accepts this URL to index the app faster.

---

### 4. `app/robots.js` — Robots file

Tells crawlers which pages to visit and which to skip. Also the key GEO file — AI crawlers are blocked by default industry-wide unless you explicitly allow them.

```js
// Accessed at: /robots.txt
rules: [
  // Standard: allow everything except internal routes
  { userAgent: "*",           allow: "/", disallow: ["/api/", "/_next/"] },

  // GEO: explicitly allow AI crawlers
  { userAgent: "GPTBot",          allow: "/" },   // OpenAI / ChatGPT
  { userAgent: "ChatGPT-User",    allow: "/" },
  { userAgent: "PerplexityBot",   allow: "/" },   // Perplexity
  { userAgent: "Claude-Web",      allow: "/" },   // Anthropic
  { userAgent: "anthropic-ai",    allow: "/" },
  { userAgent: "Gemini",          allow: "/" },   // Google AI
  { userAgent: "Googlebot-Extended", allow: "/" },
  { userAgent: "cohere-ai",       allow: "/" },   // Cohere
]
```

Without these rules, AI crawlers skip the site entirely and it never appears in AI-generated answers.

---

### 5. `public/llms.txt` — GEO: LLM Crawler Description

A plain-text file at `/llms.txt` — the emerging standard for AI crawlers (like `robots.txt` but written for LLMs to read and understand). It describes the app in factual, structured plain text with no navigation or ads — just the information an AI needs to accurately summarize and cite the app.

```
# SpirulinaAI

> An AI-powered cultivation assistant for spirulina farmers and researchers.

## What SpirulinaAI can help with
- Cultivation knowledge (pH, temperature, EC, culture media)
- Troubleshooting (contamination, color changes, foam)
- Real-time sensor monitoring (pH, EC, DO, temperature, turbidity)
- Anomaly detection, turbidity prediction, harvest scheduling
- Proactive threshold alerts via SSE

## Technology
- Frontend: Next.js 16 PWA
- Backend: FastAPI + LangGraph
- LLMs: Groq Llama 3.3 70B + Llama 3.1 8B
- RAG: ChromaDB, BAAI/bge-m3, BM25+dense hybrid retrieval
- ML: LSTM autoencoder (M1), LightGBM turbidity (M2), LightGBM harvest (M3)
```

---

## Environment variable

Both `sitemap.js`, `robots.js`, and `layout.js` read the base URL from:

```env
NEXT_PUBLIC_BASE_URL=https://your-domain.com
```

If not set, it defaults to `https://spirulina-ai.com`. Set this before deploying.

---

## Summary table

| File | Type | Purpose |
|------|------|---------|
| `app/layout.js` — `metadata` | SEO | Title, description, keywords, Open Graph, Twitter Card |
| `app/layout.js` — JSON-LD | SEO | Structured data for Google rich results |
| `app/layout.js` — `viewport` | PWA + SEO | Theme color, viewport, Apple Web App |
| `app/sitemap.js` | SEO | `/sitemap.xml` — page map for Google/Bing |
| `app/robots.js` | SEO + GEO | `/robots.txt` — crawl rules + AI bot allowlist |
| `public/llms.txt` | GEO | `/llms.txt` — plain-text description for LLM crawlers |

**SEO = rank on Google. GEO = get cited by AI.** Both are handled without any external library — purely through Next.js 16 file conventions and a static text file.

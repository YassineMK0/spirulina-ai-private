import "./globals.css";
import ServiceWorkerRegistration from "@/components/ServiceWorkerRegistration";

const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || "https://spirulina-ai.com";

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "SpirulinaAI",
  applicationCategory: "AgricultureApplication",
  operatingSystem: "Web",
  url: BASE_URL,
  description:
    "An AI-powered cultivation assistant for spirulina farmers. Combines RAG knowledge retrieval, real-time sensor monitoring, and ML-based harvest scheduling to provide intelligent diagnostics and proactive alerts.",
  featureList: [
    "RAG knowledge base from 20+ scientific documents",
    "Real-time pH, EC, DO, temperature, and turbidity monitoring",
    "ML-based anomaly detection (LSTM autoencoder)",
    "LightGBM turbidity and harvest scheduling models",
    "Proactive threshold alerts via Server-Sent Events",
    "Dual-LLM pipeline (intent routing + response generation)",
  ],
  keywords:
    "spirulina, cultivation, AI assistant, precision agriculture, RAG, LLM, IoT sensors, harvest prediction",
  author: { "@type": "Person", name: "YassineMK0" },
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
};

export const metadata = {
  metadataBase: new URL(BASE_URL),
  title: {
    default: "SpirulinaAI — Intelligent Spirulina Cultivation Assistant",
    template: "%s | SpirulinaAI",
  },
  description:
    "AI-powered assistant for spirulina cultivation. Real-time sensor monitoring, harvest prediction, anomaly detection, and scientific RAG knowledge base — all in one interface.",
  keywords: [
    "spirulina cultivation",
    "spirulina AI assistant",
    "microalgae monitoring",
    "precision agriculture",
    "IoT sensor dashboard",
    "harvest prediction",
    "anomaly detection",
    "RAG chatbot",
    "LangGraph agent",
  ],
  authors: [{ name: "YassineMK0" }],
  creator: "YassineMK0",
  publisher: "SpirulinaAI",
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-snippet": -1,
      "max-image-preview": "large",
    },
  },
  openGraph: {
    type: "website",
    locale: "en_US",
    url: BASE_URL,
    siteName: "SpirulinaAI",
    title: "SpirulinaAI — Intelligent Spirulina Cultivation Assistant",
    description:
      "AI-powered assistant for spirulina cultivation. Real-time sensor monitoring, harvest prediction, anomaly detection, and scientific RAG knowledge base.",
    images: [{ url: "/icon-512.svg", width: 512, height: 512, alt: "SpirulinaAI logo" }],
  },
  twitter: {
    card: "summary",
    title: "SpirulinaAI — Intelligent Spirulina Cultivation Assistant",
    description:
      "AI-powered assistant for spirulina cultivation. Real-time sensor monitoring, harvest prediction, and scientific RAG knowledge base.",
    images: ["/icon-512.svg"],
    creator: "@YassineMK0",
  },
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "SpirulinaAI",
  },
  formatDetection: { telephone: false },
  other: { "mobile-web-app-capable": "yes" },
};

export const viewport = {
  themeColor: "#163A20",
  width: "device-width",
  initialScale: 1,
  minimumScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" style={{ height: "100%" }}>
      <body style={{ height: "100%", margin: 0 }}>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        <ServiceWorkerRegistration />
        {children}
      </body>
    </html>
  );
}

export default function manifest() {
  return {
    name: "SpirulinaAI",
    short_name: "SpirulinaAI",
    description: "Autonomous spirulina cultivation intelligence",
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0d1f12",
    theme_color: "#163A20",
    categories: ["productivity", "agriculture"],
    icons: [
      {
        src: "/icon-192.svg",
        sizes: "192x192",
        type: "image/svg+xml",
        purpose: "any",
      },
      {
        src: "/icon-512.svg",
        sizes: "512x512",
        type: "image/svg+xml",
        purpose: "any maskable",
      },
      {
        src: "/favicon.ico",
        sizes: "any",
        type: "image/x-icon",
      },
    ],
  };
}

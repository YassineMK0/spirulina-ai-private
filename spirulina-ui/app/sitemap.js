const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || "https://spirulina-ai.com";

export default function sitemap() {
  return [
    {
      url: BASE_URL,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 1,
    },
  ];
}

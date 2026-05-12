import "./globals.css";

export const metadata = {
  title: "SpirulinaAI",
  description: "Autonomous spirulina cultivation intelligence",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" style={{ height: "100%" }}>
      <body style={{ height: "100%", margin: 0 }}>{children}</body>
    </html>
  );
}

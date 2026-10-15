import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Air-Gapped RAG | Local PDF Document Intelligence",
  description: "Local-first, air-gapped PDF question-answering with exact page citations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full bg-slate-50 antialiased">
      <body className="min-h-full flex flex-col font-sans text-slate-900">
        {children}
      </body>
    </html>
  );
}

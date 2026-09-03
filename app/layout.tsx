import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PostMeet — Meeting intelligence without invented facts",
  description: "Turn recordings and transcripts into evidence-bound meeting pages and YOOtheme layouts.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

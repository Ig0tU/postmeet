import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PostMeet — Turn meeting recordings into clear, trustworthy records",
  description:
    "Upload a school board or public meeting recording. Get a timestamped transcript and label who is speaking — so everyone gets an accurate record.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

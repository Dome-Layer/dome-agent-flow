import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";
import { NavHeader } from "@/components/NavHeader";
import { StagingBanner, ToolFooter } from "@dome-layer/dome-ui";
import { THEME_INIT_SCRIPT } from "@dome-layer/dome-ui/utils";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Agent Flow | DOME",
  description: "Governed invoice-to-approval workflow with a human-in-the-loop gate.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Sets the theme before first paint, so there is no flash; the rule lives in dome-ui. */}
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="flex flex-col min-h-screen">
        <StagingBanner environment={process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT} />
        <AuthProvider>
          <NavHeader />
          {children}
          <ToolFooter toolName="Agent Flow" />
        </AuthProvider>
      </body>
    </html>
  );
}

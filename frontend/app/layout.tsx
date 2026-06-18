import type { Metadata } from "next";
import { headers } from "next/headers";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";
import { NavHeader } from "@/components/NavHeader";
import { StagingBanner, ToolFooter } from "@dome-layer/dome-ui";

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
  title: "Agent Flow — Dome",
  description: "Governed invoice-to-approval workflow with a human-in-the-loop gate.",
};

// Prevents theme flash before first paint — reads the dome-theme cookie (shared
// across all *.domelayer.com subdomains) then falls back to localStorage.
const themeScript = `
(function() {
  try {
    var cookie = document.cookie.split('; ').find(function(r){ return r.startsWith('dome-theme='); });
    var cookieVal = cookie ? cookie.split('=')[1] : null;
    var saved = (cookieVal === 'dark' || cookieVal === 'light') ? cookieVal : localStorage.getItem('dome-theme');
    var theme = (saved === 'dark' || saved === 'light')
      ? saved
      : (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
  } catch (e) {}
})();
`;

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: themeScript }} />
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

import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./context/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
    "./node_modules/@dome-layer/dome-ui/dist/**/*.js",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", '"Helvetica Neue"', "Arial", "sans-serif"],
        mono: ['"JetBrains Mono"', '"Fira Code"', "monospace"],
        display: ["Inter", '"Helvetica Neue"', "Arial", "sans-serif"],
        body: ["Inter", '"Helvetica Neue"', "Arial", "sans-serif"],
      },
      colors: {
        dome: {
          bg: {
            primary: "var(--color-bg-subtle)",
            secondary: "var(--color-bg-base)",
            tertiary: "var(--color-bg-muted)",
            accent: "var(--color-bg-accent)",
          },
          text: {
            primary: "var(--color-text-primary)",
            secondary: "var(--color-text-secondary)",
            muted: "var(--color-text-tertiary)",
            accent: "var(--color-text-accent)",
          },
          accent: {
            DEFAULT: "var(--color-accent)",
            hover: "var(--color-accent-hover)",
            active: "var(--color-accent-active)",
            subtle: "var(--color-accent-subtle)",
          },
          border: {
            DEFAULT: "var(--color-border-default)",
            subtle: "var(--color-border-subtle)",
            strong: "var(--color-border-strong)",
            accent: "var(--color-border-accent)",
          },
          status: {
            critical: "var(--color-error)",
            major: "var(--color-warning)",
            minor: "var(--color-accent)",
            success: "var(--color-success)",
          },
        },
      },
      borderRadius: {
        dome: "8px",
        "dome-card": "12px",
      },
      letterSpacing: {
        dome: "0.18em",
        "dome-tight": "-0.025em",
        "dome-tighter": "-0.03em",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        spin: {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
      },
      animation: {
        "fade-up": "fadeUp 0.4s ease forwards",
        spin: "spin 0.8s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0b0d12",
          panel: "#11141b",
          elevated: "#171a23",
        },
        border: {
          DEFAULT: "#262b38",
          subtle: "#1c212c",
        },
        accent: {
          DEFAULT: "#3b82f6",
          hover: "#2563eb",
        },
        text: {
          DEFAULT: "#e7eaf0",
          muted: "#8b93a7",
          dim: "#5b6478",
        },
        risk: {
          low: "#10b981",
          medium: "#f59e0b",
          high: "#ef4444",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

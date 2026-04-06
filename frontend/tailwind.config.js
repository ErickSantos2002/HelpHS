/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#10B981",
          50: "#ecfdf5",
          100: "#d1fae5",
          200: "#a7f3d0",
          300: "#6ee7b7",
          400: "#34d399",
          500: "#10B981",
          600: "#059669",
          700: "#047857",
          800: "#065f46",
          900: "#064e3b",
        },
        background: {
          DEFAULT: "#0F172A",
          surface: "#1E293B",
          elevated: "#334155",
        },
        danger: {
          DEFAULT: "#EF4444",
          50: "#fef2f2",
          100: "#fee2e2",
          400: "#f87171",
          500: "#EF4444",
          600: "#dc2626",
          700: "#b91c1c",
        },
        warning: {
          DEFAULT: "#F59E0B",
          50: "#fffbeb",
          100: "#fef3c7",
          400: "#fbbf24",
          500: "#F59E0B",
          600: "#d97706",
          700: "#b45309",
        },
        info: {
          DEFAULT: "#3B82F6",
          50: "#eff6ff",
          100: "#dbeafe",
          400: "#60a5fa",
          500: "#3B82F6",
          600: "#2563eb",
          700: "#1d4ed8",
        },
        border: {
          DEFAULT: "#334155",
          muted: "#1E293B",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

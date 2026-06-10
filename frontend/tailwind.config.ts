import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: "#0d1117",
        panel: "rgba(12, 18, 29, 0.78)",
        line: "rgba(173, 196, 255, 0.16)",
        cyan: "#7dd3fc",
        gold: "#f4c95d",
        danger: "#ff647c"
      },
      boxShadow: {
        glow: "0 0 40px rgba(125, 211, 252, 0.18)",
        panel: "0 24px 80px rgba(0, 0, 0, 0.35)"
      }
    }
  },
  plugins: []
};

export default config;

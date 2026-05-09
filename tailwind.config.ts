import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./frontend/src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17201b",
        paper: "#f7f3ea",
        field: "#dce8d2",
        leaf: "#287a4f",
        chili: "#b6402a",
        saffron: "#e8a63a",
        civic: "#315d70"
      },
      fontFamily: {
        display: ["Georgia", "Cambria", "serif"],
        body: ["Aptos", "Segoe UI", "sans-serif"]
      },
      boxShadow: {
        line: "0 1px 0 rgba(23, 32, 27, 0.12)",
        lift: "0 18px 45px rgba(49, 93, 112, 0.14)"
      }
    }
  },
  plugins: []
};

export default config;

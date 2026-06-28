/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#EFE6D4",
        stock: "#FBF5E9",
        ink: "#2B2118",
        stamp: "#B33A2B",
        gold: "#C9A227",
        faded: "#8a7d63",
      },
      fontFamily: {
        stamp: ['"Oswald"', "sans-serif"],
        mono: ['"Courier Prime"', "monospace"],
      },
    },
  },
  plugins: [],
};

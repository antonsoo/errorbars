import { defineConfig } from "vite";
import { contentSecurityPolicy } from "./vite.csp";

export default defineConfig({
  base: "/errorbars/",
  plugins: [contentSecurityPolicy()],
  build: {
    target: "es2022",
  },
});

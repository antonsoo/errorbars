import { defineConfig } from "vite";
import { contentSecurityPolicy } from "./vite.csp.ts";

export default defineConfig({
  base: "/errorbars/",
  plugins: [contentSecurityPolicy()],
  build: {
    target: "es2022",
  },
});

import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import { contentSecurityPolicy } from "./vite.csp.ts";

export default defineConfig({
  base: "/errorbars/",
  plugins: [
    contentSecurityPolicy(),
    {
      name: "third-party-notices",
      // Ship the license alongside the bundled adaptation, not only in the source repository.
      generateBundle() {
        for (const [fileName, path] of [
          ["licenses/Python-2.0.txt", "../LICENSES/Python-2.0.txt"],
          ["licenses/THIRD_PARTY_NOTICES.md", "../THIRD_PARTY_NOTICES.md"],
        ] as const) {
          this.emitFile({ type: "asset", fileName, source: readFileSync(new URL(path, import.meta.url)) });
        }
      },
    },
  ],
  build: {
    target: "es2022",
  },
});

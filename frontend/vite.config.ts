import { fileURLToPath } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// The build lands inside the Python package so the wheel ships it (see pyproject.toml,
// [tool.hatch.build.targets.wheel] artifacts). Relative base: the Python server decides
// the URL prefix.
export default defineConfig({
  plugins: [vue()],
  base: "./",
  build: {
    outDir: fileURLToPath(new URL("../src/erdify_studio/_static", import.meta.url)),
    emptyOutDir: true,
  },
});

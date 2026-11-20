import { fileURLToPath } from "node:url";

import ui from "@nuxt/ui/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig, type Plugin } from "vite";

// @iconify/vue falls back to the public Iconify API for an icon that is not bundled.
// The studio must never go online: drop the API hosts, so a missing icon renders
// empty instead of being fetched. Fails the build if @iconify/vue changes the line.
const ICONIFY_API = '{ resources: ["https://api.iconify.design", "https://api2.iconify.design"] }';

function offlineIcons(): Plugin {
  return {
    name: "erdify-studio:offline-icons",
    enforce: "pre",
    transform(code, id) {
      if (!/[\\/]@iconify[\\/]vue[\\/]/.test(id) || !code.includes("configStorage[\"\"]")) {
        return null;
      }
      if (!code.includes(ICONIFY_API)) {
        this.error(`@iconify/vue changed: cannot remove its API hosts from ${id}`);
      }
      return code.replace(ICONIFY_API, "{ resources: [] }");
    },
  };
}

// The build lands inside the Python package so the wheel ships it (see pyproject.toml,
// [tool.hatch.build.targets.wheel] artifacts). Relative base: the Python server decides
// the URL prefix.
export default defineConfig({
  plugins: [
    offlineIcons(),
    vue(),
    ui({
      // No vue-router: the studio is a single page.
      router: false,
      // Bundle the icons the app uses from @iconify-json/lucide: nothing is fetched at
      // runtime (no Iconify API). scripts/check_static.py guards the build.
      icon: { clientBundle: { scan: true } },
      ui: { colors: { primary: "indigo", neutral: "slate" } },
    }),
  ],
  base: "./",
  build: {
    outDir: fileURLToPath(new URL("../src/erdify_studio/_static", import.meta.url)),
    emptyOutDir: true,
  },
  server: {
    // `npm run dev` against a running `erdify-studio --port 8765 --no-browser`; open the
    // dev page with the token of the URL it prints.
    proxy: {
      "/api": {
        target: process.env.STUDIO_API ?? "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
});

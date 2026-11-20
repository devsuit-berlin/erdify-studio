import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
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
// Packages that reach the build outside the JS module graph (CSS @import, generated
// icon data), so thirdPartyLicenses() cannot find them on its own.
const EXTRA_LICENSED = ["@fontsource/jetbrains-mono", "@iconify-json/lucide"];

/** The package directory under node_modules that a module id belongs to. */
function packageDir(id: string): string | null {
  const match = /^(.*[\\/]node_modules[\\/](?:@[^\\/]+[\\/])?[^\\/]+)/.exec(id.replace(/^\0/, ""));
  return match ? match[1] : null;
}

// Emits THIRD_PARTY_LICENSES.txt: the licence text of every package bundled into the
// shipped page (MIT, ISC, OFL … all require it in copies). scripts/check_wheel.py
// checks that the wheel has it.
function thirdPartyLicenses(): Plugin {
  return {
    name: "erdify-studio:third-party-licenses",
    apply: "build",
    generateBundle(_, bundle) {
      const dirs = new Set<string>();
      for (const chunk of Object.values(bundle)) {
        if (chunk.type !== "chunk") continue;
        for (const id of Object.keys(chunk.modules)) {
          const dir = packageDir(id);
          if (dir) dirs.add(dir);
        }
      }
      const root = dirname(fileURLToPath(import.meta.url));
      for (const name of EXTRA_LICENSED) dirs.add(join(root, "node_modules", name));
      const sections = [...dirs]
        .map((dir) => {
          const meta = JSON.parse(readFileSync(join(dir, "package.json"), "utf8")) as {
            name: string;
            version: string;
            license?: string;
          };
          // A package without a licence file needs one in frontend/licenses/ (scope/name -> scope__name.txt).
          const own = readdirSync(dir).find((f) => /^(licen[cs]e|copying)/i.test(f));
          const override = join(root, "licenses", `${meta.name.replace("/", "__")}.txt`);
          const file = own ? join(dir, own) : existsSync(override) ? override : null;
          if (!file) this.error(`no licence file in ${meta.name}@${meta.version}; add ${override}`);
          const text = readFileSync(file, "utf8").trim();
          return { key: meta.name, text: `${meta.name}@${meta.version} (${meta.license ?? "see below"})\n\n${text}\n` };
        })
        .sort((a, b) => a.key.localeCompare(b.key));
      const unique = sections.filter((s, i) => i === 0 || s.key !== sections[i - 1].key);
      this.emitFile({
        type: "asset",
        fileName: "THIRD_PARTY_LICENSES.txt",
        source: `Third-party code bundled into the erdify-studio canvas.\n\n${unique.map((s) => s.text).join("\n" + "-".repeat(78) + "\n\n")}`,
      });
    },
  };
}

export default defineConfig({
  plugins: [
    offlineIcons(),
    thirdPartyLicenses(),
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
        // The server only accepts its own Origin; the dev page's is localhost:5173.
        // The token still guards the API.
        configure: (proxy) => {
          proxy.on("proxyReq", (request) => request.removeHeader("origin"));
        },
      },
    },
  },
});

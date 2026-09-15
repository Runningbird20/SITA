/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    coverage: {
      // Post-roadmap addition — resolves WHATNEXT.md's "Frontend test
      // rigor doesn't match the backend's" item. Deliberately NOT the
      // backend's 95% floor: that number reflects Phase 11's real,
      // earned coverage, not an arbitrary target, and copying it here
      // would either be dishonest (claim it without earning it) or force
      // a large test-writing effort disproportionate to what this pass
      // scoped. Most dashboard pages still have zero direct tests — the
      // real, stated remaining gap. These numbers track actual measured
      // coverage as of the last pass that touched this file (raised from
      // an initial 38/20/28/40 baseline once the rule-tuning UI's tests
      // landed) — enforced as a floor so it can only go up from here, not
      // back down, while staying honest about what's actually covered.
      // See DEF.md § Phase 11, "Post-roadmap addition: frontend coverage
      // floor".
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/**/*.test.{ts,tsx}", "src/test/**", "src/**/*.d.ts"],
      thresholds: {
        statements: 53,
        branches: 32,
        functions: 43,
        lines: 55,
      },
    },
  },
});

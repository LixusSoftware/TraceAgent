/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            "/api": "http://127.0.0.1:8000",
            "/health": "http://127.0.0.1:8000"
        }
    },
    test: {
        environment: "jsdom",
        setupFiles: "./src/test/setup.ts",
        globals: true,
        include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
        exclude: ["e2e/**"],
        coverage: {
            provider: "v8",
            reporter: ["text", "json", "html"],
            exclude: ["node_modules/", "src/test/", "**/*.d.ts"],
            thresholds: {
                lines: 50,
                functions: 50,
                branches: 40,
                statements: 50
            }
        }
    }
});

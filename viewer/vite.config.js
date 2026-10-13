import { defineConfig } from 'vite';
import { resolve } from 'node:path';

// Builds the two demo pages. Components need no build step of their own.
export default defineConfig({
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      input: {
        table: resolve(import.meta.dirname, 'app/index.html'),
        feeder: resolve(import.meta.dirname, 'app/feeder.html'),
      },
    },
  },
});

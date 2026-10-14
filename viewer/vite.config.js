import { defineConfig } from 'vite';
import { resolve } from 'node:path';
import logApi from './server/api.js';

// Two pages: the replay viewer and the standalone birdfeeder demo.
// Components need no build step of their own.
export default defineConfig({
  plugins: [logApi()],
  server: { host: true, port: 5273, open: false },
  preview: { host: true, port: 5274 },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      input: {
        index: resolve(import.meta.dirname, 'index.html'),
        feeder: resolve(import.meta.dirname, 'app/feeder.html'),
      },
    },
  },
});

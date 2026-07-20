import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Tailwind runs via the vite plugin above; pin an empty PostCSS config so
  // Vite doesn't discover unrelated postcss.config files in parent dirs.
  css: { postcss: { plugins: [] } },
  server: {
    proxy: {
      // Real backend (fr-viewer FastAPI) lives on :7878. Flip USE_MOCK off to use it.
      '/api': 'http://localhost:7878',
    },
  },
})

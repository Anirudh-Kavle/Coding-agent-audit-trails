import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Real backend (fr-viewer FastAPI) lives on :7878. Flip USE_MOCK off to use it.
      '/api': 'http://localhost:7878',
    },
  },
})

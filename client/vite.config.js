import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import basicSsl from '@vitejs/plugin-basic-ssl';

export default defineConfig({
  plugins: [react(), basicSsl()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    // Proxy all /ws/* requests to the FastAPI backend.
    // This lets the phone connect via ngrok HTTPS (wss://) without mixed-content errors.
    proxy: {
      '/ws': {
        target: 'http://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
        secure: false,
      },
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      '/livekit-ws': {
        target: 'ws://127.0.0.1:7880',
        ws: true,
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path.replace(/^\/livekit-ws/, ''),
      },
    },
  },
  base: './',
});
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    test: {
        environment: 'jsdom',
        globals: true,
        setupFiles: './src/setupTests.js',
    },
    server: {
        port: 5173,
        proxy: {
            // Forward all /api requests to the FastAPI backend so we avoid CORS
            // issues during development. In production, configure your web server
            // (nginx, Caddy, etc.) to do the same.
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
        },
    },
});

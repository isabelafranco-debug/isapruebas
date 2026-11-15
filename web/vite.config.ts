import { defineConfig } from 'vite';
import { regionalMapPackage } from './offline-build.mjs';
export default defineConfig({
  plugins:[regionalMapPackage],
  server:{ port:5173,strictPort:true,proxy:{'/api':'http://127.0.0.1:8080'} },
  build:{rollupOptions:{output:{manualChunks(id) {
    if (id.includes('plotly.js')) return 'plotly';

  }}}}
});

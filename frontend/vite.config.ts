import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    /*
     * PWA configuration (US-024, US-025).
     *
     * `injectManifest` rather than `generateSW` because the service worker also
     * has to handle Web Push and notification clicks (US-030), which a generated
     * worker cannot express.
     */
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
      },
      devOptions: {
        // The service worker runs in development too, so offline behaviour can
        // actually be tested rather than assumed.
        enabled: true,
        type: 'module',
      },
      manifest: {
        name: 'RentFlow Kenya',
        short_name: 'RentFlow',
        description: 'Manage every rental. Empower every owner.',
        theme_color: '#1d4ed8',
        background_color: '#f8fafc',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        categories: ['business', 'finance', 'productivity'],
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icons/icon-512-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
        shortcuts: [
          { name: 'Record a payment', url: '/payments/new' },
          { name: 'Meter reading', url: '/meter-readings/new' },
          { name: 'Report an issue', url: '/maintenance/new' },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        /*
         * Vendor code is split from application code so a deploy that changes a
         * screen does not invalidate the React, form and data-fetching code that
         * did not change. These four are all in the login page's own import
         * graph, so preloading them is right.
         *
         * Recharts is deliberately NOT named here. A manual chunk is treated as
         * part of the entry graph and gets a `modulepreload` on every page load,
         * which put 119KB of charting in front of the login form. Left alone,
         * Rollup gives it a shared async chunk across the three screens that
         * import it, fetched only when one of them opens.
         */
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (/[\\/]node_modules[\\/](react|react-dom|react-router|scheduler)[\\/]/.test(id)) {
            return 'react'
          }
          if (/react-hook-form|@hookform|zod/.test(id)) return 'forms'
          if (/@tanstack|axios/.test(id)) return 'data'
          return undefined
        },
      },
    },
    // The largest remaining chunk is the vendor bundle, which is expected.
    chunkSizeWarningLimit: 700,
  },
  server: {
    port: 5173,
  },
})

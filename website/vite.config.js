import { defineConfig } from 'vite';
import { resolve } from 'node:path';

// Dev-only stand-in for api/waitlist.js so the iPhone beta page can be exercised locally.
const devWaitlist = { ios: new Set(), cloud: new Set() };
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'mock-api',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url === '/api/github') {
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify({ 
              repo: 'vasu-devs/JustHireMe',
              stars: 483, 
              pullRequests: 19,
              openIssues: 10,
              forks: 92,
              url: 'https://github.com/vasu-devs/JustHireMe'
            }));
            return;
          }
          if (req.url.startsWith('/api/waitlist')) {
            const list = new URL(req.url, 'http://dev').searchParams.get('list') || 'cloud';
            res.setHeader('Content-Type', 'application/json');
            if (req.method === 'GET') {
              res.end(JSON.stringify({ count: (devWaitlist[list]?.size || 0) + 40, configured: true }));
              return;
            }
            let raw = '';
            req.on('data', (chunk) => { raw += chunk; });
            req.on('end', () => {
              const body = JSON.parse(raw || '{}');
              const store = devWaitlist[body.list || 'cloud'];
              const email = String(body.email || '').trim().toLowerCase();
              if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
                res.statusCode = 400;
                res.end(JSON.stringify({ error: 'Enter a valid email address, like you@example.com.' }));
                return;
              }
              const already = store.has(email);
              store.add(email);
              res.end(JSON.stringify({ joined: true, already, count: store.size + 40 }));
            });
            return;
          }
          if (req.url === '/api/views') {
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify({ total: 1250, configured: true }));
            return;
          }
          next();
        });
      }
    }
  ],
  build: {
    rollupOptions: {
      input: {
        main: resolve(import.meta.dirname, 'index.html'),
        ios: resolve(import.meta.dirname, 'ios/index.html'),
      },
    },
  },
  server: { 
    host: '127.0.0.1',
    port: 5175
  }
});

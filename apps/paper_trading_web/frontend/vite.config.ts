import { defineConfig, searchForWorkspaceRoot } from 'vite'

export default defineConfig({
  server: {
    fs: {
      // The catalog embeds the checked-in database diagram viewer from docs/reference.
      allow: [searchForWorkspaceRoot(process.cwd()), '../../../docs/reference'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { existsSync, statSync, createReadStream, cpSync } from 'fs'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

const COURSE_IMAGES_DIR = resolve(__dirname, '../docs/07-courses/advanced/expanded/images')

/** When developing /course-images/* Map to the docs directory and copy to after building dist */
function courseImagesPlugin() {
  return {
    name: 'course-images',
    configureServer(server: any) {
      const mimeMap: Record<string, string> = {
        png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
        gif: 'image/gif', webp: 'image/webp', svg: 'image/svg+xml'
      }
      server.middlewares.use('/course-images', (req: any, res: any, next: any) => {
        const filePath = resolve(COURSE_IMAGES_DIR, (req.url || '').replace(/^\//, ''))
        if (existsSync(filePath) && statSync(filePath).isFile()) {
          const ext = filePath.split('.').pop()?.toLowerCase() || ''
          res.setHeader('Content-Type', mimeMap[ext] || 'application/octet-stream')
          createReadStream(filePath).pipe(res)
        } else {
          next()
        }
      })
    },
    closeBundle() {
      const dest = resolve(__dirname, 'dist/course-images')
      if (existsSync(COURSE_IMAGES_DIR)) {
        cpSync(COURSE_IMAGES_DIR, dest, { recursive: true })
      }
    }
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    courseImagesPlugin(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
      imports: [
        'vue',
        'vue-router',
        'pinia',
        '@vueuse/core'
      ],
      dts: true,
      eslintrc: {
        enabled: true
      }
    }),
    // Automatic on-demand component import
    Components({
      resolvers: [ElementPlusResolver()],
      dts: true
    })
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@components': resolve(__dirname, 'src/components'),
      '@views': resolve(__dirname, 'src/views'),
      '@stores': resolve(__dirname, 'src/stores'),
      '@utils': resolve(__dirname, 'src/utils'),
      '@types': resolve(__dirname, 'src/types'),
      '@api': resolve(__dirname, 'src/api')
    }
  },
  server: {
    host: '0.0.0.0',
    port: parseInt(process.env.VITE_PORT || '3000', 10),
    hmr: {
      overlay: false
    },
    // Allow importing raw files from outside the project root (e.g. /docs)
    fs: {
      allow: [
        resolve(__dirname, '..'),  // Allow access to project root directory
        resolve(__dirname, '../docs')  // Explicitly allow access to the docs directory
      ]
    },
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        ws: true  // Enable WebSocket proxy support
      }
    }
  },
  esbuild: {
    drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
  },
  build: {
    target: 'es2020',
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined
          }

          if (id.includes('echarts') || id.includes('zrender') || id.includes('vue-echarts')) {
            return 'vendor-echarts'
          }

          if (id.includes('element-plus') || id.includes('@element-plus')) {
            return 'vendor-element-plus'
          }

          if (id.includes('pinia') || id.includes('vue-router') || id.includes('@vueuse')) {
            return 'vendor-vue-ecosystem'
          }

          if (id.includes('marked') || id.includes('mermaid') || id.includes('highlight.js') || id.includes('markdown-it')) {
            return 'vendor-markdown'
          }

          if (id.includes('vue')) {
            return 'vendor-vue'
          }

          return 'vendor-misc'
        },
        chunkFileNames: 'js/[name]-[hash].js',
        entryFileNames: 'js/[name]-[hash].js',
        assetFileNames: '[ext]/[name]-[hash].[ext]'
      }
    }
  },
  css: {
    preprocessorOptions: {
      scss: {
        api: 'modern-compiler',
        additionalData: `@use "@/styles/variables.scss" as *;`
      }
    }
  }
})

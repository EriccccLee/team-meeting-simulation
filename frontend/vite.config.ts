import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * SSE(Server-Sent Events) 전용 프록시 설정.
 * selfHandleResponse: true + pipe 로 버퍼링 없이 스트림을 그대로 전달한다.
 * 일반 proxy는 응답을 http-proxy 내부에서 수집 후 전달해 SSE가 지연될 수 있다.
 */
function sseProxy(target: string) {
  return {
    target,
    changeOrigin: true,
    selfHandleResponse: true,
    configure: (proxy: any) => {
      proxy.on('proxyRes', (proxyRes: any, _req: any, res: any) => {
        res.writeHead(proxyRes.statusCode, proxyRes.headers)
        proxyRes.pipe(res)
      })
    },
  }
}

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // SSE 스트림 경로: 버퍼링 없이 직접 파이핑
      '/api/stream':       sseProxy('http://localhost:8000'),
      '/api/slack/stream': sseProxy('http://localhost:8000'),
      // 나머지 API: 일반 프록시
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})

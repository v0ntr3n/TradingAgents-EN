#!/usr/bin/env node
/**
 * mock-jdyun-gateway.mjs — JD Cloud Gateway local simulator (including login page)
 *
 * Complete simulation of JD Cloud login link:
 *   1. User opens http://localhost:3100 → Not logged in, redirected to /login
 *   2. /login Display the login page (simulating JD Cloud platform login)
 *   3. User enters username and password → Gateway verification credentials
 *   4. Verification passed → Set session cookie and redirect to home page
 *   5. All subsequent requests will be automatically carried cookie → Gateway extracts credentials from cookie for injection Basic Auth
 *   6. Users do not need to log in twice and can use the system directly.
 *
 * Real JD Cloud link comparison:
 *   JD Cloud login page        → This gateway /login page
 *   JD Cloud Platform Certification       → This gateway verifies user name and password
 *   JD Cloud Gateway Injection Header → This gateway extracts credentials from cookies for injection Authorization: Basic
 *   our container          → Frontend 3003 / Backend 8002
 *
 * Start mode:
 *   $env:JDYUN_AUTH_USER = "testuser"
 *   $env:JDYUN_AUTH_PASS = "Test@123456"
 *   node frontend/mock-jdyun-gateway.mjs
 *   Browser opens http://localhost:3100
 *
 * environment variables:
 *   JDYUN_GATEWAY_PORT      Gateway listening port (default 3100)
 *   JDYUN_TARGET            Destination address (default http://127.0.0.1:8082) 
 *   JDYUN_AUTH_USER         Login username (default testuser)
 *   JDYUN_AUTH_PASS         Login password (required)
 */

import http from 'node:http'
import { URL } from 'node:url'

// ===== Configuration =====
// Single container image: front end+backend+Nginx Unified on port 8082
// The simulated gateway only needs to forward all requests to 8082, and Nginx automatically distinguishes front-end/back-end internally.
const GATEWAY_PORT = parseInt(process.env.JDYUN_GATEWAY_PORT || '3100', 10)
const TARGET = process.env.JDYUN_TARGET || 'http://127.0.0.1:8082'

// Login page credentials (simulated JD Cloud platform account, user input on the login page)
// Used for development and testing, written directly, no need to configure environment variables
const AUTH_USER = 'testuser'
const AUTH_PASS = 'Test@123456'

// Basic Auth credentials injected into the backend (corresponding to the backend JDYUN_BASIC_AUTH_USERS configuration)
// By default, jcloud-ugidvcp credentials in .env.docker.jdyun are used
const INJECT_AUTH = process.env.JDYUN_INJECT_AUTH || 'jcloud-ugidvcp:8437F13DABE87D0BC1D4DCCD4739C5A7'

// Cookie Credentials stored in (that is, the base64 value of Basic Auth injected into the backend)
const CREDENTIAL_B64 = Buffer.from(INJECT_AUTH, 'utf-8').toString('base64')
const SESSION_COOKIE_NAME = 'jdyun_session'

// Backend path prefix
const BACKEND_PREFIXES = ['/api', '/docs', '/openapi.json', '/redoc']

// Paths that can be accessed without logging in (static resources, etc.)
const PUBLIC_PATHS = ['/login', '/favicon.ico', '/logo.svg', '/manifest.json']
const PUBLIC_EXTENSIONS = ['.js', '.css', '.ico', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.woff', '.woff2', '.ttf', '.map']

function isBackendPath(pathname) {
  return BACKEND_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/'))
}

function isPublicPath(pathname) {
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + '/'))) return true
  const ext = pathname.substring(pathname.lastIndexOf('.'))
  return PUBLIC_EXTENSIONS.includes(ext)
}

function parseTarget(target) {
  const t = new URL(target)
  return { protocol: t.protocol, hostname: t.hostname, port: t.port || (t.protocol === 'https:' ? 443 : 80), host: t.host }
}

// ===== Cookie / Session =====
function parseCookies(cookieHeader) {
  const cookies = {}
  if (!cookieHeader) return cookies
  for (const part of cookieHeader.split(';')) {
    const [k, ...v] = part.trim().split('=')
    if (k) cookies[k] = v.join('=').trim()
  }
  return cookies
}

function isValidSession(cookieHeader) {
  const cookies = parseCookies(cookieHeader)
  return cookies[SESSION_COOKIE_NAME] === CREDENTIAL_B64
}

// ===== Login page HTML =====
function renderLoginPage(errorMsg) {
  const errorBlock = errorMsg
    ? `<div class="error">${errorMsg}</div>`
    : `<div class="hint">JD Cloud Cooperation Edition — Please enter your JD Cloud account password</div>`
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>JD Cloud - Login</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
      background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
      min-height: 100vh; display: flex; align-items: center; justify-content: center;
    }
    .login-card {
      background: #fff; border-radius: 12px; padding: 40px 36px; width: 380px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.15);
    }
    .logo {
      text-align: center; margin-bottom: 28px;
    }
    .logo-text {
      font-size: 24px; font-weight: 700; color: #1a73e8;
    }
    .logo-sub {
      font-size: 13px; color: #999; margin-top: 4px;
    }
    .form-group { margin-bottom: 20px; }
    .form-group label {
      display: block; font-size: 14px; color: #333; margin-bottom: 8px; font-weight: 500;
    }
    .form-group input {
      width: 100%; padding: 12px 14px; border: 1px solid #ddd; border-radius: 8px;
      font-size: 15px; transition: border-color 0.2s; outline: none;
    }
    .form-group input:focus { border-color: #1a73e8; }
    .btn-login {
      width: 100%; padding: 13px; background: #1a73e8; color: #fff; border: none;
      border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer;
      transition: background 0.2s; margin-top: 8px;
    }
    .btn-login:hover { background: #1557b0; }
    .btn-login:active { background: #0d47a1; }
    .error {
      background: #fff0f0; color: #e53935; padding: 10px 14px; border-radius: 8px;
      font-size: 14px; margin-bottom: 20px; border: 1px solid #ffcdd2;
    }
    .hint {
      color: #999; font-size: 13px; margin-bottom: 20px; text-align: center;
    }
    .footer {
      text-align: center; margin-top: 24px; font-size: 12px; color: #bbb;
    }
  </style>
</head>
<body>
  <div class="login-card">
    <div class="logo">
      <div class="logo-text">☁️ JD Cloud</div>
      <div class="logo-sub">TradingAgents-CN Cooperation version</div>
    </div>
    ${errorBlock}
    <form method="POST" action="/login">
      <div class="form-group">
        <label>Username</label>
        <input type="text" name="username" placeholder="Please enter username" autocomplete="username" required />
      </div>
      <div class="form-group">
        <label>Password</label>
        <input type="password" name="password" placeholder="Please enter password" autocomplete="current-password" required />
      </div>
      <button type="submit" class="btn-login">Login</button>
    </form>
    <div class="footer">© JD Cloud Cooperation Edition · local analog gateway</div>
  </div>
</body>
</html>`
}

// ===== Request body parsing =====
function readBody(req) {
  return new Promise((resolve) => {
    let data = ''
    req.on('data', (chunk) => { data += chunk })
    req.on('end', () => resolve(data))
  })
}

function parseUrlEncoded(body) {
  const params = {}
  for (const pair of body.split('&')) {
    const [k, ...v] = pair.split('=')
    if (k) params[decodeURIComponent(k)] = decodeURIComponent(v.join('='))
  }
  return params
}

// ===== HTTP forward =====
function forward(req, res, target, injectAuth) {
  const t = parseTarget(target)
  const headers = { ...req.headers, host: t.host }
  if (injectAuth) headers.authorization = `Basic ${CREDENTIAL_B64}`

  const proxyReq = http.request(
    { protocol: t.protocol, hostname: t.hostname, port: t.port, method: req.method, path: req.url, headers },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers)
      proxyRes.pipe(res)
    }
  )
  proxyReq.on('error', (err) => {
    console.error(`❌ Forwarding failed ${req.method} ${req.url} → ${err.message}`)
    if (!res.headersSent) res.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' })
    res.end(`Gateway forwarding failed: ${err.message}`)
  })
  req.pipe(proxyReq)
}

// ===== WebSocket forward =====
function forwardUpgrade(req, socket, head) {
  const pathname = (req.url || '/').split('?')[0]
  const isBackend = isBackendPath(pathname)
  const target = TARGET
  const t = parseTarget(target)
  // Copy the original header, overwrite host, and explicitly set the upgrade header (to avoid Node.js http client overwriting Connection)
  const headers = { ...req.headers, host: t.host }
  if (isBackend) headers.authorization = `Basic ${CREDENTIAL_B64}`
  headers.connection = 'Upgrade'
  headers.upgrade = 'websocket'

  console.log(`🔌 [WS] ${req.url} → ${target}`)

  const proxyReq = http.request({
    protocol: t.protocol, hostname: t.hostname, port: t.port,
    method: req.method || 'GET', path: req.url, headers,
  })

  // Backend returns 101 Switching Protocols → Forward upgrade response
  proxyReq.on('upgrade', (proxyRes, proxySocket, proxyHead) => {
    const rawHeaders = Object.entries(proxyRes.headers)
      .map(([k, v]) => (Array.isArray(v) ? v.map((x) => `${k}: ${x}`).join('\r\n') : `${k}: ${v}`))
      .join('\r\n')
    // NOTE: Required after header end \r\n\r\n (A blank line indicates the end of the header)
    socket.write('HTTP/1.1 101 Switching Protocols\r\n' + rawHeaders + '\r\n\r\n')
    if (proxyHead && proxyHead.length) socket.write(proxyHead)
    if (head && head.length) proxySocket.write(head)
    proxySocket.pipe(socket)
    socket.pipe(proxySocket)
    console.log(`✅ [WS] Upgrade successful: ${req.url}`)
  })

  // The backend returns a normal HTTP response (e.g. 403/401 Upgrade Denied)→ forward to client
  proxyReq.on('response', (proxyRes) => {
    const chunks = []
    proxyRes.on('data', (chunk) => chunks.push(chunk))
    proxyRes.on('end', () => {
      const body = Buffer.concat(chunks)
      const statusLine = `HTTP/1.1 ${proxyRes.statusCode} ${proxyRes.statusMessage || ''}\r\n`
      const rawHeaders = Object.entries(proxyRes.headers)
        .map(([k, v]) => (Array.isArray(v) ? v.map((x) => `${k}: ${x}`).join('\r\n') : `${k}: ${v}`))
        .join('\r\n')
      socket.write(statusLine + rawHeaders + '\r\n\r\n')
      if (body.length) socket.write(body)
      socket.end()
      console.log(`⚠️ [WS] Backend refuses to upgrade (HTTP ${proxyRes.statusCode}): ${req.url}`)
    })
  })

  proxyReq.on('error', (err) => {
    console.error(`❌ WS Forwarding failed ${req.url} → ${err.message}`)
    socket.destroy()
  })

  proxyReq.end()
}

// ===== HTTP Request processing =====
async function handleHttp(req, res) {
  const pathname = (req.url || '/').split('?')[0]

  // --- Login page ---
  if (pathname === '/login') {
    if (req.method === 'GET') {
      return res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }).end(renderLoginPage())
    }
    if (req.method === 'POST') {
      const body = await readBody(req)
      const { username, password } = parseUrlEncoded(body)
      if (username === AUTH_USER && password === AUTH_PASS) {
        console.log(`✅ Login successful: ${username}`)
        res.writeHead(302, {
          'Set-Cookie': `${SESSION_COOKIE_NAME}=${CREDENTIAL_B64}; HttpOnly; Path=/; Max-Age=86400; SameSite=Lax`,
          'Location': '/',
        })
        return res.end()
      }
      console.log(`❌ Login failed: ${username}`)
      return res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }).end(renderLoginPage('Wrong username or password'))
    }
  }

  // --- Log out ---
  if (pathname === '/logout') {
    res.writeHead(302, {
      'Set-Cookie': `${SESSION_COOKIE_NAME}=; HttpOnly; Path=/; Max-Age=0`,
      'Location': '/login',
    })
    return res.end()
  }

  // --- Check login status ---
  const loggedIn = isValidSession(req.headers.cookie)

  // API Request: Return without logging in 401
  if (isBackendPath(pathname)) {
    if (!loggedIn) {
      return res.writeHead(401, { 'Content-Type': 'application/json' }).end(JSON.stringify({ success: false, message: 'Not logged in' }))
    }
    console.log(`🔐 [API] ${req.method} ${pathname} -> backend`)
    return forward(req, res, TARGET, true)
  }

  // Public resources (static files, etc.): forwarded directly to the front end
  if (isPublicPath(pathname)) {
    return forward(req, res, TARGET, false)
  }

  // Page request: Not logged in redirect to login page
  if (!loggedIn) {
    res.writeHead(302, { 'Location': '/login' })
    return res.end()
  }

  // Logged in: forwarded to the front end
  console.log(`🌐 [Page] ${req.method} ${pathname} -> front end`)
  return forward(req, res, TARGET, false)
}

// ===== start =====
const server = http.createServer((req, res) => {
  handleHttp(req, res).catch((err) => {
    console.error('❌ Handling request exceptions:', err)
    if (!res.headersSent) res.writeHead(500).end('Internal Server Error')
  })
})
server.on('upgrade', forwardUpgrade)

server.listen(GATEWAY_PORT, '0.0.0.0', () => {
  console.log('==========================================================')
  console.log('  JD Cloud Gateway local simulator (including login page)')
  console.log('==========================================================')
  console.log(`  Gateway address:  http://localhost:${GATEWAY_PORT}`)
  console.log(`  Login page:    http://localhost:${GATEWAY_PORT}/login`)
  console.log(`  destination address:  ${TARGET}`)
  console.log(`  Login credentials:  ${AUTH_USER} / ${AUTH_PASS}`)
  console.log('==========================================================')
  console.log('  process: Open gateway address → Login page → Enter credentials → Jump system')
  console.log('==========================================================')
})

import type { Connect, Plugin } from 'vite'

function credentialProxy(token: string | undefined) {
  if (token && !/^[!-~]{32,256}$/.test(token))
    throw Error('Invalid server API credential configuration')
  return (proxy: import('vite').HttpProxy.ProxyServer) => {
    if (token)
      proxy.on('proxyReq', (request) =>
        request.setHeader('Authorization', `Bearer ${token}`),
      )
  }
}
const agentCredential = credentialProxy(process.env.BANKOPS_AGENT_API_TOKEN)
const browserBoundary: Connect.NextHandleFunction = (req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff')
  res.setHeader('X-Frame-Options', 'DENY')
  res.setHeader('Referrer-Policy', 'no-referrer')
  if (
    [
      '/api/',
      '/customer-api',
      '/governance-api',
      '/monitoring-api',
      '/investigation-api',
      '/reconciliation-api',
    ].some((prefix) => req.url?.startsWith(prefix))
  ) {
    res.setHeader('Cache-Control', 'no-store')
    let reject = req.headers['sec-fetch-site'] === 'cross-site'
    const origin = req.headers.origin
    if (origin) {
      try {
        const parsed = new URL(origin)
        reject ||=
          !['http:', 'https:'].includes(parsed.protocol) ||
          parsed.host !== req.headers.host ||
          !!parsed.username ||
          parsed.pathname !== '/' ||
          !!parsed.search ||
          !!parsed.hash
      } catch {
        reject = true
      }
    }
    if (reject) {
      res.statusCode = 403
      res.end('Request unavailable')
      return
    }
  }
  if (req.url?.startsWith('/api/v1')) {
    const path = req.url.split('?')[0]
    const allowed =
      (req.method === 'POST' &&
        ['/api/v1/accounts', '/api/v1/transfers'].includes(path)) ||
      (req.method === 'GET' &&
        /^\/api\/v1\/(operator\/me|accounts\/[0-9a-f-]+(?:\/transactions)?|transfers\/[0-9a-f-]+)$/i.test(
          path,
        ))
    if (!allowed) {
      res.statusCode = 404
      res.end('Banking route unavailable')
      return
    }
  }
  next()
}
const bankingProxy = {
  target: process.env.BANKOPS_BANKING_API_TARGET || 'http://127.0.0.1:8080',
}
const customerGuard: Connect.NextHandleFunction = (req, res, next) => {
  if (!req.url?.startsWith('/customer-api')) return next()
  const path = req.url.split('?')[0]
  const allowed =
    (req.method === 'POST' &&
      [
        '/customer-api/register',
        '/customer-api/login',
        '/customer-api/logout',
        '/customer-api/accounts',
        '/customer-api/transfers',
      ].includes(path)) ||
    (req.method === 'GET' &&
      /^\/customer-api\/(me|accounts(?:\/[0-9a-f-]+(?:\/transactions)?)?|transfers\/[0-9a-f-]+)$/i.test(
        path,
      ))
  if (!allowed) {
    res.statusCode = 404
    res.end('Customer route unavailable')
    return
  }
  next()
}
// Never inject an operator or agent credential into customer requests.
const customerProxy = {
  target: bankingProxy.target,
  rewrite: (path: string) =>
    path.replace(/^\/customer-api/, '/api/v1/customer'),
}

const monitoringTarget =
  process.env.BANKOPS_MONITORING_API_TARGET || 'http://127.0.0.1:8000'
const investigationTarget =
  process.env.BANKOPS_INVESTIGATION_API_TARGET || monitoringTarget
const governanceTarget =
  process.env.BANKOPS_GOVERNANCE_API_TARGET || investigationTarget
const reconciliationTarget =
  process.env.BANKOPS_RECONCILIATION_API_TARGET || monitoringTarget
const reconciliationGuard: Connect.NextHandleFunction = (req, res, next) => {
  if (!req.url?.startsWith('/reconciliation-api')) return next()
  if (
    req.method !== 'GET' ||
    req.url !== '/reconciliation-api/incidents/detect'
  ) {
    res.statusCode = 404
    res.end('Reconciliation route unavailable')
    return
  }
  next()
}
const reconciliationProxy = {
  configure: agentCredential,
  target: reconciliationTarget,
  rewrite: (path: string) => path.replace(/^\/reconciliation-api/, ''),
}
const governanceGuard: Connect.NextHandleFunction = (req, res, next) => {
  if (!req.url?.startsWith('/governance-api')) return next()
  const m =
    /^\/governance-api\/remediation\/proposals\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?:\/(approve|reject|execute|execution|verify|verification))?$/.exec(
      req.url,
    )
  const allowed =
    m &&
    ((req.method === 'GET' &&
      (!m[1] || ['execution', 'verification'].includes(m[1]))) ||
      (req.method === 'POST' &&
        ['approve', 'reject', 'execute', 'verify'].includes(m[1])))
  if (!allowed) {
    res.statusCode = 404
    res.end('Governance route unavailable')
    return
  }
  next()
}
const governanceProxy = {
  target: governanceTarget,
  rewrite: (path: string) => path.replace(/^\/governance-api/, ''),
}
const investigationGuard: Connect.NextHandleFunction = (req, res, next) => {
  if (!req.url?.startsWith('/investigation-api')) return next()
  const allowed =
    (req.method === 'GET' &&
      [
        '/investigation-api/incidents/detect',
        '/investigation-api/incidents/investigate',
      ].includes(req.url)) ||
    (req.method === 'POST' &&
      req.url === '/investigation-api/workflows/investigate')
  if (!allowed) {
    res.statusCode = 404
    res.end('Investigation route unavailable')
    return
  }
  next()
}
const investigationProxy = {
  configure: agentCredential,
  target: investigationTarget,
  rewrite: (path: string) => path.replace(/^\/investigation-api/, ''),
}
const guard: Connect.NextHandleFunction = (req, res, next) => {
  if (!req.url?.startsWith('/monitoring-api')) return next()
  if (
    req.method !== 'GET' ||
    !['/monitoring-api/health', '/monitoring-api/incidents/detect'].includes(
      req.url,
    )
  ) {
    res.statusCode = 404
    res.end('Monitoring route unavailable')
    return
  }
  next()
}
const monitoringBoundary: Plugin = {
  name: 'monitoring-read-only-boundary',
  configureServer(server) {
    server.middlewares.use(browserBoundary)
    server.middlewares.use(customerGuard)
    server.middlewares.use(reconciliationGuard)
    server.middlewares.use(guard)
    server.middlewares.use(governanceGuard)
    server.middlewares.use(investigationGuard)
  },
  configurePreviewServer(server) {
    server.middlewares.use(browserBoundary)
    server.middlewares.use(customerGuard)
    server.middlewares.use(reconciliationGuard)
    server.middlewares.use(guard)
    server.middlewares.use(governanceGuard)
    server.middlewares.use(investigationGuard)
  },
}
const monitoringProxy = {
  configure: agentCredential,
  target: monitoringTarget,
  rewrite: (path: string) => path.replace(/^\/monitoring-api/, ''),
}

export { monitoringBoundary }
export const proxy = {
  '^/customer-api/': customerProxy,
  '^/reconciliation-api/incidents/detect$': reconciliationProxy,
  '^/governance-api/remediation/proposals/': governanceProxy,
  '^/investigation-api/(incidents/(detect|investigate)|workflows/investigate)$':
    investigationProxy,
  '^/monitoring-api/(health|incidents/detect)$': monitoringProxy,
  '/api/v1': bankingProxy,
}

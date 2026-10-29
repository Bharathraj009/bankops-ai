import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import {
  ArrowUpRight,
  ChevronRight,
  Command,
  Info,
  Menu,
  Moon,
  Search,
  Sun,
} from 'lucide-react'
import { Sidebar } from './components/Sidebar'
import { Badge, Dialog, IconButton, PageSkeleton } from './components/ui'
import { pages } from './navigation'
import { readPreference, savePreference } from './preferences'
import Overview from './pages/Overview'
const WorkspacePage = lazy(() => import('./pages/WorkspacePage'))
const Banking = lazy(() => import('./pages/Banking'))
const Monitoring = lazy(() => import('./pages/Monitoring'))
const Incidents = lazy(() => import('./pages/Incidents'))
const Governance = lazy(() => import('./pages/Governance'))
const Reconciliation = lazy(() => import('./pages/Reconciliation'))
const CustomerBanking = lazy(() => import('./pages/CustomerBanking'))

export default function App() {
  const location = useLocation()
  const governanceActive = ['/approvals', '/remediation'].includes(
    location.pathname,
  )
  const [governanceMounted, setGovernanceMounted] = useState(governanceActive)
  if (governanceActive && !governanceMounted) setGovernanceMounted(true)
  if (location.pathname === '/customer' && governanceMounted)
    setGovernanceMounted(false)
  const incidentActive = ['/incidents', '/investigation'].includes(
    location.pathname,
  )
  const [incidentMounted, setIncidentMounted] = useState(incidentActive)
  if (incidentActive && !incidentMounted) setIncidentMounted(true)
  const [bankingMounted, setBankingMounted] = useState(
    location.pathname === '/banking',
  )
  if (location.pathname === '/banking' && !bankingMounted)
    setBankingMounted(true)
  const page = pages.find((item) => item.path === location.pathname)
  const reduced = useReducedMotion()
  const [collapsed, setCollapsed] = useState(
    () => readPreference('bankops-sidebar', 'expanded') === 'collapsed',
  )
  const [theme, setTheme] = useState(() => {
    const stored = readPreference('bankops-theme', 'system')
    return stored === 'dark' || stored === 'light'
      ? stored
      : window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
  })
  const [mobileOpen, setMobileOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [guideOpen, setGuideOpen] = useState(false)
  const [query, setQuery] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const previousPath = useRef(location.pathname)
  const filtered = pages.filter((item) =>
    `${item.label} ${item.scope}`
      .toLowerCase()
      .includes(query.toLowerCase().trim()),
  )
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    savePreference('bankops-theme', theme)
  }, [theme])
  useEffect(() => {
    savePreference('bankops-sidebar', collapsed ? 'collapsed' : 'expanded')
  }, [collapsed])
  useEffect(() => {
    document.title = `${page?.label ?? 'Page not found'} · BankOps AI`
    if (previousPath.current !== location.pathname) {
      heading.current?.focus()
      previousPath.current = location.pathname
    }
  }, [location.pathname, page?.label])
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSearchOpen((value) => !value)
      }
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [])
  useEffect(() => {
    const media = window.matchMedia('(min-width: 901px)')
    const close = () => {
      if (media.matches) setMobileOpen(false)
    }
    media.addEventListener('change', close)
    return () => media.removeEventListener('change', close)
  }, [])
  return (
    <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="desktop-sidebar">
        <Sidebar
          collapsed={collapsed}
          toggle={() => setCollapsed((value) => !value)}
        />
      </aside>
      <div className="workspace-body">
        <header className="topbar">
          <div className="topbar-left">
            <IconButton
              label="Open navigation"
              className="mobile-menu"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={20} />
            </IconButton>
            <span className="topbar-workspace">Operations workspace</span>
            <ChevronRight size={13} className="breadcrumb-chevron" />
            <span className="topbar-current">
              {page?.label ?? 'Page not found'}
            </span>
          </div>
          <div className="topbar-actions">
            <button
              className="search-trigger"
              onClick={() => {
                setQuery('')
                setSearchOpen(true)
              }}
              aria-label="Search workspace pages"
            >
              <Search size={16} />
              <span>Find a workspace</span>
              <kbd>
                <Command size={11} /> K
              </kbd>
            </button>
            <div className="topbar-divider" />
            <IconButton
              label={
                theme === 'light'
                  ? 'Switch to dark theme'
                  : 'Switch to light theme'
              }
              onClick={() =>
                setTheme((value) => (value === 'light' ? 'dark' : 'light'))
              }
            >
              {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
            </IconButton>
            <IconButton
              label="About this workspace"
              onClick={() => setGuideOpen(true)}
            >
              <Info size={18} />
            </IconButton>
            <span className="preview-label">
              <span /> Interface preview
            </span>
          </div>
        </header>
        <main
          tabIndex={-1}
          id="main-content"
          className="main-content"
          aria-labelledby="page-title"
        >
          <div className="page-heading">
            <div>
              <span className="eyebrow">
                {page?.eyebrow ?? 'WORKSPACE NAVIGATION'}
              </span>
              <h1 id="page-title" tabIndex={-1} ref={heading}>
                {page?.label === 'Overview'
                  ? 'Operations overview'
                  : (page?.label ?? 'Page not found')}
              </h1>
              <p>
                {page?.description ?? 'A clear route back to your operations.'}
              </p>
            </div>
            <Badge>
              <span className="badge-dot" /> Local environment
            </Badge>
          </div>
          <div hidden={location.pathname !== '/banking'}>
            {bankingMounted && (
              <Suspense fallback={<PageSkeleton />}>
                <Banking active={location.pathname === '/banking'} />
              </Suspense>
            )}
          </div>
          <div hidden={!incidentActive}>
            {incidentMounted && (
              <Suspense fallback={<PageSkeleton />}>
                <Incidents
                  active={incidentActive}
                  investigation={location.pathname === '/investigation'}
                />
              </Suspense>
            )}
          </div>
          <div hidden={!governanceActive}>
            {governanceMounted && (
              <Suspense fallback={<PageSkeleton />}>
                <Governance
                  active={governanceActive}
                  remediation={location.pathname === '/remediation'}
                />
              </Suspense>
            )}
          </div>
          {location.pathname !== '/banking' &&
            !incidentActive &&
            !governanceActive && (
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={location.pathname}
                  initial={{ opacity: 0, y: reduced ? 0 : 7 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: reduced ? 0 : 0.16 }}
                >
                  <Suspense fallback={<PageSkeleton />}>
                    {location.pathname === '/' ? (
                      <Overview openGuide={() => setGuideOpen(true)} />
                    ) : location.pathname === '/monitoring' ? (
                      <Monitoring />
                    ) : location.pathname === '/reconciliation' ? (
                      <Reconciliation />
                    ) : location.pathname === '/customer' ? (
                      <CustomerBanking />
                    ) : (
                      <WorkspacePage path={location.pathname} />
                    )}
                  </Suspense>
                </motion.div>
              </AnimatePresence>
            )}
        </main>
        <footer className="workspace-footer">
          <span>
            <strong>BankOps AI</strong>{' '}
            <span className="footer-separator">/</span> Built for considered
            operations
          </span>
          <span className="footer-status">
            <span /> Banking & monitoring connect on demand
          </span>
        </footer>
      </div>
      <Dialog
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        title="Workspace navigation"
        className="mobile-drawer"
      >
        <Sidebar
          collapsed={false}
          mobile
          onNavigate={() => setMobileOpen(false)}
        />
      </Dialog>
      <Dialog
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        title="Find your workspace"
        className="search-dialog"
      >
        <div className="search-field">
          <Search size={19} />
          <input
            data-autofocus
            aria-label="Search pages"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Banking, incidents, approvals…"
          />
          <kbd>ESC</kbd>
        </div>
        <div className="search-results" aria-label="Matching pages">
          {filtered.length ? (
            filtered.map((item) => (
              <Link
                to={item.path}
                key={item.path}
                onClick={() => setSearchOpen(false)}
              >
                <span className={`icon-tile accent-${item.accent}`}>
                  <item.icon size={18} />
                </span>
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.scope}</small>
                </span>
                <ArrowUpRight size={15} />
              </Link>
            ))
          ) : (
            <p className="no-results">
              No pages match “{query}”. Try another workspace name.
            </p>
          )}
        </div>
        <div className="search-help">
          Use Tab to move between pages. Enter to open.
        </div>
      </Dialog>
      <Dialog
        open={guideOpen}
        onClose={() => setGuideOpen(false)}
        title="A workspace with clear boundaries"
        className="guide-dialog"
      >
        <Badge tone="blue">Frontend foundation</Badge>
        <p className="guide-lead">
          BankOps AI brings banking operations and reliability into one
          considered workspace.
        </p>
        <p>
          Banking connects to the configured API for account creation, account
          lookup, transfers, and ledger-backed history. Monitoring reads
          sanitized evidence from the reliability agent. Incidents and AI
          Investigation support evidence collection and explicitly confirmed
          RCA. Approvals and Remediation use backend-authorized records and
          confirmed actions. Reconciliation reads sanitized Airflow run and task
          evidence. No operational data is fabricated.
        </p>
        <div className="guide-detail">
          <span>Navigation</span>
          <strong>Nine focused workspaces</strong>
        </div>
        <div className="guide-detail">
          <span>Quick navigation</span>
          <kbd>Ctrl / ⌘ + K</kbd>
        </div>
        <div className="guide-detail">
          <span>Accessibility</span>
          <strong>Keyboard navigation & reduced motion</strong>
        </div>
        <button
          className="button button-primary guide-done"
          onClick={() => setGuideOpen(false)}
        >
          Continue exploring <ChevronRight size={16} />
        </button>
      </Dialog>
    </div>
  )
}

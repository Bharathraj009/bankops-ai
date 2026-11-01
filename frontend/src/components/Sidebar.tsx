import { motion, useReducedMotion } from 'motion/react'
import { NavLink, Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Laptop, ShieldCheck } from 'lucide-react'
import { pages } from '../navigation'
import { Brand, IconButton } from './ui'

export function Sidebar({
  collapsed,
  toggle,
  mobile = false,
  onNavigate,
}: {
  collapsed: boolean
  toggle?: () => void
  mobile?: boolean
  onNavigate?: () => void
}) {
  const reduced = useReducedMotion()
  return (
    <div className={`sidebar-content ${collapsed ? 'is-collapsed' : ''}`}>
      <Link
        to="/"
        aria-label="Reconlith home"
        className="brand-link"
        onClick={onNavigate}
      >
        <Brand compact={collapsed} />
      </Link>
      {!collapsed && (
        <div className="sidebar-caption">OPERATIONS WORKSPACE</div>
      )}
      <nav aria-label={mobile ? 'Mobile navigation' : 'Main navigation'}>
        {['Workspace', 'Reliability', 'Governance'].map((group) => (
          <div className="nav-group" key={group}>
            <div className="nav-group-title">
              {collapsed ? (
                <span aria-hidden="true" className="group-divider" />
              ) : (
                group
              )}
            </div>
            {pages
              .filter((page) => page.group === group)
              .map((page) => (
                <NavLink
                  end={page.path === '/'}
                  to={page.path}
                  key={page.path}
                  onClick={onNavigate}
                  title={collapsed ? page.label : undefined}
                  className={({ isActive }) =>
                    `nav-item ${isActive ? 'is-active' : ''}`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <motion.span
                          layoutId={mobile ? 'mobile-nav-active' : 'nav-active'}
                          className="nav-active-surface"
                          transition={{ duration: reduced ? 0 : 0.2 }}
                          aria-hidden="true"
                        />
                      )}
                      <page.icon size={19} strokeWidth={1.65} />
                      <span className={collapsed ? 'sr-only' : ''}>
                        {page.label}
                      </span>
                      {!collapsed && isActive && (
                        <span className="nav-indicator" aria-hidden="true" />
                      )}
                    </>
                  )}
                </NavLink>
              ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-bottom">
        {!collapsed && (
          <div className="oversight-note">
            <ShieldCheck size={17} />
            <span>
              Human oversight.
              <br />
              <strong>By design.</strong>
            </span>
          </div>
        )}
        <div className="local-workspace">
          <span className="local-icon">
            <Laptop size={18} />
          </span>
          {!collapsed && (
            <div>
              <strong>Local workspace</strong>
              <span>Interface preview</span>
            </div>
          )}
          {!mobile && toggle && (
            <IconButton
              className="collapse-button"
              label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              aria-expanded={!collapsed}
              onClick={toggle}
            >
              {collapsed ? (
                <ChevronRight size={15} />
              ) : (
                <ChevronLeft size={15} />
              )}
            </IconButton>
          )}
        </div>
      </div>
    </div>
  )
}

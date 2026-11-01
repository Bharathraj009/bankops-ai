import { Link } from 'react-router-dom'
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  CircleDot,
  Layers3,
  LockKeyhole,
  Radio,
  ShieldCheck,
} from 'lucide-react'
import { pages, principles } from '../navigation'
import { Badge } from '../components/ui'

export default function Overview({ openGuide }: { openGuide: () => void }) {
  return (
    <>
      <section className="hero-panel" aria-labelledby="hero-heading">
        <div className="hero-copy">
          <div className="hero-eyebrow">
            <span /> A MORE CONSIDERED WORKSPACE
          </div>
          <h2 id="hero-heading">
            Every operation.
            <br />
            <span>A clearer perspective.</span>
          </h2>
          <p>
            Banking, reliability, and human oversight.
            <br className="desktop-break" /> Brought together with purpose.
          </p>
          <div className="hero-actions">
            <Link className="button button-white" to="/banking">
              Explore banking <ArrowRight size={16} />
            </Link>
            <button className="hero-text-button" onClick={openGuide}>
              About this workspace <ArrowUpRight size={15} />
            </button>
          </div>
        </div>
        <div
          className="architecture-art"
          aria-label="Conceptual architecture: banking, intelligence and oversight. Not live data."
          role="img"
        >
          <div className="orbital orbital-one" />
          <div className="orbital orbital-two" />
          <div className="orbital orbital-three" />
          <div className="architecture-line line-one" />
          <div className="architecture-line line-two" />
          <div className="architecture-center">
            <Layers3 size={29} strokeWidth={1.3} />
            <span>Reconlith</span>
          </div>
          <div className="architecture-node node-banking">
            <CircleDot size={15} />
            <span>Banking</span>
          </div>
          <div className="architecture-node node-observe">
            <Radio size={15} />
            <span>Intelligence</span>
          </div>
          <div className="architecture-node node-oversight">
            <ShieldCheck size={15} />
            <span>Oversight</span>
          </div>
          <span className="architecture-caption">
            ONE WORKSPACE. CONNECTED THINKING.
          </span>
        </div>
      </section>
      <section className="pillar-grid" aria-label="Core workspace areas">
        {[pages[1], pages[4], pages[5]].map((page, index) => (
          <Link key={page.path} to={page.path} className="pillar-card group">
            <span className={`icon-tile accent-${page.accent}`}>
              <page.icon size={21} strokeWidth={1.6} />
            </span>
            <div>
              <span className="card-overline">
                {['OPERATE', 'UNDERSTAND', 'GOVERN'][index]}
              </span>
              <h3>{page.label}</h3>
              <p>
                {
                  [
                    'Accounts & transfers',
                    'Evidence-led investigation',
                    'Explicit human review',
                  ][index]
                }
              </p>
            </div>
            <ArrowUpRight size={17} className="card-arrow" />
          </Link>
        ))}
      </section>
      <div className="overview-lower">
        <section aria-labelledby="modules-heading">
          <div className="section-heading">
            <div>
              <h2 id="modules-heading">Your operations toolkit</h2>
              <p>A focused space for every part of the process.</p>
            </div>
            <span className="small-label">WORKSPACE DIRECTORY</span>
          </div>
          <div className="module-grid">
            {pages
              .filter((page) =>
                [
                  '/monitoring',
                  '/incidents',
                  '/remediation',
                  '/reconciliation',
                ].includes(page.path),
              )
              .map((page) => (
                <Link
                  className="module-card group"
                  key={page.path}
                  to={page.path}
                >
                  <div className="module-card-top">
                    <span className={`icon-tile accent-${page.accent}`}>
                      <page.icon size={20} strokeWidth={1.6} />
                    </span>
                    <ArrowUpRight className="card-arrow" size={17} />
                  </div>
                  <h3>{page.label}</h3>
                  <p>{page.scope}</p>
                  <div className="module-card-bottom">
                    <Badge>
                      {page.path === '/monitoring' ||
                      page.path === '/incidents' ||
                      page.path === '/remediation' ||
                      page.path === '/reconciliation'
                        ? 'Connects on demand'
                        : 'Not connected'}
                    </Badge>
                    <span>
                      Open workspace <ArrowRight size={13} />
                    </span>
                  </div>
                </Link>
              ))}
          </div>
        </section>
        <aside
          className="principles-panel"
          aria-labelledby="principles-heading"
        >
          <span className="card-overline">THE RECONLITH APPROACH</span>
          <h2 id="principles-heading">
            Confidence starts
            <br /> with context.
          </h2>
          <p className="principles-intro">
            A thoughtful path from signal to decision.
          </p>
          <ol>
            {principles.map((step, index) => (
              <li key={step.title}>
                <div className="principle-step">
                  <span className="step-icon">
                    <step.icon size={17} />
                  </span>
                  {index < 2 && (
                    <ArrowDown size={12} className="step-connector" />
                  )}
                </div>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="principles-footer">
            <LockKeyhole size={15} />
            <span>Evidence first. People in control.</span>
          </div>
        </aside>
      </div>
      <div className="connection-notice">
        <span className="notice-icon">
          <Radio size={16} />
        </span>
        <p>
          <strong>Banking, connected on demand.</strong> Open Banking to load
          real accounts and ledger-backed activity. Monitoring displays
          read-only service evidence. Incidents and AI Investigation collect
          evidence with optional backend-configured RCA. Approvals and
          Remediation use authenticated backend records and confirmed actions.
        </p>
      </div>
    </>
  )
}

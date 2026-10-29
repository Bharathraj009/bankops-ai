import { ArrowLeft, ArrowRight, Cable, LockKeyhole } from 'lucide-react'
import { Link } from 'react-router-dom'
import { pages } from '../navigation'
import { Badge } from '../components/ui'

export default function WorkspacePage({ path }: { path: string }) {
  const page = pages.find((item) => item.path === path)
  if (!page)
    return (
      <section className="empty-panel">
        <div className="empty-icon">
          <Cable size={30} />
        </div>
        <span className="card-overline">A DIFFERENT DIRECTION</span>
        <h2>This page is outside the workspace.</h2>
        <p>Return to the overview to find your way.</p>
        <Link className="button button-primary" to="/">
          <ArrowLeft size={16} /> Back to overview
        </Link>
      </section>
    )
  return (
    <>
      <section className="empty-panel" aria-labelledby="empty-heading">
        <div className="empty-illustration" aria-hidden="true">
          <span className="empty-orbit" />
          <span className="empty-dash dash-one" />
          <span className="empty-dash dash-two" />
          <div className={`empty-icon accent-${page.accent}`}>
            <page.icon size={34} strokeWidth={1.3} />
          </div>
          <span className="empty-mini-icon">
            <Cable size={17} />
          </span>
        </div>
        <Badge tone="blue">Workspace foundation</Badge>
        <h2 id="empty-heading">
          A dedicated view for {page.label.toLowerCase()}.
        </h2>
        <p>
          {page.scope} will live here.
          <br />
          This workspace is ready for its next integration.
        </p>
        <div className="empty-connection">
          <span className="connection-ring" /> No service connected
        </div>
        <Link className="button button-primary" to="/">
          Return to overview <ArrowRight size={16} />
        </Link>
      </section>
      <section className="empty-footnote">
        <LockKeyhole size={17} />
        <div>
          <h3>Clear boundaries. Considered connections.</h3>
          <p>
            No{' '}
            {page.path === '/banking'
              ? 'accounts, transactions, or balances'
              : 'live records or operational results'}{' '}
            are loaded or created by this interface. Integrations will be added
            explicitly.
          </p>
        </div>
      </section>
    </>
  )
}

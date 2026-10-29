import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { MotionConfig } from 'motion/react'
import App from '../App'
import { PageSkeleton } from '../components/ui'
import { pages } from '../navigation'

function mount(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MotionConfig reducedMotion="always">
        <App />
      </MotionConfig>
    </MemoryRouter>,
  )
}

describe('BankOps workspace', () => {
  it('provides all eight accessible routes without inventing live information', () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    mount()
    const navigation = screen.getByRole('navigation', {
      name: 'Main navigation',
    })
    pages.forEach((page) =>
      expect(
        within(navigation).getByRole('link', { name: page.label }),
      ).toHaveAttribute('href', page.path),
    )
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Operations overview',
    )
    expect(
      screen.getByText('Banking & monitoring connect on demand'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/\$\d/)).not.toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('navigates, marks the current page, updates the title and moves focus', async () => {
    mount()
    const user = userEvent.setup()
    const link = within(
      screen.getByRole('navigation', { name: 'Main navigation' }),
    ).getByRole('link', { name: 'Banking' })
    await user.click(link)
    expect(
      await screen.findByText('Your banking workspace starts here'),
    ).toBeInTheDocument()
    expect(link).toHaveAttribute('aria-current', 'page')
    expect(
      screen.getByRole('heading', { level: 1, name: 'Banking' }),
    ).toHaveFocus()
    expect(document.title).toBe('Banking · BankOps AI')
  })
  it('loads the reconciliation deep link without fabricating evidence', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ airflow: null }))),
    )
    mount('/reconciliation')
    expect(
      await screen.findByText(
        'Airflow evidence is not configured. No reconciliation result is available.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Reconciliation',
    )
    expect(
      screen.getByRole('button', { name: 'Refresh evidence' }),
    ).toBeEnabled()
  })
  it('persists light/dark theme selection', async () => {
    mount()
    await userEvent.click(
      screen.getByRole('button', { name: 'Switch to dark theme' }),
    )
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('bankops-theme')).toBe('dark')
    await userEvent.click(
      screen.getByRole('button', { name: 'Switch to light theme' }),
    )
    expect(document.documentElement.dataset.theme).toBe('light')
  })
  it('restores the saved theme and collapsed navigation', () => {
    localStorage.setItem('bankops-theme', 'dark')
    localStorage.setItem('bankops-sidebar', 'collapsed')
    mount()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(
      screen.getByRole('button', { name: 'Expand sidebar' }),
    ).toHaveAttribute('aria-expanded', 'false')
    expect(
      within(
        screen.getByRole('navigation', { name: 'Main navigation' }),
      ).getByRole('link', { name: 'AI Investigation' }),
    ).toBeInTheDocument()
  })
  it('collapses and expands the sidebar without losing navigation names', async () => {
    mount()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
    expect(localStorage.getItem('bankops-sidebar')).toBe('collapsed')
    expect(
      screen.getByRole('button', { name: 'Expand sidebar' }),
    ).toHaveAttribute('aria-expanded', 'false')
    await user.click(screen.getByRole('button', { name: 'Expand sidebar' }))
    expect(localStorage.getItem('bankops-sidebar')).toBe('expanded')
  })
  it('opens search with the keyboard, filters pages and navigates', async () => {
    mount()
    const user = userEvent.setup()
    await user.keyboard('{Control>}k{/Control}')
    const dialog = screen.getByRole('dialog', { name: 'Find your workspace' })
    await user.type(
      within(dialog).getByRole('textbox', { name: 'Search pages' }),
      'recon',
    )
    expect(within(dialog).getAllByRole('link')).toHaveLength(1)
    await user.click(
      within(dialog).getByRole('link', { name: /Reconciliation/ }),
    )
    expect(
      screen.queryByRole('dialog', { name: 'Find your workspace' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Reconciliation',
    )
  })
  it('shows a useful search empty state and handles dialog cancellation', async () => {
    mount()
    await userEvent.click(
      screen.getByRole('button', { name: 'Search workspace pages' }),
    )
    const dialog = screen.getByRole('dialog', { name: 'Find your workspace' })
    await userEvent.type(
      within(dialog).getByRole('textbox'),
      'unmatchedworkspace',
    )
    expect(within(dialog).getByText(/No pages match/)).toBeInTheDocument()
    fireEvent(dialog, new Event('cancel', { bubbles: true, cancelable: true }))
    expect(
      screen.queryByRole('dialog', { name: 'Find your workspace' }),
    ).not.toBeInTheDocument()
  })
  it('opens the mobile drawer and closes it after navigation', async () => {
    mount()
    await userEvent.click(
      screen.getByRole('button', { name: 'Open navigation' }),
    )
    const dialog = screen.getByRole('dialog', { name: 'Workspace navigation' })
    await userEvent.click(
      within(dialog).getByRole('link', { name: 'Incidents' }),
    )
    expect(
      screen.queryByRole('dialog', { name: 'Workspace navigation' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Incidents',
    )
  })
  it('provides functional workspace guidance', async () => {
    mount()
    await userEvent.click(
      screen.getAllByRole('button', { name: 'About this workspace' })[0],
    )
    const dialog = screen.getByRole('dialog', {
      name: 'A workspace with clear boundaries',
    })
    expect(
      within(dialog).getByText(/Banking connects to the configured API/),
    ).toBeInTheDocument()
    await userEvent.click(
      within(dialog).getByRole('button', { name: /Continue exploring/ }),
    )
    expect(
      screen.queryByRole('dialog', {
        name: 'A workspace with clear boundaries',
      }),
    ).not.toBeInTheDocument()
  })
  it('works when browser preference storage is denied', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Restricted')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('Restricted')
    })
    mount()
    await userEvent.click(
      screen.getByRole('button', { name: 'Switch to dark theme' }),
    )
    expect(document.documentElement.dataset.theme).toBe('dark')
  })
  it('handles unknown routes and provides an accessible loading fallback', async () => {
    mount('/unknown')
    expect(
      await screen.findByRole('link', { name: /Back to overview/ }),
    ).toHaveAttribute('href', '/')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Page not found',
    )
  })
  it('labels the loading skeleton without introducing fake records', () => {
    render(<PageSkeleton />)
    expect(
      screen.getByRole('status', { name: 'Loading workspace' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})

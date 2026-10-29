import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

export function IconButton({
  label,
  children,
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`icon-button inline-flex shrink-0 items-center justify-center ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'blue' | 'success' | 'danger' | 'warning'
}) {
  return (
    <span
      className={`badge inline-flex items-center gap-1.5 whitespace-nowrap badge-${tone}`}
    >
      {children}
    </span>
  )
}
export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="brand">
      <span className="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" fill="none">
          <path
            d="M7 8h10a5 5 0 0 1 0 10H7V8Zm0 10h13a5 5 0 0 1 0 10H7V18Z"
            transform="translate(0 -2)"
            stroke="currentColor"
            strokeWidth="2.3"
          />
          <path d="m10 4 14 22" stroke="currentColor" strokeWidth="2.3" />
        </svg>
      </span>
      {!compact && (
        <span className="brand-type">
          BankOps <span>AI</span>
        </span>
      )}
    </span>
  )
}
export function Dialog({
  open,
  onClose,
  title,
  children,
  className = '',
  dismissible = true,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  className?: string
  dismissible?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (open && dialog && !dialog.open) {
      dialog.showModal()
      dialog.querySelector<HTMLElement>('[data-autofocus]')?.focus()
    }
    if (!open && dialog?.open) dialog.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      aria-label={title}
      className={`dialog ${className}`}
      onCancel={(event) => {
        event.preventDefault()
        if (dismissible) onClose()
      }}
      onClose={onClose}
      onClick={(event) => {
        if (dismissible && event.target === event.currentTarget) onClose()
      }}
    >
      <div className="dialog-heading">
        <h2>{title}</h2>
        <IconButton
          disabled={!dismissible}
          label={`Close ${title.toLowerCase()}`}
          onClick={onClose}
        >
          <X size={18} />
        </IconButton>
      </div>
      {children}
    </dialog>
  )
}
export function PageSkeleton() {
  return (
    <div
      className="skeleton-layout grid gap-5"
      role="status"
      aria-label="Loading workspace"
    >
      <span className="sr-only">Loading workspace…</span>
      <div className="skeleton skeleton-hero" />
      <div className="skeleton-row">
        {[1, 2, 3].map((item) => (
          <div className="skeleton skeleton-card" key={item} />
        ))}
      </div>
    </div>
  )
}

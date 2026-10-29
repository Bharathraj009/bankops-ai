import {
  Activity,
  ArrowLeftRight,
  Bot,
  CircleAlert,
  ClipboardCheck,
  LayoutDashboard,
  Scale,
  ShieldCheck,
  Workflow,
} from 'lucide-react'

export const pages = [
  {
    path: '/',
    label: 'Overview',
    group: 'Workspace',
    icon: LayoutDashboard,
    eyebrow: 'YOUR WORKSPACE',
    description: 'A clear starting point for your banking operations.',
    scope: 'One connected view of your operations',
    accent: 'blue',
  },
  {
    path: '/banking',
    label: 'Banking',
    group: 'Workspace',
    icon: ArrowLeftRight,
    eyebrow: 'BANKING OPERATIONS',
    description:
      'Account and transfer visibility, with integrity at the center.',
    scope: 'Accounts, transfers & transaction history',
    accent: 'blue',
  },
  {
    path: '/customer',
    label: 'Customer Banking',
    group: 'Workspace',
    icon: ArrowLeftRight,
    eyebrow: 'CUSTOMER ACCESS',
    description:
      'Your accounts, private transaction history and securely authorized transfers.',
    scope: 'Customer identity & owned accounts',
    accent: 'blue',
  },
  {
    path: '/monitoring',
    label: 'Monitoring',
    group: 'Reliability',
    icon: Activity,
    eyebrow: 'SERVICE OBSERVABILITY',
    description:
      'Understand service health through measured, verifiable signals.',
    scope: 'Service health & performance signals',
    accent: 'teal',
  },
  {
    path: '/incidents',
    label: 'Incidents',
    group: 'Reliability',
    icon: CircleAlert,
    eyebrow: 'INCIDENT OPERATIONS',
    description:
      'Bring operational exceptions into focus, without losing context.',
    scope: 'Evidence-led incident triage',
    accent: 'amber',
  },
  {
    path: '/investigation',
    label: 'AI Investigation',
    group: 'Reliability',
    icon: Bot,
    eyebrow: 'ASSISTED INVESTIGATION',
    description:
      'Connect observations. Examine hypotheses. Keep uncertainty visible.',
    scope: 'Sanitized evidence & grounded hypotheses',
    accent: 'violet',
  },
  {
    path: '/approvals',
    label: 'Approvals',
    group: 'Governance',
    icon: ClipboardCheck,
    eyebrow: 'HUMAN OVERSIGHT',
    description: 'Make considered decisions with an explicit human review.',
    scope: 'Proposal review & decision history',
    accent: 'blue',
  },
  {
    path: '/remediation',
    label: 'Remediation',
    group: 'Governance',
    icon: Workflow,
    eyebrow: 'CONTROLLED RESPONSE',
    description:
      'A deliberate path from reviewed proposals to verified outcomes.',
    scope: 'Approved actions & outcome verification',
    accent: 'teal',
  },
  {
    path: '/reconciliation',
    label: 'Reconciliation',
    group: 'Governance',
    icon: Scale,
    eyebrow: 'FINANCIAL INTEGRITY',
    description: 'A dedicated view for ledger and balance integrity checks.',
    scope: 'Ledger consistency & reconciliation outcomes',
    accent: 'violet',
  },
] as const
export const principles = [
  {
    title: 'Observe',
    description: 'Start with measured signals and source evidence.',
    icon: Activity,
  },
  {
    title: 'Investigate',
    description: 'Keep observed facts separate from hypotheses.',
    icon: Bot,
  },
  {
    title: 'Review',
    description: 'Keep consequential decisions in human hands.',
    icon: ShieldCheck,
  },
]

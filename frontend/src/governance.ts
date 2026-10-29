import { uuid } from './banking'
export const actions = {
  CHECK_SERVICE_HEALTH: 'Check service health',
  REFRESH_INCIDENT_EVIDENCE: 'Refresh incident evidence',
  restart_banking_service: 'Restart banking service (not executable)',
  scale_banking_service: 'Scale banking service (not executable)',
  investigate_dependency: 'Investigate dependency (not executable)',
} as const
export type Action = keyof typeof actions
export const safeActions = [
  'CHECK_SERVICE_HEALTH',
  'REFRESH_INCIDENT_EVIDENCE',
] as const
export const evidenceRefs = [
  'rule.banking_unavailable',
  'rule.high_http_error_rate',
  'rule.elevated_p95_latency',
  'rule.high_transfer_failure_rate',
] as const
export const decisionReasons = {
  reviewed_evidence: 'Reviewed evidence',
  insufficient_evidence: 'Insufficient evidence',
  risk_unacceptable: 'Risk unacceptable',
  alternative_required: 'Alternative required',
} as const
export const outcomes = {
  service_up: 'Service observed up',
  service_down: 'Service observed down',
  evidence_refreshed: 'Evidence refreshed',
  evidence_partial: 'Partial evidence collected',
  source_unavailable: 'Source unavailable',
  timeout: 'Timed out',
  cancelled: 'Cancelled',
  internal_failure: 'Internal failure',
} as const
export const verificationReasons = {
  recorded_success: 'Recorded execution succeeded',
  recorded_failure: 'Recorded execution failed',
  execution_incomplete: 'Execution was incomplete',
  inconsistent_record: 'Recorded evidence is inconsistent',
} as const
const fail = (): never => {
  throw new Error('Invalid governance response')
}
function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : fail()
}
function date(v: unknown): string {
  return typeof v === 'string' && Number.isFinite(Date.parse(v)) ? v : fail()
}
function id(v: unknown): string {
  return typeof v === 'string' && uuid.test(v) ? v : fail()
}
function choice<T extends string>(v: unknown, options: readonly T[]): T {
  return options.includes(v as T) ? (v as T) : fail()
}
function list(v: unknown, max: number): unknown[] {
  return Array.isArray(v) && v.length <= max ? v : fail()
}
export interface Proposal {
  id: string
  action: Action
  refs: string[]
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  created: string
  decided: string | null
  reason: keyof typeof decisionReasons | null
  audit: { event: string; actor: string; at: string }[]
}
export interface Execution {
  id: string
  action: (typeof safeActions)[number]
  status: 'RUNNING' | 'SUCCEEDED' | 'FAILED'
  started: string
  completed: string | null
  outcome: keyof typeof outcomes | null
  audit: { event: string; at: string }[]
}
export interface Verification {
  id: string
  status:
    'EXECUTION_SUCCEEDED' | 'EXECUTION_FAILED' | 'VERIFICATION_INCONCLUSIVE'
  reason: keyof typeof verificationReasons
  at: string
  actor: 'human_reviewer'
}
export function parseProposal(raw: unknown): Proposal {
  const r = obj(raw),
    status = choice(r.status, ['PENDING', 'APPROVED', 'REJECTED'] as const),
    created = date(r.created_at),
    decided = r.decided_at === null ? null : date(r.decided_at),
    reason =
      r.decision_reason === null
        ? null
        : choice(
            r.decision_reason,
            Object.keys(decisionReasons) as (keyof typeof decisionReasons)[],
          )
  if (
    r.created_by !== 'proposal_service' ||
    (status === 'PENDING'
      ? decided !== null || r.decided_by !== null || reason !== null
      : decided === null ||
        r.decided_by !== 'human_reviewer' ||
        reason === null)
  )
    fail()
  const refs = list(r.evidence_references, 4).map((v) =>
    choice(v, evidenceRefs),
  )
  if (!refs.length) fail()
  const audit = list(r.audit, 2).map((raw) => {
    const a = obj(raw)
    return {
      event: choice(a.event, ['CREATED', 'APPROVED', 'REJECTED'] as const),
      actor: choice(a.actor, ['proposal_service', 'human_reviewer'] as const),
      at: date(a.timestamp),
    }
  })
  if (
    audit.length !== (status === 'PENDING' ? 1 : 2) ||
    audit[0]?.event !== 'CREATED' ||
    audit[0].actor !== 'proposal_service' ||
    audit[0].at !== created ||
    (status !== 'PENDING' &&
      (audit[1].event !== status ||
        audit[1].actor !== 'human_reviewer' ||
        audit[1].at !== decided)) ||
    (decided !== null && Date.parse(decided) < Date.parse(created))
  )
    fail()
  return {
    id: id(r.proposal_id),
    action: choice(r.action, Object.keys(actions) as Action[]),
    refs,
    status,
    created,
    decided,
    reason,
    audit,
  }
}
export function parseExecution(raw: unknown): Execution {
  const r = obj(raw),
    status = choice(r.status, ['RUNNING', 'SUCCEEDED', 'FAILED'] as const),
    started = date(r.started_at),
    completed = r.completed_at === null ? null : date(r.completed_at),
    outcome =
      r.outcome === null
        ? null
        : choice(r.outcome, Object.keys(outcomes) as (keyof typeof outcomes)[])
  if (
    obj(r.parameters).service !== 'banking-service' ||
    (status === 'RUNNING'
      ? completed !== null || outcome !== null
      : completed === null || outcome === null)
  )
    fail()
  const audit = list(r.audit, 2).map((raw) => {
    const a = obj(raw)
    return {
      event: choice(a.event, ['RUNNING', 'SUCCEEDED', 'FAILED'] as const),
      at: date(a.timestamp),
    }
  })
  if (
    audit.length !== (status === 'RUNNING' ? 1 : 2) ||
    audit[0]?.event !== 'RUNNING' ||
    audit[0].at !== started ||
    (status !== 'RUNNING' &&
      (audit[1].event !== status || audit[1].at !== completed)) ||
    (completed !== null && Date.parse(completed) < Date.parse(started))
  )
    fail()
  return {
    id: id(r.proposal_id),
    action: choice(r.action, safeActions),
    status,
    started,
    completed,
    outcome,
    audit,
  }
}
export function parseVerification(raw: unknown): Verification {
  const r = obj(raw)
  if (
    r.incident_resolution !== 'NOT_DETERMINED' ||
    r.basis !== 'recorded_execution' ||
    r.verified_by !== 'human_reviewer' ||
    typeof r.execution_sha256 !== 'string' ||
    !/^[a-f0-9]{64}$/.test(r.execution_sha256)
  )
    fail()
  return {
    id: id(r.proposal_id),
    status: choice(r.status, [
      'EXECUTION_SUCCEEDED',
      'EXECUTION_FAILED',
      'VERIFICATION_INCONCLUSIVE',
    ] as const),
    reason: choice(
      r.reason,
      Object.keys(verificationReasons) as (keyof typeof verificationReasons)[],
    ),
    at: date(r.verified_at),
    actor: 'human_reviewer',
  }
}
export class GovernanceError extends Error {
  constructor(public status: number) {
    super(
      status === 401
        ? 'Authentication failed. Credential cleared.'
        : status === 403
          ? 'This credential is not authorized for the selected role or action. Credential cleared.'
          : status === 404
            ? 'No record found.'
            : status === 409
              ? 'Conflict: another decision or execution may already exist. Read the latest records before proceeding.'
              : status === 400
                ? 'Request rejected. Check the proposal and selected details.'
                : status === 503
                  ? 'Workflow disabled or service unavailable. No backend features were enabled.'
                  : 'Request failed. State may have changed; read the latest records before proceeding.',
    )
  }
}
export type Operation =
  | 'proposal'
  | 'approve'
  | 'reject'
  | 'execute'
  | 'execution'
  | 'verify'
  | 'verification'
export async function governanceRequest(
  operation: Operation,
  proposalId: string,
  token: string,
  signal: AbortSignal,
  body?: unknown,
): Promise<Proposal | Execution | Verification> {
  if (!/^[\x21-\x7E]{32,256}$/.test(token)) throw new GovernanceError(401)
  if (!uuid.test(proposalId)) throw new GovernanceError(400)
  const read = ['proposal', 'execution', 'verification'].includes(operation)
  const suffix = `/${proposalId}${operation === 'proposal' ? '' : `/${operation}`}`
  const r = await fetch(`/governance-api/remediation/proposals${suffix}`, {
    method: read ? 'GET' : 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      ...(!read ? { 'Content-Type': 'application/json' } : {}),
    },
    body: read ? undefined : JSON.stringify(body),
    signal: AbortSignal.any([
      signal,
      AbortSignal.timeout(operation === 'execute' ? 75000 : 15000),
    ]),
    credentials: 'omit',
    cache: 'no-store',
    redirect: 'error',
  })
  if (!r.ok) throw new GovernanceError(r.status)
  const reader = r.body?.getReader()
  if (!reader) return fail()
  const chunks: Uint8Array[] = []
  let size = 0
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > 32768) {
        await reader.cancel()
        return fail()
      }
      chunks.push(value)
    }
  } finally {
    reader.releaseLock()
  }
  const data = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) {
    data.set(chunk, offset)
    offset += chunk.length
  }
  const raw: unknown = JSON.parse(new TextDecoder().decode(data)),
    result =
      operation === 'execute' || operation === 'execution'
        ? parseExecution(raw)
        : operation === 'verify' || operation === 'verification'
          ? parseVerification(raw)
          : parseProposal(raw)
  if (result.id.toLowerCase() !== proposalId.toLowerCase()) return fail()
  return result
}

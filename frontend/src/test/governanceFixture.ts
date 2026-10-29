export const governanceId = '61616161-6161-4161-8161-616161616161'
export function proposalFixture(
  status = 'PENDING',
  action = 'CHECK_SERVICE_HEALTH',
) {
  const t = '2026-10-16T12:00:00Z'
  return {
    proposal_id: governanceId,
    action,
    evidence_references: ['rule.banking_unavailable'],
    status,
    created_at: t,
    created_by: 'proposal_service',
    decided_at: status === 'PENDING' ? null : t,
    decided_by: status === 'PENDING' ? null : 'human_reviewer',
    decision_reason: status === 'PENDING' ? null : 'reviewed_evidence',
    audit: [
      { event: 'CREATED', actor: 'proposal_service', timestamp: t },
      ...(status === 'PENDING'
        ? []
        : [{ event: status, actor: 'human_reviewer', timestamp: t }]),
    ],
  }
}
export function executionFixture(
  status = 'SUCCEEDED',
  outcome: string | null = 'service_up',
) {
  const t = '2026-10-16T12:00:00Z'
  return {
    proposal_id: governanceId,
    action: 'CHECK_SERVICE_HEALTH',
    parameters: { service: 'banking-service' },
    status,
    started_at: t,
    completed_at: status === 'RUNNING' ? null : t,
    outcome: status === 'RUNNING' ? null : outcome,
    audit: [
      { event: 'RUNNING', timestamp: t },
      ...(status === 'RUNNING' ? [] : [{ event: status, timestamp: t }]),
    ],
  }
}
export function verificationFixture(
  status = 'EXECUTION_SUCCEEDED',
  reason = 'recorded_success',
) {
  return {
    proposal_id: governanceId,
    status,
    reason,
    verified_at: '2026-10-16T12:00:00Z',
    execution_sha256: 'a'.repeat(64),
    incident_resolution: 'NOT_DETERMINED',
    basis: 'recorded_execution',
    verified_by: 'human_reviewer',
  }
}

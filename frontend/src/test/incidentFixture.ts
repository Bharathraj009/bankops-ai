import { monitoringFixture } from './monitoringFixture'
export function incidentFixture(time = new Date().toISOString()) {
  const d = monitoringFixture(time)
  return {
    ...d,
    state: 'incident',
    triggered_rules: ['high_http_error_rate'],
    rules: d.rules.map((r) => ({
      ...r,
      state: r.rule_id === 'high_http_error_rate' ? 'incident' : 'healthy',
      reason:
        r.rule_id === 'high_http_error_rate' ? 'threshold_reached' : r.reason,
      observed_value: r.rule_id === 'high_http_error_rate' ? 0.2 : 1,
      threshold: r.rule_id === 'high_http_error_rate' ? 0.05 : null,
      observed_traffic: 20,
      minimum_traffic: 0.1,
    })),
    evidence: {
      ...d.evidence,
      metrics: d.evidence.metrics.map((m) => ({
        ...m,
        value: m.name === 'api_error_rate' ? 0.2 : m.value,
      })),
    },
  }
}
export function reportFixture(time = new Date().toISOString()) {
  const trace = 'a'.repeat(32),
    correlation = '11111111-1111-4111-8111-111111111111'
  return {
    started_at: time,
    completed_at: time,
    evidence_status: 'complete',
    detection: incidentFixture(time),
    traces: {
      source: 'jaeger',
      service: 'banking-service',
      window_start: time,
      window_end: time,
      collected_at: time,
      slow_span_seconds: 1,
      status: 'ok',
      truncated: false,
      traces: [
        {
          trace_id: trace,
          service: 'banking-service',
          started_at: time,
          duration_seconds: 2,
          failed: true,
          slow_span_count: 1,
          failed_span_count: 1,
          truncated: false,
          spans: [
            {
              span_id: 'b'.repeat(16),
              name: 'db.call',
              service: 'banking-service',
              started_at: time,
              duration_seconds: 2,
              failed: true,
              slow: true,
            },
          ],
        },
      ],
    },
    logs: {
      source: 'local_jsonl',
      service: 'banking-service',
      collected_at: time,
      window_start: time,
      window_end: time,
      status: 'ok',
      truncated: false,
      events: [
        {
          timestamp: time,
          level: 'ERROR',
          event_type: 'http_request_completed',
          trace_id: trace,
          correlation_id: correlation,
        },
      ],
    },
    observed_facts: {
      returned_trace_count: 1,
      failed_trace_count: 1,
      slow_span_count: 1,
      returned_log_event_count: 1,
      warn_event_count: 0,
      error_event_count: 1,
    },
    correlations: [
      {
        trace_id: trace,
        correlation_id: correlation,
        trace_present: true,
        log_event_indexes: [0],
      },
    ],
    possible_explanations: [],
    rca: {
      status: 'hypotheses',
      root_cause_confirmed: false,
      analyzed_at: time,
      reason: 'supported_hypotheses',
      hypotheses: [
        {
          kind: 'http_error_degradation',
          supporting_evidence: ['rule.high_http_error_rate'],
          confidence: 'low',
        },
      ],
      evidence: [
        {
          id: 'rule.high_http_error_rate',
          source: 'rule',
          observation: 'threshold_reached',
          timestamp: time,
          observed_value: 0.2,
          threshold: 0.05,
          supports: ['http_error_degradation'],
        },
      ],
      uncertainty: ['causality_unconfirmed', 'bounded_sample'],
      recommended_investigation_steps: [
        'compare_metric_windows',
        'collect_additional_evidence',
      ],
    },
  }
}

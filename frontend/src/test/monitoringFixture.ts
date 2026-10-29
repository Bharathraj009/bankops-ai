import { definitions } from '../monitoring'
export function monitoringFixture(time = new Date().toISOString()) {
  return {
    state: 'healthy',
    detected_at: time,
    triggered_rules: [],
    rules: [
      'banking_unavailable',
      'high_http_error_rate',
      'elevated_p95_latency',
      'high_transfer_failure_rate',
    ].map((rule_id) => ({
      rule_id,
      state: 'healthy',
      reason:
        rule_id === 'banking_unavailable' ? 'service_up' : 'below_threshold',
    })),
    evidence: {
      source: 'prometheus',
      service: 'banking-service',
      window: '5m',
      status: 'ok',
      evaluated_at: time,
      collected_at: time,
      metrics: Object.entries(definitions).map(([name, d]) => ({
        name,
        unit: d.unit,
        status: 'ok',
        value:
          name === 'banking_availability'
            ? 1
            : name === 'api_error_rate'
              ? 0.01
              : name === 'api_latency_p95'
                ? 0.2
                : name === 'transfer_failure_rate'
                  ? 0
                  : name === 'api_request_rate'
                    ? 20
                    : 2,
        sampled_at: time,
      })),
    },
  }
}

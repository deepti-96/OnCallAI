"""Synthetic incidents for the MIND demo and tests. No real company data.

Topology (all invented):
    checkout-service --depends on--> payment-service --depends on--> card-gateway

History written to MIND before Incident B:
  A  payment-service: v2.14.0 config change shrank the card-gateway timeout -> 5xx
  C  checkout-service: payment-service slowness cascaded into checkout deadline errors
  D  inventory-service: unrelated memory leak whose ALERT TEXT looks a lot like B's

Incident B (new): checkout-service 504s and latency. Its logs never name
payment-service. Similar text points at D. The relationship path points
at C and then A. The real cause of B is different again (connection pool
shrunk in payment-service v2.15.0), so copying A's RCA would be wrong.
"""

INCIDENT_A = {
    "id": "demo-inc-A",
    "service": "payment-service",
    "environment": "prod",
    "severity": "CRITICAL",
    "payload": {
        "alert": "Elevated 5xx rate on POST /charge after payment-service v2.14.0 rollout",
        "dependencies": ["card-gateway"],
        "deployment": "payment-service v2.14.0",
    },
    "logs": [
        "deploy payment-service v2.14.0 config changed CARD_GATEWAY_TIMEOUT_MS 3000 -> 300",
        "upstream=card-gateway request timed out after 300ms",
        "HTTP 503 returned to caller for POST /charge",
    ],
    "resolution": {
        "root_cause": "payment-service v2.14.0 lowered CARD_GATEWAY_TIMEOUT_MS from 3000 to 300, so normal card-gateway latency tripped timeouts.",
        "mitigation": ["Revert CARD_GATEWAY_TIMEOUT_MS to 3000", "Add a config diff check to the payment-service deploy pipeline"],
        "affected_component": "payment-service",
        "deployment": "payment-service v2.14.0",
    },
}

INCIDENT_C = {
    "id": "demo-inc-C",
    "service": "checkout-service",
    "environment": "prod",
    "severity": "HIGH",
    "payload": {
        "alert": "Checkout success rate dropped below SLO",
        "dependencies": ["payment-service"],
    },
    "logs": [
        "checkout-service calling payment-service: deadline exceeded after 2000ms",
        "payment-service p99 latency 4.2s",
    ],
    "resolution": {
        "root_cause": "payment-service slow responses cascaded into checkout-service deadline errors because checkout had no circuit breaker.",
        "mitigation": ["Enable the checkout-service circuit breaker on payment-service calls", "Scale payment-service"],
        "affected_component": "payment-service",
    },
}

INCIDENT_D = {
    "id": "demo-inc-D",
    "service": "inventory-service",
    "environment": "prod",
    "severity": "HIGH",
    "payload": {"alert": "Elevated error rate and p99 latency spike on stock sync API"},
    "logs": [
        "HTTP 500 elevated error rate on stock sync API",
        "p99 latency spike on stock sync API",
        "OOMKilled inventory-sync worker",
    ],
    "resolution": {
        "root_cause": "inventory-sync worker memory leak after inventory-service v3.2.0 caused OOM restarts.",
        "mitigation": ["Raise the inventory-sync memory limit", "Patch the leak in the batch loader"],
    },
}

INCIDENT_B = {
    "id": "demo-inc-B",
    "service": "checkout-service",
    "environment": "prod",
    "severity": "CRITICAL",
    "payload": {"alert": "Elevated error rate and p99 latency spike on cart submit API"},
    "logs": [
        "HTTP 504 Gateway Timeout on POST /api/cart/submit",
        "p99 latency spike to 3.9s on cart submit API",
        "worker threads blocked waiting on downstream response",
    ],
    # Revealed only after investigation, used when we resolve B at the end of the demo.
    "true_resolution": {
        "root_cause": "payment-service v2.15.0 cut its DB connection pool from 50 to 10, so payment calls queued and checkout hit gateway timeouts.",
        "mitigation": ["Restore payment-service DB pool size to 50", "Alert on payment-service pool saturation"],
        "affected_component": "payment-service",
        "deployment": "payment-service v2.15.0",
    },
}

HISTORY = [INCIDENT_A, INCIDENT_C, INCIDENT_D]

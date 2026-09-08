# Production Operations & Resilience

Arbiter v0.20 adds dependency health, load admission, backlog pressure states, incident records, and repeatable recovery drills. The application can now expose whether required dependencies are healthy and whether work queues are approaching unsafe pressure.

Production certification still requires deployment-backed evidence: multi-zone HA, external telemetry/alerting, managed database failover, restore drills, load tests, and incident exercises in the actual target environment.

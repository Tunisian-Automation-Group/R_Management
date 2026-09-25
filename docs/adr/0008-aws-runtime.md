# 0008. AWS runtime

## Decision
- **Edge.** CloudFront serves the web app from S3 and forwards `/api/*` to the
  ALB and `/media/*` to the media bucket — one origin, no CORS. AWS WAF on the
  distribution: managed rule sets and per-IP rate limits.
- **Compute.** ECS on Fargate, one service per deployable, private subnets
  only. The ALB reaches the gateway; the gateway reaches the services through
  ECS Service Connect. Security groups allow nothing else. Target-tracking
  autoscaling on CPU and request count.
- **Data.** Aurora PostgreSQL Serverless v2 (writer + reader, multi-AZ), one
  database per service, credentials in Secrets Manager.
- **Messaging.** SNS + SQS (ADR 0003). **Identity** Cognito (0002).
  **Email** SES (0006). **Media** S3 (0007).
- **Observability.** JSON logs to CloudWatch with request ids, OpenTelemetry
  traces to X-Ray, alarms on 5xx rate, latency, DLQ depth and DB CPU.
- **Delivery.** Terraform, one state per environment. GitHub Actions: test,
  build images to ECR, run migrations as a one-off task, then roll ECS
  services. OIDC federation, no long-lived keys.

## Rejected
- *EKS.* Nothing here needs Kubernetes; Fargate removes the node fleet.
- *Lambda for the services.* Long-running consumers and connection pooling to
  Postgres fit containers better; Lambda stays an option for glue.
- *Keep the Python gateway as the only edge.* It remains the router (one
  tested routing table in every environment) but sits behind CloudFront, WAF
  and the ALB rather than being them.

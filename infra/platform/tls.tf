# Encryption inside the VPC (P-11).
#
# - Service to service: Service Connect TLS. The proxies in every task get
#   short-lived certificates from this private CA and speak TLS to each other;
#   the services keep calling http://<name>:8000 on their own proxy.
# - ALB to gateway: HTTPS to the task. The gateway serves TLS with a key it
#   makes when it starts (cappy_common.selfsigned); the ALB encrypts but does
#   not check target certificates, which is how AWS documents it for targets.
# - Services to Aurora: TLS verified against the RDS CA bundle baked into the
#   image (sslmode verify-full, data.tf).
#
# ponytail: one CA in short-lived-certificate mode (the cheaper mode, ~$50 a
# month); a CA hierarchy only if certificates are ever issued outside ECS.

resource "aws_acmpca_certificate_authority" "internal" {
  type       = "ROOT"
  usage_mode = "SHORT_LIVED_CERTIFICATE"
  certificate_authority_configuration {
    key_algorithm     = "EC_prime256v1"
    signing_algorithm = "SHA256WITHECDSA"
    subject {
      common_name  = "${local.name}.internal"
      organization = "Cappy"
    }
  }
  permanent_deletion_time_in_days = 7
}

resource "aws_acmpca_certificate" "internal_root" {
  certificate_authority_arn   = aws_acmpca_certificate_authority.internal.arn
  certificate_signing_request = aws_acmpca_certificate_authority.internal.certificate_signing_request
  signing_algorithm           = "SHA256WITHECDSA"
  template_arn                = "arn:aws:acm-pca:::template/RootCACertificate/V1"
  validity {
    type  = "YEARS"
    value = 10
  }
}

resource "aws_acmpca_certificate_authority_certificate" "internal" {
  certificate_authority_arn = aws_acmpca_certificate_authority.internal.arn
  certificate               = aws_acmpca_certificate.internal_root.certificate
  certificate_chain         = aws_acmpca_certificate.internal_root.certificate_chain
}

# Service Connect keeps each task's private key encrypted with this key.
resource "aws_kms_key" "service_connect" {
  description             = "${local.name} Service Connect TLS"
  enable_key_rotation     = true
  deletion_window_in_days = 7
}

data "aws_iam_policy_document" "ecs_infrastructure_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "service_connect_tls" {
  name               = "${local.name}-service-connect-tls"
  assume_role_policy = data.aws_iam_policy_document.ecs_infrastructure_assume.json
}

resource "aws_iam_role_policy_attachment" "service_connect_tls" {
  role       = aws_iam_role.service_connect_tls.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRolePolicyForServiceConnectTransportLayerSecurity"
}

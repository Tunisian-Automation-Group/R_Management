"""Create, idempotently, the AWS resources the local stack needs, with the
names Terraform gives them: the event topic, one queue (and dead-letter
queue) per consumer, the media bucket, the sender identity, the user pool and
its app client, and two demo people. Then load the demo world.

Writes /run/cappy/local.env (for the services) and /run/cappy/web.env (for
the Vite dev server). Run by `make up`; safe to run again.
"""

from __future__ import annotations

import json
import os
import sys
import time

import boto3

REGION = "eu-central-1"
ACCOUNT = "000000000000"
LOCALSTACK = os.environ.get("AWS_ENDPOINT_URL", "http://localstack:4566")
COGNITO = os.environ.get("COGNITO_ENDPOINT_URL", "http://cognito:9229")
COGNITO_PUBLIC = os.environ.get("COGNITO_PUBLIC_URL", "http://localhost:9229")
OUT = "/run/cappy"

TOPIC = "cappy-events"
BUCKET = "cappy-media"
MAIL_FROM = "no-reply@cappy.local"
# Which events each service's queue receives (Terraform: modules/messaging).
CONSUMERS = {
    "catalog": ["booking.rated", "payment.payouts_ready", "booking.renter_rated"],
    "booking": [
        "payment.authorised",
        "payment.failed",
        "listing.changed",
        "moderation.owner_suspended",
        "payment.identity_verified",
        "profile.deleted",
        "moderation.owner_reinstated",
    ],
    "payments": ["booking.status_changed", "profile.deleted"],
    "notifications": [
        "booking.status_changed",
        "payment.payout_sent",
        "profile.deleted",
        "booking.message",
        "moderation.report_received",
        "moderation.decision",
    ],
}
DEMO_PASSWORD = "Demo-pass-123!"
DEMO = {
    "host": ("host@demo.cappy.local", "o1"),
    "buyer": ("buyer@demo.cappy.local", None),
    # A moderator, for the admin console (member of the "admin" group).
    "staff": ("staff@demo.cappy.local", None),
}


def client(name: str, endpoint: str = LOCALSTACK):
    return boto3.client(name, region_name=REGION, endpoint_url=endpoint, aws_access_key_id="test", aws_secret_access_key="test")


def wait(what: str, fn) -> None:
    for _ in range(60):
        try:
            fn()
            return
        except Exception:  # noqa: BLE001
            time.sleep(1)
    sys.exit(f"{what} did not come up")


def messaging() -> dict[str, str]:
    sns, sqs = client("sns"), client("sqs")
    topic = sns.create_topic(Name=TOPIC)["TopicArn"]
    urls = {}
    for service, types in CONSUMERS.items():
        dlq = sqs.create_queue(QueueName=f"cappy-{service}-dlq", Attributes={"MessageRetentionPeriod": "1209600"})
        dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq["QueueUrl"], AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        attributes = {
            "VisibilityTimeout": "120",
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "12"}),
        }
        try:
            q = sqs.create_queue(QueueName=f"cappy-{service}", Attributes=attributes)
        except sqs.exceptions.QueueNameExists:
            # Made by an earlier run with other settings: bring it up to date.
            q = sqs.get_queue_url(QueueName=f"cappy-{service}")
            sqs.set_queue_attributes(QueueUrl=q["QueueUrl"], Attributes=attributes)
        arn = sqs.get_queue_attributes(QueueUrl=q["QueueUrl"], AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        existing = {s["Endpoint"] for s in sns.list_subscriptions_by_topic(TopicArn=topic)["Subscriptions"]}
        if arn not in existing:
            sns.subscribe(
                TopicArn=topic,
                Protocol="sqs",
                Endpoint=arn,
                Attributes={"RawMessageDelivery": "true", "FilterPolicy": json.dumps({"type": types})},
            )
        urls[service] = q["QueueUrl"]
    return {"topic": topic, **urls}


def storage_and_mail() -> None:
    s3 = client("s3")
    try:
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass
    client("ses").verify_email_identity(EmailAddress=MAIL_FROM)


def identity() -> dict:
    idp = client("cognito-idp", COGNITO)
    pools = [p for p in idp.list_user_pools(MaxResults=60)["UserPools"] if p["Name"] == "cappy"]
    pool = pools[0]["Id"] if pools else idp.create_user_pool(
        PoolName="cappy",
        UsernameAttributes=["email"],
        AutoVerifiedAttributes=["email"],
        # As in infra/platform/identity.tf: 12 characters, no composition rules.
        Policies={"PasswordPolicy": {"MinimumLength": 12, "RequireUppercase": False, "RequireLowercase": False, "RequireNumbers": False, "RequireSymbols": False}},
    )["UserPool"]["Id"]
    clients = [c for c in idp.list_user_pool_clients(UserPoolId=pool, MaxResults=60)["UserPoolClients"] if c["ClientName"] == "web"]
    app_client = clients[0]["ClientId"] if clients else idp.create_user_pool_client(
        UserPoolId=pool, ClientName="web", ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
    )["UserPoolClient"]["ClientId"]
    try:
        idp.create_group(GroupName="admin", UserPoolId=pool, Description="Cappy staff")
    except Exception as e:  # noqa: BLE001 - cognito-local and AWS name "already exists" differently
        if "exist" not in str(e).lower():
            raise
    subs = {}
    for role, (email, _) in DEMO.items():
        found = idp.list_users(UserPoolId=pool, Filter=f'email = "{email}"')["Users"]
        user = found[0] if found else idp.admin_create_user(
            UserPoolId=pool,
            Username=email,
            UserAttributes=[{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"}],
            MessageAction="SUPPRESS",
            TemporaryPassword=DEMO_PASSWORD,
        )["User"]
        idp.admin_set_user_password(UserPoolId=pool, Username=email, Password=DEMO_PASSWORD, Permanent=True)
        subs[role] = next(a["Value"] for a in user["Attributes"] if a["Name"] == "sub")
        if role == "staff":
            idp.admin_add_user_to_group(UserPoolId=pool, Username=email, GroupName="admin")
    return {"pool": pool, "client": app_client, "subs": subs}


def main() -> None:
    wait("LocalStack", lambda: client("sqs").list_queues())
    wait("cognito-local", lambda: client("cognito-idp", COGNITO).list_user_pools(MaxResults=1))
    m = messaging()
    storage_and_mail()
    ident = identity()
    env = {
        "AUTH_ISSUER": f"http://0.0.0.0:9229/{ident['pool']}",
        "AUTH_JWKS_URL": f"{COGNITO}/{ident['pool']}/.well-known/jwks.json",
        "AUTH_CLIENT_IDS": ident["client"],
        "USER_POOL_ID": ident["pool"],
        "EVENT_BUS_URL": f"sns://{m['topic']}",
        **{f"{s.upper()}_QUEUE_URL": m[s] for s in CONSUMERS},
        "DEMO_OWNER_MAP": f"o1={ident['subs']['host']}",
    }
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/local.env", "w") as f:
        f.writelines(f"{k}={v}\n" for k, v in env.items())
    with open(f"{OUT}/web.env", "w") as f:
        demo = ";".join(f"demo {role}:{email}:{DEMO_PASSWORD}" for role, (email, _) in DEMO.items())
        f.write(f"VITE_COGNITO_ENDPOINT={COGNITO_PUBLIC}\nVITE_COGNITO_CLIENT_ID={ident['client']}\n")
        # Local only: one-tap sign-in to the seeded accounts. Never set in a deploy.
        f.write(f"VITE_DEMO_ACCOUNTS={demo}\n")
    print(json.dumps({"pool": ident["pool"], "client": ident["client"], "demo": {r: e for r, (e, _) in DEMO.items()}}))


if __name__ == "__main__":
    main()

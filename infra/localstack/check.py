"""After `terraform apply` here: publish one event of each type and check
each queue received exactly the types its filter asks for."""

import json
import subprocess
import time

import boto3

out = json.loads(subprocess.check_output(["terraform", "output", "-json", "messaging"]))
kw = dict(region_name="eu-central-1", endpoint_url="http://localhost:4566", aws_access_key_id="test", aws_secret_access_key="test")
sns, sqs = boto3.client("sns", **kw), boto3.client("sqs", **kw)
types = [
    "booking.rated",
    "payment.authorised",
    "booking.status_changed",
    "payment.payout_sent",
    "payment.payouts_ready",
    "profile.deleted",
    "person.signed_out",
    "booking.message",
    "moderation.report_received",
    "moderation.decision",
    "moderation.owner_suspended",
    "payment.identity_verified",
    "booking.renter_rated",
    "moderation.owner_reinstated",
    "listing.changed",
    "booking.owner_reliability",
    "moderation.person_flagged",
]
for t in types:
    sns.publish(TopicArn=out["topic_arn"], Message=json.dumps({"type": t}), MessageAttributes={"type": {"DataType": "String", "StringValue": t}})
time.sleep(2)
expected = {
    "catalog": {"booking.rated", "payment.payouts_ready", "booking.renter_rated", "booking.owner_reliability", "moderation.person_flagged"},
    "booking": {
        "payment.authorised",
        "listing.changed",
        "moderation.owner_suspended",
        "payment.identity_verified",
        "profile.deleted",
        "person.signed_out",
        "moderation.owner_reinstated",
    },
    "payments": {"booking.status_changed", "profile.deleted", "person.signed_out"},
    "notifications": {
        "booking.status_changed",
        "payment.payout_sent",
        "profile.deleted",
        "person.signed_out",
        "booking.message",
        "moderation.report_received",
        "moderation.decision",
    },
}
for svc, url in out["queue_urls"].items():
    got = set()
    for _ in range(3):
        for m in sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=1).get("Messages", []):
            got.add(json.loads(m["Body"])["type"])  # raw delivery: the body is the event
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
    assert got == expected[svc], (svc, got)
    print(f"{svc:14} {sorted(got)}")
print("routing ok")

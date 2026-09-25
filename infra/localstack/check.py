"""After `terraform apply` here: publish one event of each type and check
each queue received exactly the types its filter asks for."""

import json
import subprocess
import time

import boto3

out = json.loads(subprocess.check_output(["terraform", "output", "-json", "messaging"]))
kw = dict(region_name="eu-central-1", endpoint_url="http://localhost:4566", aws_access_key_id="test", aws_secret_access_key="test")
sns, sqs = boto3.client("sns", **kw), boto3.client("sqs", **kw)
types = ["booking.rated", "payment.authorised", "booking.status_changed", "payment.payout_sent", "listing.changed"]
for t in types:
    sns.publish(TopicArn=out["topic_arn"], Message=json.dumps({"type": t}), MessageAttributes={"type": {"DataType": "String", "StringValue": t}})
time.sleep(2)
expected = {
    "catalog": {"booking.rated"},
    "booking": {"payment.authorised"},
    "payments": {"booking.status_changed"},
    "notifications": {"booking.status_changed", "payment.payout_sent"},
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

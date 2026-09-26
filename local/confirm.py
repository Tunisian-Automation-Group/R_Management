"""Finish a local sign-up by hand (`make confirm EMAIL=… [ADMIN=1] [LEAD=1]`).

cognito-local confirms a sign-up without marking the email verified, and
Cappy only emails verified addresses; this marks it, confirms the account if
the code was never entered, with ADMIN=1 adds it to the staff group, and
with LEAD=1 to the leads too (higher refund limits, H-6).
Local stack only: it talks to cognito-local on :9229.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3

ENV = dict(
    line.strip().split("=", 1)
    for line in (Path(__file__).parents[1] / ".local" / "local.env").read_text().splitlines()
    if "=" in line
)
email = os.environ.get("EMAIL") or sys.exit("usage: make confirm EMAIL=you@example.com [ADMIN=1] [LEAD=1]")
pool = ENV["USER_POOL_ID"]
idp = boto3.client(
    "cognito-idp",
    region_name="eu-central-1",
    endpoint_url="http://localhost:9229",
    aws_access_key_id="x",
    aws_secret_access_key="x",
)
users = idp.list_users(UserPoolId=pool, Filter=f'email = "{email}"')["Users"]
if not users:
    sys.exit(f"no local account for {email}: sign up in the app first")
name = users[0]["Username"]
if users[0]["UserStatus"] == "UNCONFIRMED":
    idp.admin_confirm_sign_up(UserPoolId=pool, Username=name)
idp.admin_update_user_attributes(
    UserPoolId=pool,
    Username=name,
    UserAttributes=[{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"}],
)
lead = os.environ.get("LEAD") == "1"
groups = ["admin", "admin-lead"] if lead else ["admin"] if os.environ.get("ADMIN") == "1" else []
for group in groups:
    try:
        idp.create_group(GroupName=group, UserPoolId=pool)
    except Exception as e:  # noqa: BLE001 - cognito-local and AWS say "already exists" differently
        if "exist" not in str(e).lower():
            raise
    idp.admin_add_user_to_group(UserPoolId=pool, Username=name, GroupName=group)
print(f"{email}: confirmed, email verified" + (f", in {' and '.join(groups)}" if groups else ""))

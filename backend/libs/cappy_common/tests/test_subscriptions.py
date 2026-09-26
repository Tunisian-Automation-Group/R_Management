"""Who hears which event is written down four times: the Terraform
subscriptions (AWS), the LocalStack module and its check, the local bootstrap,
and each service's handlers. They must agree (D-13): an event a queue never
receives is a feature that silently does nothing."""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

from notifications.handlers import handlers as notification_handlers
from payments.handlers import handlers as payment_handlers
from payments.provider import FakeProvider

from booking.handlers import handlers as booking_handlers
from booking.settings import Settings as BookingSettings
from cappy_common.events import ALL_TYPES
from cappy_common.guard import REVOKING
from catalog.main import HANDLERS as CATALOG_HANDLERS

ROOT = Path(__file__).parents[4]


def _terraform(path: str) -> dict[str, set[str]]:
    text = (ROOT / path).read_text()
    block = text[text.index("consumers = {") : text.index("}", text.index("consumers = {"))]
    return {m[1]: set(re.findall(r'"([^"]+)"', m[2])) for m in re.finditer(r"(\w+)\s*=\s*\[([^\]]*)\]", block)}


def _bootstrap() -> dict[str, set[str]]:
    spec = importlib.util.spec_from_file_location("bootstrap", ROOT / "local" / "bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {k: set(v) for k, v in module.CONSUMERS.items()}


def _localstack_check() -> dict[str, set[str]]:
    text = (ROOT / "infra" / "localstack" / "check.py").read_text()
    start = text.index("expected = {") + len("expected = ")
    tree = ast.parse(text[start:], mode="exec").body[0]
    return {k: set(v) for k, v in ast.literal_eval(tree.value).items()}


def _handled() -> dict[str, set[str]]:
    return {
        "catalog": set(CATALOG_HANDLERS),
        "booking": set(booking_handlers(BookingSettings())),
        "payments": set(payment_handlers(FakeProvider(), "payments")),
        "notifications": set(notification_handlers(None, None, "http://x")),  # type: ignore[arg-type]
    }


def test_every_list_of_subscriptions_agrees():
    aws = _terraform("infra/platform/data.tf")
    assert _terraform("infra/localstack/main.tf") == aws
    assert _bootstrap() == aws
    assert _localstack_check() == aws


def test_every_subscribed_event_is_handled_and_every_handler_subscribed():
    aws = _terraform("infra/platform/data.tf")
    for service, handled in _handled().items():
        subscribed = aws[service]
        assert subscribed <= ALL_TYPES, (service, subscribed - ALL_TYPES)
        # Sign-out and deletion are handled by every service's runtime (guard.py).
        assert subscribed - set(REVOKING) <= handled, (service, subscribed - handled)
        assert handled <= subscribed, (service, "handles but never receives", handled - subscribed)

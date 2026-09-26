"""Write every service's OpenAPI document to docs/api/, from the code itself.
`make openapi`. The reference can then never drift from what is deployed."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parents[1] / "docs" / "api"


def main() -> None:
    from payments.main import build_app as payments
    from payments.settings import Settings as PaymentsSettings

    from booking.main import build_app as booking
    from booking.settings import Settings as BookingSettings
    from catalog.main import build_app as catalog
    from catalog.settings import Settings as CatalogSettings
    from matching.main import build_app as matching
    from matching.settings import Settings as MatchingSettings

    OUT.mkdir(parents=True, exist_ok=True)
    for name, app in {
        "catalog": catalog(CatalogSettings(app_env="test")),
        "matching": matching(MatchingSettings(app_env="test")),
        "booking": booking(BookingSettings(app_env="test")),
        "payments": payments(PaymentsSettings(app_env="test")),
    }.items():
        (OUT / f"{name}.json").write_text(json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n")
        print(f"docs/api/{name}.json")


if __name__ == "__main__":
    main()

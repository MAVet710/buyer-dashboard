from __future__ import annotations

from typing import Any

from .metrc_package_actions import MetrcPackageActionError, MetrcPackageActionService


class GovernedMetrcPackageActionService(MetrcPackageActionService):
    """Operator boundary for package writes whose current provider state is provable."""

    def prepare(self, **kwargs: Any) -> dict[str, Any]:
        try:
            prepared = super().prepare(**kwargs)
        except MetrcPackageActionError:
            raise
        except (TypeError, ValueError) as exc:
            raise MetrcPackageActionError(
                "The linked Metrc package identity or reviewed package values are not valid for the promoted write contract."
            ) from exc

        operation = str(prepared.get("operation_type") or "").strip().casefold()
        if operation in {"package_adjust", "package_item"}:
            finished = (prepared.get("expected_provider_state") or {}).get("finished")
            if finished is True:
                raise MetrcPackageActionError(
                    "This Metrc package is finished. Reopen it through the governed package workflow before changing quantity or item."
                )
            if finished is not False:
                raise MetrcPackageActionError(
                    "Fresh Metrc readback cannot prove this package is unfinished, so quantity/item mutation remains blocked."
                )
        return prepared

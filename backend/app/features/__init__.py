"""The feature catalog. Every Feature is registered here explicitly."""

from typing import Any

from app.features import (
    compose_stack,
    docker_container,
    host_power,
    ping_check,
    systemd_service,
    wake_on_lan,
    webhook,
)
from app.features.base import Feature

FEATURES: dict[str, Feature[Any]] = {
    feature.id: feature
    for feature in [
        docker_container.FEATURE,
        compose_stack.FEATURE,
        systemd_service.FEATURE,
        host_power.FEATURE,
        wake_on_lan.FEATURE,
        webhook.FEATURE,
        ping_check.FEATURE,
    ]
}


def get_feature(feature_id: str) -> Feature[Any] | None:
    return FEATURES.get(feature_id)

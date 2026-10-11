"""The feature catalog. Every Feature is registered here explicitly."""

from typing import Any

from app.features import docker_container
from app.features.base import Feature

FEATURES: dict[str, Feature[Any]] = {
    feature.id: feature
    for feature in [
        docker_container.FEATURE,
    ]
}


def get_feature(feature_id: str) -> Feature[Any] | None:
    return FEATURES.get(feature_id)

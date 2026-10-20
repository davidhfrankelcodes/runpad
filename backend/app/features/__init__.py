"""The feature catalog. Every Feature is registered here explicitly."""

from typing import Any

from app.features import (
    apt_updates,
    compose_stack,
    docker_container,
    home_assistant,
    host_power,
    host_resources,
    jenkins_agent,
    jenkins_job,
    libvirt_vm,
    ping_check,
    port_check,
    proxmox_guest,
    restic_backup,
    systemd_service,
    tls_certificate,
    wake_on_lan,
    webhook,
    website_check,
    zfs_pool,
)
from app.features.base import Feature

FEATURES: dict[str, Feature[Any]] = {
    feature.id: feature
    for feature in [
        docker_container.FEATURE,
        compose_stack.FEATURE,
        systemd_service.FEATURE,
        host_power.FEATURE,
        host_resources.FEATURE,
        apt_updates.FEATURE,
        wake_on_lan.FEATURE,
        proxmox_guest.FEATURE,
        libvirt_vm.FEATURE,
        zfs_pool.FEATURE,
        restic_backup.FEATURE,
        home_assistant.FEATURE,
        jenkins_job.FEATURE,
        jenkins_agent.FEATURE,
        webhook.FEATURE,
        ping_check.FEATURE,
        port_check.FEATURE,
        website_check.FEATURE,
        tls_certificate.FEATURE,
    ]
}


def get_feature(feature_id: str) -> Feature[Any] | None:
    return FEATURES.get(feature_id)

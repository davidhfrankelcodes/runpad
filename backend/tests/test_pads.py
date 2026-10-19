import time
from collections.abc import Callable

from fastapi.testclient import TestClient

MEMBER = {"username": "member", "password": "member password 1"}
OTHER = {"username": "other", "password": "other password 12"}


def _user(admin: TestClient, make_client: Callable, credentials: dict) -> tuple[TestClient, str]:
    user_id = admin.post("/api/v1/users", json=credentials).json()["id"]
    browser: TestClient = make_client()
    assert browser.post("/api/v1/auth/login", json=credentials).status_code == 200
    return browser, user_id


def _action(admin: TestClient, script: str = "echo pressed", **extra: object) -> dict:
    body = {"name": "act", "executor": "local", "spec": {"script": script}, **extra}
    response = admin.post("/api/v1/actions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _pad(admin: TestClient, name: str = "Home", member_ids: list[str] | None = None) -> dict:
    response = admin.post("/api/v1/pads", json={"name": name, "member_ids": member_ids or []})
    assert response.status_code == 201, response.text
    return response.json()


def _button(admin: TestClient, pad: dict, action: dict, label: str = "Press") -> dict:
    response = admin.post(
        f"/api/v1/pads/{pad['id']}/buttons", json={"action_id": action["id"], "label": label}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _wait(client: TestClient, run_id: str) -> dict:
    for _ in range(200):
        run = client.get(f"/api/v1/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_admin_builds_a_pad(admin_client: TestClient) -> None:
    pad = _pad(admin_client)
    action = _action(admin_client)
    button = _button(admin_client, pad, action)
    assert button["color"] == "slate"
    detail = admin_client.get(f"/api/v1/pads/{pad['id']}").json()
    assert [b["label"] for b in detail["buttons"]] == ["Press"]
    assert detail["buttons"][0]["action"]["name"] == "act"


def test_pad_detail_never_exposes_the_command(
    admin_client: TestClient, make_client: Callable
) -> None:
    member, member_id = _user(admin_client, make_client, MEMBER)
    secret = admin_client.post(
        "/api/v1/secrets", json={"name": "tok", "kind": "text", "value": "v"}
    ).json()
    action = _action(
        admin_client,
        "echo very-private-script",
        secret_env=[{"name": "TOKEN", "secret_id": secret["id"]}],
    )
    pad = _pad(admin_client, member_ids=[member_id])
    _button(admin_client, pad, action)
    body = member.get(f"/api/v1/pads/{pad['id']}").text
    assert "very-private-script" not in body
    assert secret["id"] not in body
    assert member_id not in body  # Members do not see the pad's member list.


def test_members_see_only_their_pads(admin_client: TestClient, make_client: Callable) -> None:
    member, member_id = _user(admin_client, make_client, MEMBER)
    mine = _pad(admin_client, "Mine", [member_id])
    hidden = _pad(admin_client, "Hidden")
    assert [p["name"] for p in member.get("/api/v1/pads").json()] == ["Mine"]
    assert member.get(f"/api/v1/pads/{mine['id']}").status_code == 200
    assert member.get(f"/api/v1/pads/{hidden['id']}").status_code == 404
    assert [p["name"] for p in admin_client.get("/api/v1/pads").json()] == ["Mine", "Hidden"]


def test_member_runs_action_on_a_visible_pad(
    admin_client: TestClient, make_client: Callable
) -> None:
    member, member_id = _user(admin_client, make_client, MEMBER)
    action = _action(admin_client)
    _button(admin_client, _pad(admin_client, member_ids=[member_id]), action)
    response = member.post(f"/api/v1/actions/{action['id']}/run", json={"args": {}})
    assert response.status_code == 202
    run = _wait(member, response.json()["id"])
    assert (run["status"], run["output"], run["triggered_by"]) == (
        "succeeded",
        "pressed\n",
        "member",
    )
    assert [r["id"] for r in member.get("/api/v1/runs").json()["runs"]] == [run["id"]]


def test_buttons_show_the_latest_run_each_user_can_see(
    admin_client: TestClient, make_client: Callable
) -> None:
    member, member_id = _user(admin_client, make_client, MEMBER)
    action = _action(admin_client, "exit 3")
    other = _action(admin_client)
    pad = _pad(admin_client, member_ids=[member_id])
    _button(admin_client, pad, action)
    _button(admin_client, pad, other, "Never pressed")

    def last_runs(client: TestClient) -> list[dict | None]:
        detail = client.get(f"/api/v1/pads/{pad['id']}").json()
        return [b["last_run"] for b in detail["buttons"]]

    assert last_runs(admin_client) == [None, None]
    first = _wait(member, member.post(f"/api/v1/actions/{action['id']}/run", json={}).json()["id"])
    latest = admin_client.post(f"/api/v1/actions/{action['id']}/run", json={}).json()
    _wait(admin_client, latest["id"])

    # Admins see anyone's latest run; members only their own, as on the Runs page.
    admin_last, admin_other = last_runs(admin_client)
    assert admin_last is not None and admin_other is None
    assert (admin_last["id"], admin_last["status"]) == (latest["id"], "failed")
    assert admin_last["finished_at"] is not None
    member_last, _ = last_runs(member)
    assert member_last is not None
    assert (member_last["id"], member_last["status"]) == (first["id"], "failed")


def test_member_cannot_run_actions_on_other_pads(
    admin_client: TestClient, make_client: Callable
) -> None:
    member, _ = _user(admin_client, make_client, MEMBER)
    _, other_id = _user(admin_client, make_client, OTHER)
    action = _action(admin_client)
    _button(admin_client, _pad(admin_client, member_ids=[other_id]), action)
    unlisted = _action(admin_client)
    for action_id in (action["id"], unlisted["id"], "00000000-0000-0000-0000-000000000000"):
        response = member.post(f"/api/v1/actions/{action_id}/run", json={"args": {}})
        assert response.status_code == 403  # Same answer whether or not the action exists.


def test_removing_member_from_pad_revokes_running(
    admin_client: TestClient, make_client: Callable
) -> None:
    member, member_id = _user(admin_client, make_client, MEMBER)
    action = _action(admin_client)
    pad = _pad(admin_client, member_ids=[member_id])
    _button(admin_client, pad, action)
    admin_client.patch(f"/api/v1/pads/{pad['id']}", json={"member_ids": []})
    assert member.post(f"/api/v1/actions/{action['id']}/run", json={}).status_code == 403
    assert member.get(f"/api/v1/pads/{pad['id']}").status_code == 404


def test_members_cannot_change_pads(admin_client: TestClient, make_client: Callable) -> None:
    member, member_id = _user(admin_client, make_client, MEMBER)
    pad = _pad(admin_client, member_ids=[member_id])
    action = _action(admin_client)
    assert member.post("/api/v1/pads", json={"name": "x"}).status_code == 403
    assert member.patch(f"/api/v1/pads/{pad['id']}", json={"name": "x"}).status_code == 403
    assert member.delete(f"/api/v1/pads/{pad['id']}").status_code == 403
    response = member.post(
        f"/api/v1/pads/{pad['id']}/buttons", json={"action_id": action["id"], "label": "x"}
    )
    assert response.status_code == 403


def test_unknown_member_ids_are_rejected(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/v1/pads",
        json={"name": "x", "member_ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert response.status_code == 400


def test_deleting_action_removes_its_buttons(admin_client: TestClient) -> None:
    pad = _pad(admin_client)
    action = _action(admin_client)
    _button(admin_client, pad, action)
    admin_client.delete(f"/api/v1/actions/{action['id']}")
    assert admin_client.get(f"/api/v1/pads/{pad['id']}").json()["buttons"] == []


def test_deleting_pad_keeps_actions(admin_client: TestClient) -> None:
    pad = _pad(admin_client)
    action = _action(admin_client)
    _button(admin_client, pad, action)
    assert admin_client.delete(f"/api/v1/pads/{pad['id']}").status_code == 204
    assert admin_client.get(f"/api/v1/actions/{action['id']}").status_code == 200


def test_reorder_buttons_and_pads(admin_client: TestClient) -> None:
    pad = _pad(admin_client)
    action = _action(admin_client)
    ids = [_button(admin_client, pad, action, label)["id"] for label in ("a", "b", "c")]
    new_order = [{"kind": "button", "id": i} for i in (ids[2], ids[0], ids[1])]
    response = admin_client.put(f"/api/v1/pads/{pad['id']}/order", json={"items": new_order})
    assert response.status_code == 204
    labels = [b["label"] for b in admin_client.get(f"/api/v1/pads/{pad['id']}").json()["buttons"]]
    assert labels == ["c", "a", "b"]
    bad = admin_client.put(f"/api/v1/pads/{pad['id']}/order", json={"items": new_order[:2]})
    assert bad.status_code == 400

    second = _pad(admin_client, "Second")
    admin_client.put("/api/v1/pads/order", json={"ids": [second["id"], pad["id"]]})
    assert [p["name"] for p in admin_client.get("/api/v1/pads").json()] == ["Second", "Home"]


def test_buttons_and_tiles_share_one_board_order(admin_client: TestClient) -> None:
    pad = _pad(admin_client)
    action = _action(admin_client)
    first = _button(admin_client, pad, action, "first")
    tile = admin_client.post(
        "/api/v1/feature-instances",
        json={
            "feature_id": "ping_check",
            "item": "ping",
            "config": {"host": "db"},
            "pad_id": pad["id"],
        },
    ).json()
    last = _button(admin_client, pad, action, "last")
    detail = admin_client.get(f"/api/v1/pads/{pad['id']}").json()
    [placed] = detail["tiles"]
    # New items go after everything already on the board, whatever their kind.
    assert [first["position"], placed["position"], last["position"]] == [0, 1, 2]
    assert placed["feature_instance_id"] == tile["id"]

    # Any order of buttons and tiles, mixed.
    order = [
        {"kind": "button", "id": last["id"]},
        {"kind": "tile", "id": placed["id"]},
        {"kind": "button", "id": first["id"]},
    ]
    assert (
        admin_client.put(f"/api/v1/pads/{pad['id']}/order", json={"items": order}).status_code
        == 204
    )
    detail = admin_client.get(f"/api/v1/pads/{pad['id']}").json()
    positions = {b["label"]: b["position"] for b in detail["buttons"]}
    assert (positions["last"], detail["tiles"][0]["position"], positions["first"]) == (0, 1, 2)

    # The order must name each item on the pad once, with its right kind.
    wrong_kind = [{**item, "kind": "button"} for item in order]
    response = admin_client.put(f"/api/v1/pads/{pad['id']}/order", json={"items": wrong_kind})
    assert response.status_code == 400
    twice = [*order, order[0]]
    assert (
        admin_client.put(f"/api/v1/pads/{pad['id']}/order", json={"items": twice}).status_code
        == 400
    )


def test_moving_a_button_to_another_pad_puts_it_last_on_its_board(
    admin_client: TestClient,
) -> None:
    home, other = _pad(admin_client), _pad(admin_client, "Other")
    action = _action(admin_client)
    admin_client.post(
        "/api/v1/feature-instances",
        json={
            "feature_id": "ping_check",
            "item": "ping",
            "config": {"host": "db"},
            "pad_id": other["id"],
        },
    )
    button = _button(admin_client, home, action)
    moved = admin_client.patch(f"/api/v1/buttons/{button['id']}", json={"pad_id": other["id"]})
    assert moved.json()["position"] == 1  # After the tile already there.


def test_update_and_delete_button(admin_client: TestClient) -> None:
    pad = _pad(admin_client)
    button = _button(admin_client, pad, _action(admin_client))
    updated = admin_client.patch(
        f"/api/v1/buttons/{button['id']}", json={"label": "Renamed", "color": "red"}
    ).json()
    assert (updated["label"], updated["color"]) == ("Renamed", "red")
    assert admin_client.delete(f"/api/v1/buttons/{button['id']}").status_code == 204
    assert admin_client.get(f"/api/v1/pads/{pad['id']}").json()["buttons"] == []

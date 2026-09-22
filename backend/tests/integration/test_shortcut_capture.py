# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import importlib.util
import plistlib
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "shortcuts/clipo-save.unsigned.shortcut"


def decode_text(value: dict[str, Any], variables: dict[str, str]) -> str:
    value = value["Value"]
    result = value["string"]
    for attachment in value["attachmentsByRange"].values():
        key = attachment.get("VariableName", attachment.get("OutputUUID"))
        result = result.replace("\ufffc", variables[key], 1)
    return result


def decode_dictionary(value: dict[str, Any], variables: dict[str, str]) -> dict[str, str]:
    return {
        decode_text(item["WFKey"], variables): decode_text(item["WFValue"], variables)
        for item in value["Value"]["WFDictionaryFieldValueItems"]
    }


def test_shortcut_template_request_works_with_api_token_and_reports_errors(
    client: TestClient, auth: dict
) -> None:
    workflow = plistlib.loads(TEMPLATE.read_bytes())
    actions = workflow["WFWorkflowActions"]
    request = next(
        action["WFWorkflowActionParameters"]
        for action in reversed(actions)
        if action["WFWorkflowActionIdentifier"].endswith(".downloadurl")
    )
    selected = next(
        action["WFWorkflowActionParameters"]["UUID"]
        for action in actions
        if action["WFWorkflowActionIdentifier"].endswith(".getitemfromlist")
    )
    token = client.post("/api/v1/tokens", headers=auth, json={"name": "iPhone Shortcut"}).json()
    variables = {
        "Clipo 服务器": "",
        "Clipo Token": token["token"],
        selected: "https://example.com/shortcut",
    }
    path = decode_text(request["WFURL"], variables)
    headers = decode_dictionary(request["WFHTTPHeaders"], variables)
    body = decode_dictionary(request["WFJSONValues"], variables)
    response = client.request(request["WFHTTPMethod"], path, headers=headers, json=body)
    assert response.status_code == 202 and response.json()["job_id"].startswith("j_")
    assert response.json()["url"] == variables[selected]
    invalid = client.post(path, headers=headers, json={"url": "https://127.0.0.1/private"})
    assert invalid.status_code == 422 and invalid.json()["error"]["message"]
    client.delete(f"/api/v1/tokens/{token['id']}", headers=auth)
    denied = client.post(path, headers=headers, json=body)
    assert denied.status_code == 401 and denied.json()["error"]["message"]
    assert token["token"] not in TEMPLATE.read_text()


def test_shortcut_artifact_matches_reproducible_generator() -> None:
    spec = importlib.util.spec_from_file_location(
        "generate_shortcut", ROOT / "scripts/generate_shortcut.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    generated = plistlib.dumps(module.build_shortcut(), fmt=plistlib.FMT_XML, sort_keys=False)
    assert generated == TEMPLATE.read_bytes()


def test_downloaded_template_claims_configuration_using_its_actual_request_fields(
    client: TestClient, auth: dict
) -> None:
    response = client.get("/api/v1/shortcuts/template")
    assert response.status_code == 200
    assert response.content == TEMPLATE.read_bytes()
    workflow = plistlib.loads(response.content)
    actions = workflow["WFWorkflowActions"]
    pairing = client.post(
        "/api/v1/shortcuts/pairings",
        headers=auth,
        json={"name": "模板测试", "server_url": "https://clipo.example.com"},
    ).json()
    import json

    payload = json.loads(pairing["setup_input"].removeprefix("clipo-setup:"))
    fields = {
        action["WFWorkflowActionParameters"].get("WFDictionaryKey"): action[
            "WFWorkflowActionParameters"
        ]["UUID"]
        for action in actions[
            : next(
                i
                for i, action in enumerate(actions)
                if action["WFWorkflowActionIdentifier"].endswith(".downloadurl")
            )
        ]
        if action["WFWorkflowActionIdentifier"].endswith(".getvalueforkey")
    }
    variables = {fields["server_url"]: "", fields["code"]: payload["code"]}
    request = next(
        action["WFWorkflowActionParameters"]
        for action in actions
        if action["WFWorkflowActionIdentifier"].endswith(".downloadurl")
    )
    claimed = client.request(
        request["WFHTTPMethod"],
        decode_text(request["WFURL"], variables),
        json=decode_dictionary(request["WFJSONValues"], variables),
    )
    assert claimed.status_code == 200
    config = claimed.json()
    assert config["server_url"] == payload["server_url"]
    assert (
        client.get("/api/v1/auth/me", headers={"X-Clipo-Token": config["token"]}).status_code == 200
    )
    assert payload["code"].encode() not in response.content
    assert config["token"].encode() not in response.content
    assert b"ct_" not in response.content
    # Public artifact has no personal import defaults; credentials are only obtained at runtime.
    assert workflow["WFWorkflowImportQuestions"] == []
    assert any(action["WFWorkflowActionIdentifier"].endswith(".getclipboard") for action in actions)
    saved = next(
        action["WFWorkflowActionParameters"]
        for action in actions
        if action["WFWorkflowActionIdentifier"].endswith(".documentpicker.save")
    )
    loaded = next(
        action["WFWorkflowActionParameters"]
        for action in actions
        if action["WFWorkflowActionIdentifier"].endswith(".getfile")
    )
    assert saved["WFFileDestinationPath"] == loaded["WFGetFilePath"] == "Clipo.json"

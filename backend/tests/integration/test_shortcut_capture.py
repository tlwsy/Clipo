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
        for action in actions
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

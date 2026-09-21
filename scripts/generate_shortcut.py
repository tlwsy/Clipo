"""Generate the unsigned, credential-free Clipo Shortcut for signing on macOS."""

import plistlib
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]


def token(value: dict[str, Any]) -> dict[str, Any]:
    return {"Value": value, "WFSerializationType": "WFTextTokenAttachment"}


def output(identifier: str) -> dict[str, Any]:
    return token({"Type": "ActionOutput", "OutputUUID": identifier, "OutputName": "结果"})


def variable(name: str) -> dict[str, Any]:
    return token({"Type": "Variable", "VariableName": name})


def text_value(value: str) -> dict[str, Any]:
    return {
        "Value": {"string": value, "attachmentsByRange": {}},
        "WFSerializationType": "WFTextTokenString",
    }


def template(prefix: str, value: dict[str, Any], suffix: str = "") -> dict[str, Any]:
    return {
        "WFSerializationType": "WFTextTokenString",
        "Value": {
            "string": prefix + "\ufffc" + suffix,
            "attachmentsByRange": {
                f"{{{len(prefix.encode('utf-16-le')) // 2}, 1}}": value["Value"]
            },
        },
    }


def dictionary(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "WFSerializationType": "WFDictionaryFieldValue",
        "Value": {
            "WFDictionaryFieldValueItems": [
                {"WFItemType": 0, "WFKey": text_value(key), "WFValue": value}
                for key, value in values.items()
            ]
        },
    }


def build_shortcut() -> dict[str, Any]:
    actions: list[dict[str, Any]] = []

    def action(name: str, **params: Any) -> str:
        identifier = str(uuid5(NAMESPACE_URL, f"clipo/shortcut/v1/{len(actions)}")).upper()
        actions.append(
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions." + name,
                "WFWorkflowActionParameters": {"UUID": identifier, **params},
            }
        )
        return identifier

    base = action("gettext", WFTextActionText="https://clipo.example.com")
    action("setvariable", WFVariableName="Clipo 服务器", WFInput=output(base))
    api_token = action("gettext", WFTextActionText="ct_REPLACE_IN_SHORTCUTS")
    action("setvariable", WFVariableName="Clipo Token", WFInput=output(api_token))
    urls = action("detect.link", WFInput=token({"Type": "ExtensionInput"}))
    link = action("getitemfromlist", WFInput=output(urls), WFItemSpecifier="First Item")
    group = str(uuid5(NAMESPACE_URL, "clipo/shortcut/link-condition"))
    action(
        "conditional",
        WFControlFlowMode=0,
        GroupingIdentifier=group,
        WFInput=output(link),
        WFCondition=100,
    )
    request = action(
        "downloadurl",
        WFURL=template("", variable("Clipo 服务器"), "/api/v1/captures"),
        WFHTTPMethod="POST",
        WFHTTPBodyType="JSON",
        WFHTTPHeaders=dictionary({"X-Clipo-Token": template("", variable("Clipo Token"))}),
        WFJSONValues=dictionary({"url": template("", output(link))}),
    )
    job_id = action("getvalueforkey", WFInput=output(request), WFDictionaryKey="job_id")
    result_group = str(uuid5(NAMESPACE_URL, "clipo/shortcut/result-condition"))
    action(
        "conditional",
        WFControlFlowMode=0,
        GroupingIdentifier=result_group,
        WFInput=output(job_id),
        WFCondition=100,
    )
    action(
        "notification",
        WFNotificationActionTitle="Clipo",
        WFNotificationActionBody="已加入保存队列，正文和摘要将在后台处理。",
        WFNotificationActionSound=False,
    )
    action("conditional", WFControlFlowMode=1, GroupingIdentifier=result_group)
    error = action("getvalueforkey", WFInput=output(request), WFDictionaryKey="error")
    message = action("getvalueforkey", WFInput=output(error), WFDictionaryKey="message")
    action(
        "notification",
        WFNotificationActionTitle="Clipo 保存失败",
        WFNotificationActionBody=template("原因：", output(message)),
        WFNotificationActionSound=False,
    )
    action(
        "alert",
        WFAlertActionTitle="Clipo 保存失败",
        WFAlertActionMessage=template(
            "", output(message), "\n点按完成打开 Clipo 检查登录、Token 或保存队列。"
        ),
        WFAlertActionCancelButtonShown=True,
    )
    action("openurl", WFInput=template("", variable("Clipo 服务器"), "/jobs/"))
    action("conditional", WFControlFlowMode=2, GroupingIdentifier=result_group)
    action("conditional", WFControlFlowMode=1, GroupingIdentifier=group)
    action(
        "notification",
        WFNotificationActionTitle="Clipo 未收到链接",
        WFNotificationActionBody="请在网页的分享面板中选择“保存到 Clipo”。",
        WFNotificationActionSound=False,
    )
    action("conditional", WFControlFlowMode=2, GroupingIdentifier=group)
    return {
        "WFWorkflowName": "保存到 Clipo",
        "WFWorkflowClientVersion": "3036.0.4.2",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {
            "WFWorkflowIconStartColor": 431817727,
            "WFWorkflowIconGlyphNumber": 59511,
        },
        "WFWorkflowTypes": ["ActionExtension"],
        "WFWorkflowInputContentItemClasses": [
            "WFURLContentItem",
            "WFStringContentItem",
            "WFSafariWebPageContentItem",
        ],
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowImportQuestions": [
            {
                "ActionIndex": 0,
                "Category": "Parameter",
                "ParameterKey": "WFTextActionText",
                "Text": "Clipo 的 HTTPS 地址，末尾不要斜杠",
                "DefaultValue": "https://clipo.example.com",
            },
            {
                "ActionIndex": 2,
                "Category": "Parameter",
                "ParameterKey": "WFTextActionText",
                "Text": "在 Clipo 设置中创建的独立 API Token",
                "DefaultValue": "ct_REPLACE_IN_SHORTCUTS",
            },
        ],
        "WFWorkflowActions": actions,
    }


def main() -> None:
    destination = ROOT / "shortcuts/clipo-save.unsigned.shortcut"
    destination.write_bytes(plistlib.dumps(build_shortcut(), fmt=plistlib.FMT_XML, sort_keys=False))
    print(f"已生成未签名模板：{destination.relative_to(ROOT)}（不包含真实凭据）")


if __name__ == "__main__":
    main()

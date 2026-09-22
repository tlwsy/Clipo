# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Credential-free Shortcut protocol v1; Apple action execution needs device acceptance."""

from typing import Any
from uuid import NAMESPACE_URL, uuid5


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
        identifier = str(uuid5(NAMESPACE_URL, f"clipo/shortcut/pairing-v1/{len(actions)}")).upper()
        actions.append(
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions." + name,
                "WFWorkflowActionParameters": {"UUID": identifier, **params},
            }
        )
        return identifier

    def begin(value: dict[str, Any]) -> str:
        group = str(uuid5(NAMESPACE_URL, f"clipo/shortcut/condition/{len(actions)}"))
        action(
            "conditional",
            WFControlFlowMode=0,
            GroupingIdentifier=group,
            WFInput=value,
            WFCondition=100,
        )
        return group

    def otherwise(group: str) -> None:
        action("conditional", WFControlFlowMode=1, GroupingIdentifier=group)

    def end(group: str) -> None:
        action("conditional", WFControlFlowMode=2, GroupingIdentifier=group)

    def notify(message: str) -> None:
        action(
            "notification",
            WFNotificationActionTitle="Clipo",
            WFNotificationActionBody=message,
            WFNotificationActionSound=False,
        )

    def stop() -> None:
        action("exit")

    def field(source: str, key: str) -> str:
        return action("getvalueforkey", WFInput=output(source), WFDictionaryKey=key)

    action(
        "comment",
        WFCommentActionText=(
            "Clipo 自动配置版 v1。先在 Clipo 设置中配置此设备；日常接收分享或读取剪贴板。"
            "凭据仅保存在运行时的 Shortcuts/Clipo.json，不写入模板。"
        ),
    )
    incoming = token({"Type": "ExtensionInput"})
    provided = begin(incoming)
    action("setvariable", WFVariableName="Clipo 输入", WFInput=incoming)
    otherwise(provided)
    clipboard = action("getclipboard")
    action("setvariable", WFVariableName="Clipo 输入", WFInput=output(clipboard))
    end(provided)
    input_text = action("gettext", WFTextActionText=template("", variable("Clipo 输入")))
    marker = action(
        "text.match",
        WFMatchTextPattern="^clipo-setup:",
        WFTextMatchCaseSensitive=True,
        WFInput=output(input_text),
    )
    configure = begin(output(marker))
    stripped = action(
        "text.replace",
        WFReplaceTextFind="^clipo-setup:",
        WFReplaceTextReplace="",
        WFReplaceTextRegularExpression=True,
        WFInput=output(input_text),
    )
    setup = action("getdictionaryfrominput", WFInput=output(stripped))
    server = field(setup, "server_url")
    code = field(setup, "code")
    action(
        "alert",
        WFAlertActionTitle="连接 Clipo",
        WFAlertActionMessage=template(
            "将此设备连接到：", output(server), "。继续会替换已保存的 Clipo 配置。"
        ),
        WFAlertActionCancelButtonShown=True,
    )
    response = action(
        "downloadurl",
        WFURL=template("", output(server), "/api/v1/shortcuts/pairings/consume"),
        WFHTTPMethod="POST",
        WFHTTPBodyType="JSON",
        WFJSONValues=dictionary({"code": template("", output(code))}),
    )
    credential = field(response, "token")
    valid = begin(output(credential))
    serialized = action("gettext", WFTextActionText=template("", output(response)))
    action(
        "documentpicker.save",
        WFInput=output(serialized),
        WFFileStorageService="iCloud Drive",
        WFAskWhereToSave=False,
        WFFileDestinationPath="Clipo.json",
        WFSaveFileOverwrite=True,
    )
    notify("Clipo 配置已保存。复制帖子链接后运行此指令即可保存。")
    otherwise(valid)
    error = field(response, "error")
    message = field(error, "message")
    action(
        "alert",
        WFAlertActionTitle="Clipo 配置失败",
        WFAlertActionMessage=template("", output(message), " 请回到 Clipo 重新配置设备。"),
        WFAlertActionCancelButtonShown=False,
    )
    end(valid)
    stop()
    end(configure)

    urls = action("detect.link", WFInput=variable("Clipo 输入"))
    has_urls = begin(output(urls))
    otherwise(has_urls)
    notify("未找到链接。请先在小红书、小黑盒或浏览器中复制帖子链接，再运行此指令。")
    stop()
    end(has_urls)
    link = action("getitemfromlist", WFInput=output(urls), WFItemSpecifier="First Item")
    stored = action(
        "getfile",
        WFFileStorageService="iCloud Drive",
        WFShowFilePicker=False,
        WFGetFilePath="Clipo.json",
        WFFileErrorIfNotFound=False,
    )
    exists = begin(output(stored))
    otherwise(exists)
    notify("尚未配置 Clipo。请打开 Clipo 设置，选择“配置此设备”。")
    stop()
    end(exists)
    config = action("getdictionaryfrominput", WFInput=output(stored))
    saved_server = field(config, "server_url")
    saved_token = field(config, "token")
    action("setvariable", WFVariableName="Clipo 服务器", WFInput=output(saved_server))
    action("setvariable", WFVariableName="Clipo Token", WFInput=output(saved_token))
    configured = begin(output(saved_token))
    otherwise(configured)
    notify("Clipo 配置缺少 Token，请在设置中重新配置此设备。")
    stop()
    end(configured)
    result = action(
        "downloadurl",
        WFURL=template("", variable("Clipo 服务器"), "/api/v1/captures"),
        WFHTTPMethod="POST",
        WFHTTPBodyType="JSON",
        WFHTTPHeaders=dictionary({"X-Clipo-Token": template("", variable("Clipo Token"))}),
        WFJSONValues=dictionary({"url": template("", output(link))}),
    )
    job_id = field(result, "job_id")
    accepted = begin(output(job_id))
    notify("已加入保存队列，正文和摘要将在后台处理。")
    otherwise(accepted)
    capture_error = field(result, "error")
    capture_message = field(capture_error, "message")
    action(
        "alert",
        WFAlertActionTitle="Clipo 保存失败",
        WFAlertActionMessage=template(
            "", output(capture_message), "。继续可打开保存队列；Token 失效时请在设置中重新配置。"
        ),
        WFAlertActionCancelButtonShown=True,
    )
    action("openurl", WFInput=template("", variable("Clipo 服务器"), "/jobs/"))
    end(accepted)
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
        "WFWorkflowHasShortcutInputVariables": True,
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowImportQuestions": [],
        "WFWorkflowActions": actions,
    }

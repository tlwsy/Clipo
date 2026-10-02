// SPDX-License-Identifier: AGPL-3.0-or-later
import type { ExportOptions as Options } from "@/lib/note-export";

export function ExportOptions({
  options,
  onChange,
  disabled = false,
}: {
  options: Options;
  onChange: (options: Options) => void;
  disabled?: boolean;
}) {
  const labels: [keyof Options, string][] = [
    ["include_summary", "包含 AI 摘要"],
    ["include_comments", "包含有价值评论"],
    ["include_annotations", "包含私人标注"],
  ];
  return (
    <fieldset className="export-options" disabled={disabled}>
      <legend>导出内容</legend>
      {labels.map(([key, label]) => (
        <label key={key}>
          <input
            type="checkbox"
            checked={options[key]}
            onChange={(event) =>
              onChange({ ...options, [key]: event.target.checked })
            }
          />
          {label}
        </label>
      ))}
    </fieldset>
  );
}

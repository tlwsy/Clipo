# SPDX-License-Identifier: AGPL-3.0-or-later
from pydantic import BaseModel, ConfigDict, Field


class ExportOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include_summary: bool = Field(default=True, description="包含 AI 摘要和要点")
    include_comments: bool = Field(default=True, description="仅包含标记为有价值的评论")
    include_annotations: bool = Field(default=True, description="包含私人高亮和批注列表")

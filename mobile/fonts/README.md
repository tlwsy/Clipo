# 离线阅读字体

两端共用 `ClipoReadingSans.ttf`（思源黑体 / Noto Sans SC）和 `ClipoReadingSerif.ttf`（思源宋体 / Noto Serif SC）可变字体子集，保留 400/500/600/700 字重。包含 GB2312、扩展拉丁与常用标点，共 7681 个字符；子集外字符与 emoji 由系统字体回退。修改后字体已改名为 Clipo Reading Sans / Serif。

来源为 Google Fonts 的 [Noto Sans SC](https://github.com/google/fonts/tree/main/ofl/notosanssc) 和 [Noto Serif SC](https://github.com/google/fonts/tree/main/ofl/notoserifsc)，随附原始 SIL Open Font License 1.1。2026-11-04 下载的原始文件 SHA-256：

- NotoSansSC.ttf：`a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da`
- NotoSerifSC.ttf：`050080d9255a86808f2945bffac582b31ef32bc36411ce29563b4961670c66f9`

重建时将官方 `NotoSansSC[wght].ttf`、`NotoSerifSC[wght].ttf` 分别保存为上述文件名，许可证分别保存为 `OFL-Sans.txt`、`OFL-Serif.txt`，核对哈希后在仓库根目录运行：

```bash
uv run --no-project --with fonttools==4.60.1 python scripts/subset_mobile_fonts.py /path/to/originals mobile/fonts
```

App 不下载在线字体；网页 `online` 字体名称含 Serif / 宋体时映射到内置宋体，其余映射到内置黑体。原始网页字体元数据仍在样式中保留。

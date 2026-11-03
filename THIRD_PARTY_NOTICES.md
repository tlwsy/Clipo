# 第三方许可

## ParseHub

`backend/app/extractors/heybox_sign.py` 的小黑盒签名算法参考 ParseHub（commit `5cff7e8d9e14fa464599dc9a5e6c966ec5526c3e`），保留其 MIT 许可：

```text
MIT License

Copyright (c) 2024 梓澪

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## xhshow

依赖 `xhshow==0.2.0` 使用 MIT 许可，安装包附带许可文本。来源：https://github.com/Cloxl/xhshow 。

## pgvector

数据库镜像编译 pgvector 0.8.2，使用 PostgreSQL License，源码来自 https://github.com/pgvector/pgvector 。镜像内保留完整许可于 `/usr/local/share/doc/pgvector/LICENSE`，构建固定版本并校验下载源码的 SHA-256。

Python 依赖 `pgvector` 使用 MIT 许可，依赖的 NumPy 使用 BSD-3-Clause 许可；各安装包附带许可及其所捆绑组件的声明，版本固定在 `backend/requirements.lock`。

## Material Color Utilities

前端莫奈取色使用 `@material/material-color-utilities@0.3.0`（Google，Apache-2.0）。来源：https://github.com/material-foundation/material-color-utilities 。完整许可随静态站点分发于 `frontend/public/licenses/material-color-utilities.txt`（站点路径 `/licenses/material-color-utilities.txt`）。

## Fontsource 在线字体

在线目录来自 https://api.fontsource.org ，用户选择的字体由 jsDelivr 上的 Fontsource 包按固定版本加载；仓库不捆绑这些字体文件。字体各自的许可及来源可在 https://fontsource.org/fonts 查看，下载包中也包含许可。用户配置仅保存字体元数据，不接受自定义 CSS 或资源地址。

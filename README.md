# Whole-House Customization 报价系统
## 报价系统 · 开源版

An English-first, Chinese-assisted local quotation application for whole-house
custom furniture. Python backend, browser-based desktop interface, SQLite data,
Excel/PDF/print exports. Released under the **MIT License**.

**Current source release / 当前源码版本：3.0.2**

英文为主、中文为辅的本机全屋定制报价系统。支持柜体、柜门、橱柜、护墙板、灯带及五金增项，
本机保存业务数据，生成带尺寸示意图的 Excel、PDF 和打印报价。**MIT 开源，允许修改和商用。**

## Quick start / 快速启动

**Windows 10/11 (64-bit), Python 3.11 or newer.**

1. Download the source ZIP from GitHub and fully extract it. / 下载源码 ZIP 并完整解压。
2. Install Python from [python.org](https://www.python.org/downloads/windows/).
   / 安装 Python，勾选添加到 PATH。
3. Double-click **Setup.cmd** once. It creates `.venv` and installs the pinned dependencies.
   / 首次双击 **Setup.cmd**，创建独立环境并安装依赖，需要联网。
4. Double-click **Start.cmd**. / 双击 **Start.cmd** 启动。

The app opens an Edge/Chrome app window, or your default browser. It listens on
`127.0.0.1` only, starting at port `8878` and trying the next free port if occupied.
PDF output requires a locally installed Edge or Chrome. Image OCR requires
Windows OCR language support. Normal operation and calculations are local.

默认本机端口 `8878`，占用时自动顺延；优先打开 Edge/Chrome 独立窗口。
PDF 导出需要本机 Edge 或 Chrome，图片文字识别需要 Windows OCR 语言支持。
安装依赖后，报价和计价可离线使用。这是**源码版，不含便携 Python 环境或预编译 EXE**。

### Command line / 命令行

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

For headless startup: `python app.py --no-browser --port 8878`.

## Features / 功能

- Customer/project quotations, floors, rooms, custom cabinet names and L/H/D.
  / 客户项目、楼层区域、柜型名称及长高深录入。
- Area, linear-foot and quantity pricing; optional doors; minimum-height,
  depth and non-standard rules. / 面积、长度、数量计价，柜门拆分、最低计价高、超深与非标规则。
- LED, power supplies, sensors, glass doors, quartz, sinks and baskets.
  / 灯带、电源、感应器、玻璃门、台面、水槽与拉篮。
- Editable categories and materials (add, edit, remove/disable); saved ordering for
  categories, floors, rooms, materials, doors and add-ons flows into quotation choices.
  / 品类、材料可新增、修改、移除或停用；品类、楼层、区域、材料、柜门及增项排序会同步到报价选项。
- Numbered repeated room instances (for example Bedroom 1 / Bedroom 2), with bilingual
  labels; quick-entry material and add-on choices are remembered per quotation and reset
  for a new quotation. / 支持卧室1、卧室2等重复区域及双语名称；快速录入会按报价记住材料与增项，新建报价后重置。
- Autosave, duplicate/edit, locked-price snapshots, backup and restore.
  / 自动保存、复制编辑、锁价快照、备份与恢复。
- English/Chinese customer and internal Excel/PDF/print output, embedded
  dimension drawings and Excel formulas. / 双语客户版与内部版导出、内嵌尺寸图及 Excel 公式。
- Local image/PDF/ASCII-DXF dimension-assisted entry; extracted dimensions
  require review, not automatic room/cabinet design interpretation.
  / 本机图纸尺寸辅助录入，识别结果需人工核对，不是全自动拆单或设计识别。
- Paste a copied drawing image with Ctrl+V in the drawing dialog.
  / 在图纸识别窗口按 Ctrl+V 粘贴剪贴板中的图片。

## Demo data and business data / 演示与业务数据

**No price list, costs, company identity, contact details, logo or commercial
terms are bundled.** All material, add-on and lighting amounts start at zero.
Fill your own private prices, company information and terms under **Manage**.

**开源包不含价格表、成本资料、公司信息、联系方式、Logo 或商业条款。**
材料、柜门、增项和灯带价格均从零开始；使用前在“管理”中填写自己的资料。
计价、公司管理与导出功能保留。自动化测试只在内存中构造简单数值，不提供业务价格表。

On first launch the app creates `data/pricing.json` from the public seed
`data/factory-pricing.json`, then creates `data/app.db`. Generated documents go
to `exports/`. These files, uploads, config history and backups are ignored by Git.
This repository includes no customer databases, old quotations, uploaded drawings,
private contacts, credentials or bundled third-party runtimes.

首次启动自动生成 `data/pricing.json` 与 `data/app.db`；导出存入 `exports/`。
业务库、活动价格、上传资料、配置历史和备份均被 Git 忽略。开源整理不修改原应用的业务数据。

Optional environment variables: `WHOLE_HOUSE_CUSTOMIZATION_DATA_DIR`, `WHOLE_HOUSE_CUSTOMIZATION_EXPORT_DIR` and
`WHOLE_HOUSE_CUSTOMIZATION_NO_BROWSER=1`. Each application copy should use its own data directory.

## Tests / 测试

After setup, double-click **Run-tests.cmd**, or run:

```powershell
.venv\Scripts\python.exe tools\run_tests.py
```

Each test module runs in a separate process with temporary business data.
Coverage includes hand-calculated temporary test inputs, depth/minimum-height rules,
discount/deposit, persisted configuration, locked-price snapshots, bilingual
LED/add-on remarks, customer data separation, drawings and Excel formula caches.
GitHub Actions also runs the suite on Windows with Python 3.12 and 3.13.

测试使用临时业务目录，覆盖自填价格后的计价、超深、最低计价高、折扣定金、配置持久化、锁价、
双语增项备注、客户版不含成本毛利、示意图与公式缓存。界面和导出主打 Windows。
其他操作系统未作为桌面版验收目标。

## Before publishing / 每次发布前

```powershell
python tools/public_data.py --clean
python tools/public_data.py
python tools/run_tests.py
```

The cleaner only edits this public checkout's seed and example JSON, never your
active business database or `data/pricing.json`. CI rejects non-blank public defaults.

清理工具只处理开源目录的初始配置与示例，不修改正在使用的数据库和活动价格配置。
公开源码与 ZIP 不纳入业务库、活动价格、公司 Logo、上传文件、业务导出或备份。

## Source / 源码

- `core/`: pricing engine and configuration / 计价引擎与配置。
- `server/`: local API, SQLite storage, backup and drawing entry / 本机接口与业务存储。
- `web/`: desktop-style bilingual interface / 双语界面。
- `export/`: Excel, PDF, printing and cabinet diagrams / 导出与柜体示意图。
- `templates/`: blank layout geometry only / 不含原业务内容的空白版式基准。
- `tests/`, `tools/`: isolated regression tests / 隔离回归测试。
- `launcher/`: optional Windows launcher source / 可选 Windows 启动器源码。

## License / 许可证

[MIT](LICENSE). Python and third-party packages retain their own upstream licenses;
dependencies are installed separately and are not redistributed in this source repository.

项目源码按 MIT 许可证发布；Python 与各依赖保留各自许可证，本仓库不捆绑分发其运行环境。
See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute. / 参与开发请参阅贡献说明。

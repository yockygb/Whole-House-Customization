# Changelog / 更新记录

## 3.0.2 — 2026-10-23

- Ported quotation workflow improvements while retaining the independent v3 codebase: dropdown category selection, repeated numbered rooms, per-quotation quick-entry memory, and Ctrl+V drawing-image paste.
- Added persistent ordering for categories, floors, rooms, materials, door finishes and add-ons; ordering is reflected in the quote form.
- Exposed category and material add/edit/remove controls while retaining historical quotation data when entries are removed.
- 保留独立版 v3 架构并移植录单改进：品类下拉选择、重复编号区域、按报价记忆快速录入，以及图纸窗口 Ctrl+V 粘贴图片。
- 新增品类、楼层、区域、材料、柜门和增项的持久排序，并同步到报价页面。
- 完善品类与材料新增、编辑、移除/停用管理；移除时保留历史报价数据。

## 3.0.1 — 2026-10-21

- Removed bundled prices, costs, company information, logos and commercial terms.
- 移除内置价格、成本、公司信息、Logo 与商业条款；所有金额从零开始，保留自填与计价功能。
- Added a release data cleaner and CI checks. / 新增发布前清理和持续集成检查。

## 3.0.0 — 2026-10-21

- Published as **Whole-House Customization 报价系统** with matching UI, namespaces and source package.

- Initial public source release under the MIT license. / 首次以 MIT 许可证公开源码。
- Independent local database and editable catalogue/rules. / 独立本机数据库、可编辑目录与规则。
- English/Chinese UI, Excel, PDF and print exports. / 英中文界面及 Excel、PDF、打印导出。
- Independent configuration and blank reference layout. / 独立配置和空白版式基准。
- Windows source launchers, isolated tests and GitHub Actions. / Windows 源码启动脚本、隔离测试与持续集成。

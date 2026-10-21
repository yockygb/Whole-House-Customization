# Contributing / 参与开发

1. Fork the repository and create a focused branch. / Fork 仓库并新建功能分支。
2. Install Python 3.11+ and `requirements.txt`. / 安装 Python 3.11+ 与依赖。
3. Run `python tools/run_tests.py`. / 运行自动化测试。
4. Submit a pull request describing the change and test result. / 提交 PR，说明改动与测试结果。

Keep English-first and Chinese-second UI/export wording consistent. Preserve
quotation formulas, dimensions and historical locked-price snapshots. Add a
regression test for calculation changes. Keep bundled prices and company information blank; use temporary numeric inputs in tests.

界面与导出统一英文优先、中文辅助；修改计价时补充回归测试，保留公式、尺寸和历史锁价快照。
示例不含价格及公司资料；发布前运行 tools/public_data.py，不提交客户库、报价导出、公司联系方式、供应商配置或凭据。

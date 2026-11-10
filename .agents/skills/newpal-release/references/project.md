# 项目入口

工作区`补丁工作仓库/当前状态.json`、`GitHub维护/当前公开准备进度.md`为现行本地入口。公开克隆通常在`GitHub公开候选/v0.3.0-preview/repository`；实际版本读baseline.json/tool-baseline.json和Git，远端授权实时核对。

- `tools/build_current.py`是冻结差分，`build_updated_from_source.py`仅覆盖所列阶段；相同目标不重复重建。
- 历史`tools/pack_release.py`默认会做玩家包，工具单独更新不要顺带重打游戏；用明确ZIP成员清单。
- `tools/freeze_release.py`只在公开树变化后固定一次。prepare/assemble/finalize_github_v03是首次整理脚本，不重跑覆盖首页。
- `tools/build_map_tester.py`复用内嵌预览，接口离线/隐藏检查证据在map-test-compat-v2；真实连接另记，由用户操作。
- 本地`脚本/audit_publication_privacy_v1.py`仅文本规则初筛，原生/内嵌代码及图元数据另查；报告放公开树外。

# 证据与包复用小脚本

Python标准库；清单在私有候选目录，不含凭据，文件相对--root。脚本只登记实际完成的检查，不自动证明通过。

检查计划：
```json
{"checks":[{"id":"interface","method":"interface-v2","files":["scripts/matcher.py","data/rules.json"],"method_files":["tests/check.py"]}]}
```
```powershell
python scripts/release_once.py status --root "候选目录" --plan "检查计划.json" --ledger "私有回执.json"
python scripts/release_once.py record --root "候选目录" --plan "检查计划.json" --ledger "私有回执.json" --check interface --result pass --evidence "真实报告.json"
```
reusable表示旧证据依然适用，不是新执行。内容/方法/依赖/证据改变会失效；功能与隐私范围分别列项。

包清单：
```json
{"version":"tool-preview","entries":[{"source":"dist/tool.exe","name":"NewPAL_MapTester/新仙剑地图传送器.exe"},{"source":"docs/工具说明.md","name":"NewPAL_MapTester/工具说明.md"}]}
```
```powershell
python scripts/release_once.py pack --root "候选目录" --manifest "包清单.json" --output "分享包.zip" --receipt "私有包回执.json"
```
相同内容/打包方法/ZIP哈希命中则复用；已有不同输出拒绝覆盖，使用新候选/版本。新包只做一次成员、内容和CRC核对并记总SHA256，随后本地复制与GitHub上传复用此包。回执不代表功能或隐私通过。上传后另记tag/commit/远端附件digest及待验项目。

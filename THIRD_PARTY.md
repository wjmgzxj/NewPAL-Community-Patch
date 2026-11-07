# 第三方、素材与依赖

本项目是面向Steam正版《新仙剑奇侠传》的非官方粉丝补丁，不提供完整游戏或正版验证绕过。原游戏、商标和原有素材的权利归各自权利人；项目自有内容的非商业许可不覆盖这些权利，也不替第三方重新授权。

## 素材范围与来源

逐文件用途与哈希见[素材来源清单](docs/asset-provenance.json)，运行版完整清单见[baseline.json](baseline.json)。

- 地图纸面、风格化地图、人物标记及其组件来自本项目制作的图像与后续编辑。路线/连接参考游戏数据及两套攻略，不把攻略图当作项目原创。47页补充美术仅为后续候选，未全部校验或接入。
- 不遇敌菜单是用户提供的扁平化修改界面，再加工为开关状态PNG。它保留原菜单背景元素，不宣称原游戏界面权利属于本项目。
- 独立传送器保留现有工具的475张缩小地图预览和数值格数据，用于选择测试坐标；其中预览源自游戏提取图，**不属于项目原创美术**。工具包不含可启动游戏、存档、原音频或完整游戏资源包。不要将工具内预览作为独立美术全集转载。
- 炼蛊菜单来自用户提供的扁平化修图，保留原界面元素；新增名牌/连线为项目绘制，数字与名字使用游戏运行时原生文字层，不附字体文件。
- 两套网页攻略本身、原始高分辨率提取全集、PSD字体文件和私人制作记录不随源码目录整包分发。参考站点：[仙剑英雄网](https://www.palhero.net/?p=2894)、[秋忆网站攻略](https://chiuinan.github.io/game/game/intro/ch/c11/palgame/palgame/palgame.htm)。

## 字体

地图制作脚本使用Windows提供的楷体、微软雅黑和Times New Roman，传送器按名称请求系统字体。发布的是已经渲染的文字图片，不含TTF/OTF/TTC、字库或独立逐字位图字体。Windows字体使用说明见[Microsoft字体FAQ](https://learn.microsoft.com/en-us/typography/fonts/font-faq)。

用户菜单制作时选用过“華康正顏楷體W5”的近似字体；本项目仅接收、分发必要的扁平化界面图片，不提供该字体安装包，也不授予字体本身的使用权。继续编辑者应使用自己有权使用的字体。生成图中绘出的字形与程序调用的字体分别记录，不把二者混为字体嵌入。

## 程序与依赖

自研补丁脚本和工具代码按根目录LICENSE.md。第三方组件保持原许可；本项目禁止商用的条款不改变第三方组件的授权。工具以未修改的CPython和Tcl/Tk等运行库打包，不修改这些运行库。

|组件|用途与分发范围|许可材料|
|---|---|---|
|CPython 3.10.8|独立工具内的运行时/标准库|third_party/Python-3.10.8-LICENSE.txt，包含PSF及多项随附组件说明|
|Tcl/Tk 8.6.12|工具窗口|third_party/Tcl-8.6.12-license.terms、Tk-8.6.12-license.terms|
|OpenSSL 1.1.1q、libffi、bzip2、LZMA|CPython随附运行库|Python许可汇编及libffi-LICENSE|
|Expat、zlib|CPython的XML/压缩支持|Expat-COPYING、zlib-notice.txt|
|SQLite 3.37.2|标准库随附动态库|[SQLite公开领域说明](https://sqlite.org/copyright.html)|
|Microsoft VC/UCRT运行库|官方Python Windows运行依赖|保留原始二进制及版权，见[Python Windows说明](https://docs.python.org/3.10/using/windows.html)|
|NumPy、Pillow、pefile|地图制作/检查依赖，不要求玩家安装|third_party内各项目原始许可，版本见requirements-map.txt|
|PyInstaller|独立程序打包及bootloader|third_party/pyinstaller，遵循其bootloader例外|
|Capstone、Unicorn、psd-tools|可选研发工具，本下载不附其安装环境|使用各自官方分发与许可，见docs/工具说明.md|

许可原件下载出处记录在third_party/license-sources.json。此表是当前分发内容的来源与通知说明，不宣称得到原游戏权利人的官方认可。

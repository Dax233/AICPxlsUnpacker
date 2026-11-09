# 实机验证记录：重建产物能否被 PixelLiner 打开

> 结论（2026-11-09）：**能**。用真实 AIC 素材构造的"外置贴图"变体，经
> `reconstruct_pxl.py` 重建后，在 **PixelLiner 0.97.14** 中完整加载、渲染、编辑，
> 另存为工程格式 `.pxl` 后还能再次打开。

## 1. 测试环境

| 项 | 值 |
| --- | --- |
| 系统 | Debian 13（无 Windows） |
| 显示 | Xvnc（`DISPLAY=:1`，VNC 5901） |
| 兼容层 | Wine 10.0 |
| AIR 运行时 | HARMAN AIR SDK 51.5.1 **Windows** 版（`adl64.exe`，SDK 自带 captive runtime） |
| 被测软件 | PixelLiner **0.97.14**（Adobe AIR 24 应用，`.air` 取自 PixelLinerTranslate 公开镜像） |

Android/Linux 原生 AIR SDK 免费层会拒绝运行（"Linux runtime is limited to use by
commercially licensed developers"），所以走 Wine + Windows SDK 的 `adl64.exe`。

## 2. 启动与传文件（关键）

Wine 下 PixelLiner 的菜单/文件对话框自动化不可靠（`Ctrl+O` 容易点错到
「連結PNGの読込」）。但 PixelLiner 注册了 AIR 的 InvokeEvent
（`EDT/AFL.as: fnFileInvoke`），因此可以**把文件作为 adl 启动参数**传入：

```bash
# adl <application.xml> [<root-dir>] -- <app 参数...>
cd app/pixelliner
WINEPREFIX=/path/to/wineprefix DISPLAY=:1 \
  wine64 ../../airsdk_win/bin/adl64.exe application.xml -- 'C:\tests\target.pxl'
```

`--` 不能省：否则第二个位置参数会被 adl 当成 root-dir，报
`app:/pxl.swf initial content not found`。

运行时出现「更新アップデート」提示框点 CANCEL 即可。

## 3. 验证结果

输入样本：来自公开 mod 仓库（AAAA9731/WeNeedMoreNoels）的 UnityFS AssetBundle，
用 UnityPy 解出的真实 AIC `.pxls.bytes` + 纹理 PNG（版权归游戏作者，仅本地测试用，
不随仓库分发）。

| # | 输入 | 结果 |
| --- | --- | --- |
| A | 普通 PNG（texture_0.png，环境对照） | ✅ 作为新角色打开、画布显示图集，无崩溃 |
| B | 手写的 491B 工程格式最小样本（见 docs/minimal_pxl_reference.py） | ⚠️ 部分加载后报 `Error #2030: End of file was encountered`，属该参考样本自身 POSE 字段未写全，非环境问题 |
| C | 1.8 MB 真实内嵌图集样本（noel_magic_blue，76 poses） | ✅ 完整打开：pose/图层/画布渲染正常 |
| D | **重建产物**（noel_blue，4.6 MB，177 poses） | ✅ **完整打开**：pose 列表 177 个、图层列表与时间轴 000–003 帧齐全、画布渲染完整立绘、无错误框 |
| D2 | 在 PixelLiner 中「名前を付けて保存」 | ✅ 成功，输出 5.32 MB 工程格式文件（ASCII 头 `konnna_syarinn...` + `%IMGS_SECTION%` + `%POSE_SECTION%` + `%OPTS_SECTION%`） |
| D3 | 重新打开 D2 的文件 | ✅ 完整恢复，编辑→保存→再打开闭环成立 |

另外，重建产物与游戏内嵌图集版本的原始文件 **sha256 逐字节一致**，说明
"外置贴图 → 内嵌贴图"的转换没有引入任何像素/结构改动。

## 4. 与 issue #1 的关系

- issue 里的 `.pxls.bytes + texture_0.png`（外置贴图变体）→ 重建出的文件
  在真机 PixelLiner 里与内嵌图集版本行为一致（D 的输入正是按该形态构造并转换的）。
- 因为 PixelLiner 打开 PXLS 容器后会自动 `EdCsp.convertFromPxls()` 转成可编辑角色，
  所以不需要我们自己重写工程格式；另存时 PixelLiner 会写出标准工程 `.pxl`。

## 5. 复验方法

1. 准备 Wine + AIR SDK Windows 版 + PixelLiner 0.97.14 解包目录；
2. `python reconstruct_pxl.py files -o unpack` 生成 `.pxl`；
3. 用上面第 2 节的 `adl ... -- 文件` 启动；
4. 观察左侧 pose 列表 / 图层 / 画布是否恢复。

（具体环境的下载地址、样本 sha256、55 张验证截图与一键脚本在本次调查的临时目录
`/data/home/code/temp/20261109-assets/`，未提交进仓库——素材版权归游戏作者。）

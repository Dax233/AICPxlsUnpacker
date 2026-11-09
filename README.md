# AICPxlsUnpacker

自动拆分 Alice In Cradle 中 `*.pxls.bytes` 与 `*.pxls.bytes.texture_0.png` 纹理图文件的工具，
并支持**把拆分出来的数据重建为 PixelLiner 可直接编辑的 `.pxl` 文件**。

注:为了方便做 mod 写的，后续可能只会对针对像素小人的图有优化更新，欢迎大佬来协助维护这个项目。
另外这个项目是靠分析 pixelliner 的演示文件写出来的，所以理论上也可以拆分其它使用该程序制作的 unity 资产。

#### 游戏作者

[ひなゆあ🔞Alice in Cradle 制作中 (@hinayua_r18) / Twitter](https://twitter.com/hinayua_r18)

[橋野みずは🌿アルケミスト志望同人ゲーム制作系VTuber (@HashinoMizuha) / Twitter](https://twitter.com/HashinoMizuha)

**再次感谢两位作者为广大玩家提供此游戏并允许对游戏内容进行更改。**

## 功能一：拆分 PNG（原有功能）

从 `*.pxls.bytes` 的 PACK 段读取每个图块的 UV，再从纹理图集里裁剪出单张 PNG。

### 使用方法

1. 安装依赖：

   ```bash
   pip install -r requirement.txt
   ```

2. 在运行目录下新建 `files` 文件夹，把 `*.pxls.bytes` 与对应的
   `*.pxls.bytes.texture_0.png` 放进去。
3. 运行 `python start.py`，裁剪结果输出到 `unpack/<资产名>/`。

## 功能二：从 pxls + png 重建 `.pxl`（issue #1）

> 详细背景见 [issue #1](https://github.com/Dax233/AICPxlsUnpacker/issues/1)：
> AssetStudio 之类的工具已经能把 `pxls` 与 `png` 从 `dat` 里拆出来，
> 但真正麻烦的是"把它们还原成 PixelLiner 能打开继续编辑的 `.pxl`"。

好消息：**这件事不需要重新实现整个工程格式**。PixelLiner 的打开对话框
（`ファイル -> 読み込み...`）其实同时接受三种扩展名并按文件头自动分派：

| 文件头 | 含义 | 处理方式 |
| --- | --- | --- |
| 文本 `konnna_syarinn...` | 工程格式 `.pxl`（`%IMGS_SECTION%`，逐图内嵌） | 直接打开 |
| `u32 0x7741A8FF + "PXLS"` + `%PACK_SECTION%` | 游戏导出格式（图集） | 读入后自动转成可编辑角色 |

游戏导出的 `.pxls.bytes` 与工程格式的唯一结构性差异在于：它的
`%PACK_SECTION%` 图集记录带 **"贴图外置"标志位**，PNG 被单独导出成
`texture_N.png`。把这个标志位清掉、把 PNG 内嵌回去，文件就变成
PixelLiner 可直接打开的形态；打开后它会把 PXLS 转换成可编辑角色，
另存就会得到标准工程 `.pxl`。

本仓库的 `reconstruct_pxl.py` 就做这一件事（纯标准库，不需要 Pillow）：

```bash
# 默认：处理 ./files，输出到 ./unpack
python reconstruct_pxl.py

# 指定目录，并在产出后做结构自校验
python reconstruct_pxl.py files -o unpack --verify

# 只处理指定文件
python reconstruct_pxl.py --file files/noel_blue.pxls.bytes
```

输入命名要求与功能一相同：`<资产名>.pxls.bytes` 旁边放
`<资产名>.pxls.bytes.texture_0.png`（也兼容 AssetStudio 的
`Texture_<资产名>.pxls.texture_N.png` 等常见命名）。

输出：`unpack/<资产名>.pxl`，可以直接拖进 PixelLiner，或从
`ファイル -> 読み込み...` 打开，之后正常编辑、另存即可。

### 实现说明

- 只做**容器级**改写：解析 section 表，仅替换 `%PACK_SECTION%` 的内容，
  其余 section（`%POSE_SECTION%`、`%PTCL_SECTION%`、`%IMGV_SECTION%` 等）
  原样复制，避免引入不必要的格式风险。
- 支持一个资产有多个图集记录的情况（例如同时导出了 I 图集和 parts 图集时，
  按记录顺序依次寻找 `texture_0.png`、`texture_1.png`……）。
- 若输入本来就是内嵌图集（有些 mod 资产是这样），产出与原文件等价，
  同样可以交给 PixelLiner 打开。

### 实机验证（2026-11-09）

在 PixelLiner 0.97.14（Adobe AIR 24，Wine + HARMAN AIR SDK 51.5.1 adl 启动，
通过 adl 的 InvokeEvent 传文件参数）上实测：

- 用真实 AIC 资产构造"外置贴图"变体（模拟 AssetStudio 解包后的形态），
  经 `reconstruct_pxl.py` 重建后，与原始内嵌文件**逐字节一致**（sha256 相符）；
- 重建产物能正常加载：177 个 pose、图层列表与时间轴完整、画布正确渲染立绘，无错误弹窗；
- 加载后可正常「別名で保存」，输出为标准工程格式 `.pxl`
  （ASCII 头 `konnna_syarinn...` + `%IMGS_SECTION%` + `%POSE_SECTION%` + `%OPTS_SECTION%`），
  即已被 PixelLiner 当作可编辑工程。

（截图含游戏素材，未收录进仓库。）

### 测试

```bash
python -m unittest discover -s tests -v
```

测试夹具自己构造最小 PXLS 容器，不依赖游戏资产；另外可用环境变量指定真实
`.pxls.bytes` 跑往返验证：

```bash
AICPXLS_REAL_SAMPLE=/path/to/noel_blue.pxls.bytes \
    python -m unittest tests.test_real_sample -v
```

它会自动把样本改写成"外置贴图"变体，再重建，要求结果与原内嵌文件逐字节一致。

### 已知限制

- 只处理 PXLS 容器格式；若拿到的是工程格式 `.pxl` 则不需要转换，直接打开即可。
- 不重建像素数据本身：本工具只是把外置图集**原样内嵌**回去，像素数据完全来自游戏资产。
- 若缺少对应 `texture_N.png` 会明确报错并列出尝试过的路径，不会静默产出坏文件。

## 深入阅读

- [PixelLiner .pxl 工程格式规范](docs/pixeliner-pxl-format.md)：从反编译源码整理的完整格式文档
  （P 格式 / X 格式、EdImg、EdPose、线段长度、最小可打开文件等），附带参考实现
  [docs/minimal_pxl_reference.py](docs/minimal_pxl_reference.py)。
- 本仓库的 `reconstruct_pxl.py` 走的是更省事的"容器级改写"路线；上面的工程格式文档是
  给需要做完整 `%IMGS_SECTION%` 转换的后来者参考的。

## 参考资料 / 致谢

- PixelLiner（くろば・Ｕ / cloba.U）：<https://pixelliner.sakura.ne.jp/wiki/>
- [e9ae9933/pixelliner4j](https://github.com/e9ae9933/pixelliner4j)：
  PXLS 格式的 Java 只读实现，本工具的格式理解大量参考了该项目
  （以及 PixelLiner 0.97.14 反编译源码 `jp/clobau/pixelliner/pxls/`）。
- [DreamRuthenium/PixelLinerTranslate](https://github.com/DreamRuthenium/PixelLinerTranslate)：
  提供了 PixelLiner 版本与本地化信息，方便定位可复现的 0.97.14 AIR 包。

## LICENCE

AGPL @Dax233
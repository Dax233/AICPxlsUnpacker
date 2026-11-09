# PixelLiner 0.97.14 .pxl 工程文件格式规范（可写出器实现级）

> 目标：把 Alice in Cradle 导出的 `*.pxls.bytes`（`%PACK_SECTION%` 变体）重建为 PixelLiner
> 0.97.14 能直接打开并编辑的 `.pxl` 工程文件。
>
> 依据：FFDec 反编译的 PixelLiner 0.97.14 ActionScript 源码
> PixelLiner 0.97.14 反编译 ActionScript 源码（下称"源码"），并用真实游戏资源做了结构验证。
> 本目录附最小文件参考实现 `minimal_pxl_reference.py`（生成 + 镜像自检），
> 生成的 `minimal.pxl`（491 字节）可作字节级对照。**尚未在 PixelLiner 中实际打开验证**，见第 10 节。

---

## 0. 结论速览（TL;DR）

1. 工程格式（扩展名 `.pxl`，下称 **P 格式**）与导出格式（`.pxls` / `.pxls.bytes`，下称 **X 格式**）是两套东西：
   - **P 格式**：ASCII 头 `konnna_syarinn_no_saikaihatsu_ha_okashii_by_cloba_u`（51 字节，`EDF.headerKey`）
     + `%IMGS_SECTION%` / `%IMGD_SECTION%` + `%POSE_SECTION%` + `%OPTS_SECTION%` + `%EXPT_SECTION%`。
   - **X 格式**：`u32 0x7741A8FF` + 原始字节 `"PXLS"`；段一律 `14 字节段名 + u32 段长 + 载荷`；
     游戏资产里是 `%PACK_SECTION%` + `%POSE_SECTION%`。
2. 全程 **大端**；无全局长度、无校验和、无对齐填充。仅有的"保留字节"：IMGS 后 16 字节 0、
   pose 数据后 curPose 标题 + 16 字节 0、图层尾部 `u32 0 + u8 0 + u8 0`。
3. 字符串（`XX.Str.writeString`）：**u16 大端字节长（截断 65535）+ UTF-8 字节**，无 NUL。
4. 图像段 `%IMGS_SECTION%`：`u32 图数` + 每张图一个 `EdImg`；每张图必须有
   `key=(id:u32, id2:f64)`、`type`、`I`（正常色 PNG）、`P`（parts 色 PNG）两张内嵌 PNG。
5. 图层只引用图像 key，不内嵌图；坐标/缩放/旋转/透明度/混合模式在 `EdALayer` 中。
6. **关键坑**：`EdALayer.type==0`（普通 luster 层）时 `zmx/zmy/rotR` 三个 f64 **不写入文件**，
   读取端 `stabilizePosition()` 会把变换强制拉直。凡有非单位变换的图层类型必须 `>0`；游戏 X 格式里
   变换层恰好都是 `type=1`，转换时原样保留即可。
7. 最小可打开文件 = 头 + IMGS（≥1 张图）+ POSE（≥1 pose / 1 aim / 1 帧 / 1 图层）。
   `%OPTS_SECTION%`、`%EXPT_SECTION%` 可省略（读取端有缺省处理），建议带 OPTS 固定标题/背景色。

---

## 1. 编码与基础类型

所有多字节整数/浮点为 **big-endian**（Flash ByteArray 默认大端）。

| 记号 | 字节 | 源码 | 说明 |
|---|---:|---|---|
| u8 / i8 | 1 | `writeByte` | 布尔 = `writeBoolean` = 1 字节 0/1 |
| u16 / i16 | 2 | `writeShort` 写 / `readUShort` 读 | 读端常把负数 +65536 当无符号 |
| u32 | 4 | `writeUnsignedInt` | 段长、计数、颜色 |
| f64 | 8 | `writeDouble` | IEEE-754，用于 `id2`、变换 |
| f32 | 4 | `writeFloat` | 仅 `writeObject` 类型 8 |
| str | 2+n | `Str.writeString` / `Str.readString` | u16 BE 字节长 + UTF-8；空串 `00 00` |
| extract | 1/2/4 | `Str.writeExtract(Ba,data,len_byte)` | 长度前缀 + data；默认 2，`%EXPT%` 用 4 |
| object | — | `Str.writeObject` / `Str.readObject` | 见下 |

`Str.writeObject`（仅用于 `%EXPT_SECTION%` 的导出设置）：
```
重复 {
  str   key
  u8    类型
  value 按类型
} 直到 u16(0) 终止
类型码：4=bool(1B) 5=u32 6=i32 7=str 8=f32 9=f64 15=u16 16=i16 25=u8 26=i8
```
空对象 = 仅 `00 00`（2 字节）。`Str.writeFlags(...)` 参数按 bit0 起置位返回 u32。
`Str.writePascalString`（u8 长度）本格式 **不使用**。

---

## 2. .pxl（P 格式）整体布局

由 `EdCsp.getSaveBytesExecute()` 产出：先写 51 字节 `EDF.headerKey`，再 `EdCsp.writeToBytes()`。
`writeToBytes()` **不写头**，写出器需自行先写头。

```
偏移      内容
0         51 字节 headerKey = "konnna_syarinn_no_saikaihatsu_ha_okashii_by_cloba_u"
51        "%IMGS_SECTION%" (14) 或 "%IMGD_SECTION%" (14)
65        u32 图像段载荷字节数 N
69        N 字节载荷：u32 图像数 + 各 EdImg
+0        16 字节 0（4×u32；读取端 position += 16，不校验）
+16       "%POSE_SECTION%" (14)
+30       u32 pose 数
+34       pose 数据（EdPose 连续平铺，无长度前缀）
+         str curPose 标题
+         16 字节 0（读取端 position += 16）
+         [可选] "%OPTS_SECTION%" (14) + OPTS 载荷（无整段长度字段）
+         [可选] "%EXPT_SECTION%" (14) + u32 载荷长 + writeObject 数据
EOF       无文件尾标记
```

注意：**P 格式 `%POSE_SECTION%` 没有 u32 段长**（X 格式有）；`%OPTS/%EXPT` 也不是"段长=整个载荷"，
OPTS 是"段名 + 顺序字段"，EXPT 是"段名 + u32 内部对象长 + 对象"。

### 2.1 头部（51 字节）
源码 `EDF.as:44-46`：
```
headerKey_head_sct = "konnna_syarinn"    // 15B，注意 3 个 n
headerKey = headerKey_head_sct + "_no_saikaihatsu_ha_okashii_by_cloba_u"   // 51B
```
`EDF.fnOpenSuccess` 先读 `u32 h0`（`EDF.as:478` 起）：
- `h0 == 1802464878`（ASCII `"konn"` = `0x6B6F6E6E`）→ `initPxlLoad` → `Str.checkHeader(Ba, headerKey)`；
- `h0 == PxlCharacter.file_header1`（`2000791807` = `0x7741A8FF`）→ `.pxls`/PXLS 加载。
头必须逐字节等于上述 51 字节 ASCII，否则报 `"PXL ファイルのエラー"`。
`EdCsp.readFromBytes`（`EdCsp.as:970-983`）：先读 14 字节，若等于 `"konnna_syarinn"` 就回退 14、
校验 51 字节头、再读 14 字节作为第一个段名 ⇒ **头后必须紧跟段名**。

---

## 3. %IMGS_SECTION% / %IMGD_SECTION%（图像段）

`EdCsp.writeToBytes`（`EdCsp.as:865-900`）：
```
u32 imageCount
重复 imageCount 次：EdImg 数据（见 `3.1）
```
整段包成 `段名(14) + u32 载荷长度 + 载荷`。若 `compress_graphics` 为 true，则载荷整体
Flash `ByteArray.deflate()`（**zlib 流**）且段名写 `%IMGD_SECTION%`，读取端 `inflate()`。
建议一律写未压缩 `%IMGS_SECTION%`。载荷后紧跟 **16 字节 0**（4×u32，不属于段长）。

### 3.1 EdImg 数据块（`EdImg.as:1253-1309 / 927-1095`）
`type`：`0`=luster、`2`=vector、`8`=luster+vector（`EdImg.isValidType`；`TYPE_ADD=22`）。

```
u8   typeByte = type + 22        // type=0 -> 0x16
u8   vers = 0                    // 当前读端不校验；容错扫描要求 0
u32  id
f64  id2
[type 含 luster 位（0 或 8）]
  u32 lenI; bytes[lenI]          // PNG：正常色图 I
  u32 lenP; bytes[lenP]          // PNG：parts 色图 P
[type 含 vector 位（2 或 8）]
  f64 l2v_quality_               // 默认 3.0
  u32 lenV; bytes[lenV]          // EdVectorData；可为 0
```
- **未使用图像槽**只写 1 字节 `type+22 = -1+22 = 0x15`，读端读到 type<0 直接 return（`EdImg.as:1258-1266`）。
  正常文件不要产生这种槽。
- **I 和 P 都必须有且尺寸一致**：读端给 luster 图同时挂 `LOAD_I`/`LOAD_P` 两个异步任务，
  只有 `I && P` 才算完成（`EdImg.as:1326`）；P 长度为 0 会让该图永远 loading。
- P 像素约定：`EDI.considerParts()`（`EDI.as:2084-2097`）把 I 中不透明像素全部涂成
  `0xFF787878`（= `EdCellColor.PARTS_DEF_COL(0xFF707070) | 0x080808`），透明像素保持 0。
  即 **P = I 的 alpha 遮罩 + parts 默认色**，32 位 ARGB PNG。
- `id2` 只要求同一 key 在图像表和图层引用里写**同样的 8 字节 double**；读端用
  `id.toString(16) + "_" + id2`（AS Number.toString）索引，两边公式一致，实现语言无需模拟 AS 数字格式化。
- 图像顺序任意，靠 key 查找；**不要重复 key**（后写同 key 会被 `EDI.assignImage` 忽略）。
- `EdImg` **没有**独立的 preview / alpha 字段：显示预览就是 I 本身，透明度已编码在 I 的 PNG alpha 里；
  P 只是 parts 色图（供 parts 调色板绘画用），不是 alpha 图。

---

## 4. %POSE_SECTION%（姿态段）

`EdCsp.writeToBytes`（`EdCsp.as:901-921`）：
```
"%POSE_SECTION%" (14)
u32 poseCount
poseCount × EdPose 数据（平铺，无长度）
str curPoseTitle
16 字节 0
```
读取端记住 pose 计数起点，逐个 `EdPose.readFromBytes`；全部完成后读 `curPoseTitle`、跳 16 字节，
再 `readAfterData`。`curPoseTitle` 用于默认打开 pose；写空串则默认第一个 pose。

### 4.1 EdPose（`EdPose.as:825-929`）
```
u8   vers = 4
u8   data_auto_flip (bool)
str  title
i16  cvw
i16  cvh
重复（aim 0..7 中有效且未 flip 的）{
  u8   aim + 10                    // 10..17
  EdSequence 数据（`4.2，平铺）
}
u8   0                             // 序列列表结束
i16  aliasCount
str  alias[aliasCount]
str  end_jump_title
i16  flags = writeFlags(tetra_pose, auto_flip)   // bit0=tetra, bit1=auto_flip
object Oadditional_var             // 空对象 = 00 00（读端会取其中 cvw/cvh/Aalias_to 覆盖）
str  comment                       // vers>=2
str  edit_layer                    // vers>=3（编辑时选中图层名，可空）
u8   end_jump_loop_count           // vers>=4
```
读端要求至少解析出 1 个有效 aim/序列，否则返回 false，该 pose 被丢弃（`EdPose.as:880-898`）。
`cvw/cvh` 读用 `readUShort`，取 1..32767。转换时把 X 格式 `auto_flip` 写进 bool 字节、flags 写 tetra。
`Oadditional_var` 写空对象即可。

### 4.2 EdSequence（`EdSequence.as:802-910`）
```
u8   vers = 1
i16  maisu                        // 帧数；读端 readUShort；65535=忽略帧特殊值，正常别用
i16  width                        // 读端 readUShort
i16  height
i16  bodyx
i16  bodyy
i16  shiftx
i16  shifty
i16  loop_to
maisu × EdAFrame 数据（`4.3）
i16  soundCount
str  sound[soundCount]
u8   stopped (bool)
i16  cframe
i16  loop_start                   // vers>=1
i16  loop_end
```

### 4.3 EdAFrame（`EdAFrame.as:574-635`；`VERS_DEFAULT=3`）
```
u8   vers = 3
i16  layerCount                   // 帧内全部图层数（含 group 子层，见 `4.4）
i16  crf60                        // 帧时长，1/60 秒（默认 10）
str  name                         // 可空
u8   flags = (important?1:0) | (pinned?2:0)   // 读端只还原 important（源码 bug）
layerCount × EdALayer 数据（`4.4）
```

### 4.4 EdALayer（`EdALayer.as:1420-1526`）
```
u32  imgId
f64  imgId2
u8   type                         // 位域，见 `5
[若 type & 8（group）] EdGroupContainer:
     u8  vers = 0
     u8  toggled (bool)
     u32 preserve_contain_layers  // 该 group 包含的图层数
[i16 f]                           // 仅 ClipGetter（剪贴板粘贴）路径；正常文件没有！
str  name
i16  alpha100 = int(alpha * 100)  // alpha 0..100；读端 readShort()/100 并 clamp 0..100
i16  x10 = int(x * 10)            // 读端 /10；坐标是图层中心（相对 pose 画布中心）
i16  y10 = int(y * 10)
[若 type > 0]
     f64 zmx
     f64 zmy
     f64 rotR                     // 弧度；PI = 180°
i16  blend_variable               // 低 8 位 lblend，高 8 位 ablend
u32  0
u8   0
u8   0
```
- `ClipGetter` 是静态剪贴板状态，正常打开/保存为 null，写出器不要写那个 i16。
- group 层同样走 `type>0` 分支写 zmx/zmy/rotR（一般 1,1,0）。
- group 子层**不嵌套**写在 group 内部，而是作为同一帧后续 `EdALayer` 依次出现，加载后由
  `EdGroupContainer.fineLinks()` 归组；因此 `layerCount` 是扁平列表长度。最小文件不需要 group。
- 读取时 `stabilizePosition()`（`EdALayer.as:1528`）：type==0（非 float/import）→
  `x=int(x); y=int(y); zmx=zmy=1; rotR=0`（小数坐标与变换被抹掉）；type 含 bit0/bit2 → 保留。
- 坐标范围受 i16 限制：x/y ∈ [-3276.8, 3276.7] px。
- `hidden` 不入文件（隐藏用 alpha=0）；`important/pinned` 在帧上。

---

## 5. 字段编码汇总：key / type / alpha / 变换（问题 6）

### 5.1 图像 key
- `id`：u32，`id.toString(16)` 参与 idstr（如 `EDI1bf52_998244353`）。
- `id2`：f64（double）；源码随机取整型 double。
- 注册/查找完全依赖 `"EDI" + id.toString(16) + "_" + id2` 字符串；同一 key 在两处必须同 double 位模式。

### 5.2 `EdALayer.type` 位域（`EdALayer.as:20-36, 1736-1759`）
| bit | 值 | 常量 | 含义 |
|---:|---:|---|---|
| 0 | 1 | TYPE_IMPORT | 导入（关联）层；可自由变换，不可直接绘制 |
| 1 | 2 | TYPE_VECTOR | 矢量层 |
| 2 | 4 | TYPE_FLOAT | 浮游层；可自由变换 |
| 3 | 8 | TYPE_GROUP | 组 |
| 组合 | 3/5/6/7 | — | 按位组合（如 3=矢量导入） |

**只有 `type > 0` 才写 zmx/zmy/rotR 三个 f64**。`0`=普通 luster（不能带变换/小数坐标）；
`1`、`4` 是普通带变换层常用值。X 格式游戏数据里变换层正好是 `type=1`、普通层 `type=0`（实测 `7.3），可原样照抄。

### 5.3 其它
| 字段 | 编码 | 说明 |
|---|---|---|
| alpha | `i16 = int(alpha*100)` | 0..100 → 0..10000 |
| x, y | `i16 = int(x*10)` | 读端 /10；type==0 时读端再取整 |
| zmx, zmy | `f64` | 1=原始；-1=水平/垂直翻转 |
| rotR | `f64` | 弧度，±π = 180° |
| blend_variable | `i16`（读 u16） | lblend=低8位，ablend=高8位 |
| crf60 | `i16` | 帧时长 1/60 秒 |
| flags(pose) | `i16` | bit0 tetra_pose，bit1 旧 auto_flip |

---

## 6. 加载器行为、容错与最小 section 集合（问题 4）

1. `EDF.fnOpenSuccess` → 命中 `"konn"` → `initPxlLoad` → 校验 51 字节头 → `EdCsp.copyFrom(ByteArray)` → `readFromBytes`。
2. `readFromBytes`（`EdCsp.as:961-1029`）：
   - 读第一个段名；必须是 `%IMGS_SECTION%`/`%IMGD_SECTION%`，否则置 `ERROR_NO_IMAGE` 并跳 `readAfterData`；
   - 读 u32 段长、拷出图像载荷（IMGD 先 inflate）、读 u32 图像数；
   - `position += 16`（跳过 4×u32 保留）；
   - 读 14 字节**必须**是 `%POSE_SECTION%`（否则 `ERROR_POSE_HEADER` 并向前扫描恢复）；
   - 记录 pose 数据起点、读 u32 pose 数、挂 `LOAD_PXL` 任务。
3. `progressLoad`（`EdCsp.as:1031-1097`）每次 tick：先逐张 `new EdImg(图像载荷)`；图像读完后逐 pose
   `new EdPose()` + `readFromBytes` + `addP`；pose 读完后读 curPose 标题、跳 16 字节，进入 `readAfterData`。
4. `readAfterData`（`EdCsp.as:1104-1233`）循环读 14 字节段名：
   - `%OPTS_SECTION%`：标题、ColorData、4×背景色、opvers、字幕/幻影脚本、导出路径记忆；
   - `%EXPT_SECTION%`：`Str.readExtract(Ba,4)` + `Str.readObject` → `OExpVals`；
   - 其它段：置 `ERROR_SECTION` 并扫描 `%` 恢复（**不要写未知段**）。
   末尾 `prepareDefault()` + `fineLinks()`。

**最小可用集合**：`51 字节头 + %IMGS_SECTION% + 16 字节 0 + %POSE_SECTION% + pose 数据 + curPose 标题 + 16 字节 0`。

- `%OPTS_SECTION%`：**非必需**。缺省时标题来自文件名（`EDF.initPxlLoad` 用 `validName`），
  ColorData 为空 ByteArray，背景色取 `CFG.Abgcol`；OPTS 的 title 仅在 `Csp.title` 为空或 `"NewCharacter"` 时采用。
- `%EXPT_SECTION%`：**非必需**。缺省 `OExpVals = {}`，只影响导出设置对话框默认值。
- `%POSE_SECTION%`：**必需**，缺失会在 `copyFrom` 抛异常，报 `"PXL ファイルのエラー"`。
- 图像段：技术上可缺（`ERROR_NO_IMAGE`），但所有图层会变成 64×64 空白占位，无意义。
- 错误位（`EdCsp.ERROR_*`）由 `CspErrorCheck.checkLoadAfter` 汇总；非 0 时"能开但不干净"。
  写出器应保证为 0：段序正确、计数匹配、保留字节齐全。
- 计数上限：图像数、pose 数须 `0 <= n < 262144`（`X.BTW`），否则 clamp 并置错误位。
- 加载分帧异步：PNG 解码任务并行；只要 PNG 合法、I/P 尺寸一致即可。

---

## 7. X 格式（.pxls / .pxls.bytes，%PACK_SECTION%）与差异（问题 5 上半）

### 7.1 整体
```
u32  0x7741A8FF            // PxlCharacter.file_header1 = 2000791807
raw  "PXLS" (4 字节)
重复直到 EOF {
  14 字节段名
  u32 段载荷字节数
  载荷
}
```
段（`PxlCharacter.as:40-50, 274-423`）：
| 段名 | 载荷 |
|---|---|
| `%IMGS_SECTION%` | u32 图数 + `PxlImage` 序列（内嵌 PNG） |
| `%IMGD_SECTION%` | 同上但 deflate(zlib) |
| `%PACK_SECTION%` | u32 图集数 + `PxlsImgAtlas` 序列 |
| `%IMGV_SECTION%` | 矢量数据（可忽略/单独处理） |
| `%POSE_SECTION%` | u32 pose 数 + `PxlPose` 序列（**带分段长度**） |
| `%PTCL_SECTION%` | `u32 颜色数据长 + EdCellColor.writeToBytes()` |

### 7.2 X 格式内部结构（与 P 格式不同，别混用）

`PxlImage`（`PxlImage.as:176-216`，非 PACK）：
```
u8 typeByte = type+22
u8 vers
u32 id
f64 id2
[type 含 luster] u32 lenI + PNG; u32 lenP + PNG
[type 含 vector] 无（vector 在 IMGV 段）
```

`PxlsImgAtlas`（`PxlsImgAtlas.as:257-367`，PACK 每张图集）：
```
u8  imgTypeByte = imgType + 22    // imgType 0=NORMAL(I)，1=PARTS(P)
u8  flag                          // bit0=1: PNG 在外部文件；0: 内嵌
u8  margin                        // 实测常为 1
u32 entryCount
entryCount × {
  u32 id; f64 id2
  u32 x; u32 y; u32 w; u32 h     // 图集格子矩形，已含四周 margin
}
if (flag & 1) { u32 pngWidth; u32 pngHeight }
else          { u32 pngLen; bytes pngLen }
```
- 实际图像 = `(x+margin, y+margin, w-2*margin, h-2*margin)`（写时贴图在 `x+margin`；读时同样内缩）。
- 外部 PNG 命名（`PxlsExporter.as:593-605`）：`<pxls 文件名>.texture_<index>.png`，
  index = 图集写入序号（含 parts 图集，从 0 开始）；`flag&1` 时才用外部文件。
- 图集项按 `imgType` 填 `PxlImage.I`（normal）或 `PxlImage.P`（parts）。若导出未输出 parts
  （`pxls_parts_out` 未开），只有 normal 一张、`PxlImage.P` 为空，需要按 `3.1 规则从 I 生成 P。
- 图集装箱 margin=1（`PxlsImgPacker.as:margin`），PNG 其余区域透明。

`PxlPose`（`PxlPose.as:writeDataForPxls/readFromBytes`）——与 P 格式 EdPose 不同：
```
u32 headLen
head{
  u8 vers(=2); u8 auto_flip; u8 tetra_pose
  str title
  u16 width; u16 height
  u16 end_jump_loop_count
  str end_jump_title
  u16 aliasCount; str*
  if vers>=2: str comment
}
循环 {
  u8 aim + 10 (10..17)；为 0 结束
  u32 seqHeadLen
  seqHead{
    u8 vers(=1)
    u16 width; u16 height
    i16 bodyx; i16 bodyy; i16 shiftx; i16 shifty; i16 loop_to
    u16 soundCount; str*
  }
  u16 frameCount
  frameCount × {
    u32 frameHeadLen
    frameHead{ u8 vers(=3); i16 frame_time(crf60); str name; u8 flags }
    i16 layerCount
    layerCount × PxlLayer
  }
}
```
`PxlLayer`（`PxlLayer.as:readFromBytes/writeDataForPxls`）：
```
u32 id; f64 id2; u8 type; str name; i16 alpha*100
if (type & 8) { u32 preserve_contain_layers }        // group
else {
  i16 x*10; i16 y*10
  f64 zmx; f64 zmy; f64 rotR      // X 格式非 group 层"无条件"写三个 f64
  i16 blend_variable; u32 0; u8 0; u8 0
}
```
- X 格式 POSE 段每个 pose/序列/帧头部**带 u32 长度**，P 格式平铺；这是最容易写错的地方。
- `%PTCL_SECTION%` 后直接 `u32 colorLen + colorBytes`（`PxlCharacter.writeColorData`），不再套段长。

### 7.3 真实资产验证（可直接作解析器单测样例）
样本（已从 UnityFS 解包）：
- `/data/home/code/temp/20261109-assets/out/noel_blue/noel_blue.pxls.bytes`（4,668,479B）+ 同名 `.texture_0.png`（3,046,606B）
- `/data/home/code/temp/20261109-assets/out/noel_magic_blue/noel_magic_blue.pxls.bytes`（1,808,975B）
- `/data/home/code/temp/20261109-Kaleidoscopic/Resources/unifont128.pxls`（19,061B，独立导出 X 样本）

`noel_blue.pxls.bytes` 实测：
- 段：`%PACK_SECTION%`(4,363,071B) + `%POSE_SECTION%`(305,364B)，无 IMGV/PTCL；
- PACK：图集数 1；`imgTypeByte=22`(normal)、`flag=0`(内嵌 PNG)、`margin=1`、entryCount=1421；
  内嵌 PNG 2048×4096；所有 entry key 互不重复；
- POSE：177 poses、4665 图层；layer type 直方图 `{0:1420, 1:3245}`，无 group；
  图层引用的 1421 个唯一 key 全部能在图集找到。
- 该版本游戏把图集 PNG 内嵌在 `.pxls.bytes` 里（flag=0）；issue 所说"外部 texture_0.png"对应
  `flag&1=1` 的变体，转换器两种都要分支。注意该样本内嵌图 2048×4096 与外置 `texture_0.png`
  1024×2048 分辨率不同（外置应是另一版本资源），不能混用坐标。

`noel_magic_blue.pxls.bytes` 实测：图集数 1、entryCount=752、flag=0、margin=1；
POSE 76 poses / 1887 layers，type 直方图 `{0:752, 1:1135}`。

`unifont128.pxls` 实测：X 格式独立导出；PACK 图集 1 张、entryCount=128、margin=1、内嵌 PNG，
每项 48×48 字模格子，key 形如 `(114514, 998244353.0)`；验证了分段式 POSE 解析。

---

## 8. PACK → .pxl 工程转换映射（问题 5 下半）

1. **解析 X 文件**（`7.1/7.2）：得到 key→(I,P) 与 pose 树。
2. **裁剪图像**：
   - `flag=0`：读内嵌 PNG，按 `(x+margin, y+margin, w-2m, h-2m)` 裁剪；
   - `flag=1`：加载 `<base>.texture_<index>.png`（尺寸应与 pngWidth/Height 一致），同样按格子裁剪；
   - 每 key 得 I；有 parts 图集（imgType=1）则得 P，否则
     P = alpha 遮罩：不透明→`0xFF787878`，透明→0（尺寸同 I）。
3. **写图像表**：每个 key 一个 `EdImg`：
   | P 格式字段 | 来源 |
   |---|---|
   | `id/id2` | PACK entry 原样（double 原样） |
   | `type` | `0`（luster）；PACK 不产生矢量图 |
   | `I` | 裁剪后的正常色 PNG |
   | `P` | parts 图集裁剪，或由 I 生成的 `0xFF787878` 遮罩 |
   | `vers` | `0` |
   PACK entry 的 `x/y/w/h` 是打包元数据，**不写进 P 格式**；P 格式 EdImg 没有坐标字段，
   位置在每条 `EdALayer.x/y`。
4. **写 pose 树**：
   | P 格式 | X 格式来源 |
   |---|---|
   | `EdPose.title` | `PxlPose.title` |
   | `EdPose.cvw/cvh` | `PxlPose.width/height` |
   | `data_auto_flip` | `PxlPose.auto_flip` |
   | `flags` bit0 | `PxlPose.tetra_pose` |
   | `end_jump_title` / `end_jump_loop_count` | 同名 |
   | `Aalias_to` | `PxlPose.Aalias_to` |
   | `comment` | `PxlPose.comment` |
   | `edit_layer` | 无（空串） |
   | `Oadditional_var` | 空对象 |
   | `EdSequence.*` | `PxlSequence.width/height/bodyx/bodyy/shiftx/shifty/loop_to/Aframe_snd` |
   | `EdAFrame.crf60 / name` | `PxlFrame.frame_time / name` |
   | `EdALayer.imgId/imgId2` | `PxlLayer.id/id2`（必须与 EdImg key 位模式一致） |
   | `EdALayer.type` | `PxlLayer.type` 原样；**若来源 type==0 但 zmx!=1 或 zmy!=1 或 rotR!=0，改写为 1（import）或 4（float）**，否则变换丢失 |
   | `name/alpha/x/y/zmx/zmy/rotR/blend_variable` | 同名字段直接搬 |
   | `EdAFrame.important/pinned` | X 格式不存，写 0 |
   | group | X 导出通常已扁平化；若有 group，按 `4.4 扁平顺序写，preserve=子层数 |
5. **写文件**：头 + IMGS（未压缩）+ POSE +（建议）OPTS +（可选）EXPT。
   - `curPoseTitle` 取第一个 pose 名（或原打开 pose），必须与某 `pose.title` 完全一致；
   - OPTS：title=文件名去 `&` 前缀，ColorData 长度 0，Abgcol 默认，opvers=4，字幕/幻影各 0，
     remember_export_path=false；
   - EXPT：空对象（`u32 2 + 00 00`）。
6. **自检**：按 `6 镜像解析一遍，断言错误位 0、全部图层 key 命中图像表。

可选增强：把 X 的 `%PTCL_SECTION%` 转成 P 格式 OPTS 的 `ColorData`
（`EdCellColor.writeToBytes`：`u8 ver=1, u8 holderCount, PartsCHolder*, u8 curi, u8 curib,
ST__MAX×(u32 前色, u32 后色)`）。不写则用默认调色板。

---

## 9. 最小 .pxl 字节级构造清单 / 伪代码（问题 7）

参考实现：本目录 `minimal_pxl_reference.py`。运行
`python3 minimal_pxl_reference.py --out minimal.pxl` 生成 491 字节样本并用镜像解析器复读校验
（1 张 4×4 图、1 pose、aim 0、1 帧、1 图层）。

伪代码（BE=大端；str(s)=u16 字节长+UTF-8；计数 u32）：

```
write.bytes( b"konnna_syarinn_no_saikaihatsu_ha_okashii_by_cloba_u" )   # 51B

# ---------- 图像段 ----------
payload  = u32(1)                             # imageCount
payload += u8(0 + 22)                         # EdImg.type 0 -> 0x16
payload += u8(0)                              # vers
payload += u32(imgId) + f64(imgId2)
payload += u32(len(pngI)) + pngI              # I：正常色 PNG（RGBA）
payload += u32(len(pngP)) + pngP              # P：parts 遮罩 PNG（不透明处 0xFF787878）
write.tag("%IMGS_SECTION%")
write.u32(len(payload))
write.bytes(payload)
write.zeros(16)                               # 4×u32 保留

# ---------- 姿态段 ----------
pose  = u8(4)                                 # EdPose.vers
pose += u8(0)                                 # data_auto_flip
pose += str(poseTitle)
pose += i16(cvw) + i16(cvh)
pose += u8(10 + 0)                            # 仅 aim 0 的序列
seq   = u8(1)                                 # EdSequence.vers
seq  += i16(1)                                # maisu
seq  += i16(cvw) + i16(cvh)
seq  += i16(0)*5                              # bodyx,bodyy,shiftx,shifty,loop_to
frame = u8(3)                                 # EdAFrame.vers
frame+= i16(1)                                # layerCount
frame+= i16(10)                               # crf60
frame+= str("")                               # frame name
frame+= u8(0)                                 # flags
layer = u32(imgId) + f64(imgId2)
layer+= u8(0)                                 # type=0 luster（无变换）
layer+= str("Layer")
layer+= i16(100*100)                          # alpha=100
layer+= i16(0) + i16(0)                       # x,y
layer+= i16(0)                                # blend_variable
layer+= u32(0) + u8(0) + u8(0)                # 保留
frame+= layer
seq  += frame
seq  += i16(0)                                # soundCount
seq  += u8(1)                                 # stopped
seq  += i16(0)                                # cframe
seq  += i16(0) + i16(1)                       # loop_start, loop_end
pose += seq
pose += u8(0)                                 # aim 列表结束
pose += i16(0)                                # aliasCount
pose += str("")                               # end_jump_title
pose += i16(0)                                # flags
pose += u16(0)                                # 空 Oadditional_var
pose += str("")                               # comment
pose += str("")                               # edit_layer
pose += u8(0)                                 # end_jump_loop_count
write.tag("%POSE_SECTION%")
write.u32(1)                                  # poseCount
write.bytes(pose)
write.str(poseTitle)                          # curPoseTitle，必须匹配某 pose.title 或 ""
write.zeros(16)                               # 4×u32 保留

# ---------- 可选 OPTS ----------
write.tag("%OPTS_SECTION%")
write.str(title)                              # 不含 "&" 前缀
write.u32(0)                                  # ColorData 长度 0
write.u32(bg0)+u32(bg1)+u32(bg2)+u32(bg3)
write.u8(4)                                   # opvers
write.u8(0)                                   # Asub_cvs_script 数
write.u8(0)                                   # Aghost_script 数
write.u8(0)                                   # remember_export_path=false

# ---------- 可选 EXPT ----------
write.tag("%EXPT_SECTION%")
write.u32(2)                                  # 空 writeObject 长度
write.u16(0)                                  # 空对象终止符
```

要点：计数必须与实际条目严格一致；16 字节保留块不能省（缺了会把段名顶歪，容错扫描会置错误位）；
每个 EdImg 的 I/P 必须是 Flash Loader 能解析的 PNG 且尺寸一致；图层 key 必须命中图像表。

---

## 10. 仍需实测确认 / 风险点

1. **P 图层类型选择**：X 的 `type=1` 变换层在 P 格式里原样写 `type=1` 是否会让编辑器当"导入层"
   限制绘制（源码加载时 `ImportFrom` 为空，渲染不受影响）；备选 `type=4`（浮游层）或把变换烘焙进
   位图后写 `type=0`。三种在 PixelLiner UI 的差异需实际打开确认。
2. **P 图像 parts 语义**：按 `EDI.considerParts` 生成 `0xFF787878` 全遮罩，预计显示/编辑正常；
   缺 `%PTCL%` 时本来就用默认 parts 调色板，但"parts 绘画"结果需眼验。
3. **省略 OPTS/EXPT**：源码读路径显示可省（错误位仍 0），但导出设置/字幕等子窗口初始化是否依赖
   非空字段未实机确认；当前建议"带 OPTS、EXPT 空对象"以降低风险。
4. **id2 的 double 与 AS Number.toString**：加载端两次格式化同源，理论上无需模拟；实现里同一 key
   若写了两套不同 double 位模式会变成"找不到图像"。
5. **头后第一个段名** 必须是 IMGS/IMGD，读端不做"找第一个段"的通用扫描。
6. **group/子层顺序**：最小文件不需 group；完整转换若有 group 需保持"扁平列表 + preserve 数"。
7. **pinned 帧标志**：源码写 bit1，读端未还原（只读 important）。
8. **PNG 编码细节**：标准 32 位 RGBA PNG 应可被 `Loader.loadBytes` 接受，但未在 PixelLiner 实测。
9. **%IMGD% 压缩**：deflate/inflate 等价 Python `zlib.compress`；建议默认不压缩。

---

## 11. 附：关键源码索引

| 主题 | 文件:行 |
|---|---|
| 头部 key / 类型分派 | `EDT/EDF.as:44-46, 478-490`（`initPxlLoad` 附近） |
| 保存入口（加头） | `EDT/EdCsp.as:728-743` |
| writeToBytes / readFromBytes / progressLoad / readAfterData | `EDT/EdCsp.as:865-959, 961-1029, 1031-1097, 1104-1233` |
| ColorData 读写 | `EDT/EdCsp.as:1235-1246` |
| EdImg 序列化/反序列化/类型 | `EDT/utils/EdImg.as:37-41, 927-1095, 1253-1309, 1511-1541` |
| EdPose | `EDT/EdPose.as:825-929` |
| EdSequence | `EDT/utils/EdSequence.as:802-910` |
| EdAFrame / VERS_DEFAULT | `EDT/utils/EdAFrame.as:27, 574-635` |
| EdALayer / 类型位 / stabilize | `EDT/utils/EdALayer.as:20-36, 1420-1526, 1528-1542, 1736-1759` |
| EdGroupContainer | `EDT/utils/EdGroupContainer.as:364-418` |
| Str 编码工具 | `XX/Str.as`（按函数名搜索） |
| PXLS/PACK 读写 | `jp/clobau/pixelliner/pxls/PxlCharacter.as:84-138, 274-423, 442-460` |
| PXLS 图集 | `jp/clobau/pixelliner/pxls/PxlsImgAtlas.as:75-89, 209-229, 257-367, 384-424` |
| PXLS 打包器（margin/外部 PNG 序号） | `jp/clobau/pixelliner/pxls/PxlsImgPacker.as` |
| PXLS 导出器（段组装/外部 PNG 命名） | `EDT/utils/PxlsExporter.as:275-511, 514-522, 549-605` |
| PxlPose / PxlSequence / PxlFrame / PxlLayer | `jp/clobau/pixelliner/pxls/Pxl*.as` |
| PxlImage | `jp/clobau/pixelliner/pxls/PxlImage.as:81-216` |
| considerParts（P 图规则） | `EDT/EDI.as:2084-2097` |
| 备份/缓存（headerKey + writeToBytes） | `EDT/utils/BackupManager.as:173`；`EDI.as:1624-1626` |

参考实现与产物（本目录）：
- `minimal_pxl_reference.py`：最小 `.pxl` 生成 + 镜像解析自检；
- `minimal.pxl`：由脚本生成的 491 字节样本，可用于字节对照。

---

## 12. 附：最小样本 `minimal.pxl` 实测段偏移（491 字节）

| 偏移 | 内容 |
|---:|---|
| 0 | 51 字节 headerKey（`...cloba_u`） |
| 51 | `%IMGS_SECTION%`（14B） |
| 65 | u32 = 198（图像载荷长度） |
| 69 | u32 = 1（图像数） |
| 73 | EdImg：`16 00` + id=114514 + id2=998244353.0 + I(86B) + P(86B) |
| 267 | 16 字节 0（IMGS 后保留） |
| 283 | `%POSE_SECTION%`（14B） |
| 297 | u32 = 1（pose 数） |
| 301 | EdPose（vers=4, title=`Pose1`, cvw=cvh=128, 1 个 aim 0 序列，1 帧，1 图层） |
| 397 | str `Pose1`（curPoseTitle；u16 长度 5 在 397，文本在 399..403） |
| 404 | 16 字节 0（POSE 后保留） |
| 420 | `%OPTS_SECTION%`（14B） |
| 434 | OPTS：title=`MinimalTest`、ColorData 长 0、4×背景色、opvers=4、脚本数 0/0、remember=false |
| 471 | `%EXPT_SECTION%`（14B） |
| 485 | u32 = 2（空对象长） |
| 489 | `00 00`（空对象） |
| 491 | EOF |

---

> 本文件原为 issue #1 调查时产出的内部规范，收录进仓库供后续维护参考。
> 参考实现脚本见 docs/minimal_pxl_reference.py（需要 Pillow）。

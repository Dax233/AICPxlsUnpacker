
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
minimal_pxl_reference.py — PixelLiner 0.97.14 ".pxl" 工程文件最小可用样本生成器 + 反向校验器

用途：
  1) build_minimal() 生成一个结构完整、字段来自反编译源码的最小 .pxl（1 张图 / 1 pose / 1 序列 / 1 帧 / 1 图层）；
  2) parse_pxl() 用与 ActionScript 读取逻辑一一对应的镜像解析器复读刚写出的字节，做自检；
  3) 生成前可用 --out 指定输出路径。默认输出 minimal.pxl。

说明：这是"规范参考实现"，字段顺序/宽度逐条对应 FFDec 导出的 EDT/EdCsp.as、EdPose.as、
EdSequence.as、EdAFrame.as、EdALayer.as、EdImg.as、XX/Str.as。它不依赖 PixelLiner 运行，
因此只能证明"字节自洽"，不能替代在 PixelLiner 里实际打开验证。
"""

import argparse
import io
import struct

try:
    from PIL import Image
except Exception as e:  # pragma: no cover
    raise SystemExit("需要 Pillow: pip install pillow (%s)" % e)

# ---------------------------------------------------------------- 基础常量
HEADER_KEY = b"konnna_syarinn_no_saikaihatsu_ha_okashii_by_cloba_u"  # 51 bytes, EDF.headerKey
SCT_LEN = 14                      # 段标记长度，EdCsp.SCT_LEN
TAG_IMGS = b"%IMGS_SECTION%"      # 未压缩图像段
TAG_IMGD = b"%IMGD_SECTION%"      # deflate 压缩图像段
TAG_POSE = b"%POSE_SECTION%"
TAG_OPTS = b"%OPTS_SECTION%"
TAG_EXPT = b"%EXPT_SECTION%"
TYPE_ADD = 22                     # EdImg.TYPE_ADD
EDIMG_TYPE_LUSTER = 0
EDIMG_TYPE_VECTOR = 2
EDIMG_TYPE_LUSTER_VECTOR = 8
LAYER_TYPE_LUSTER = 0
LAYER_TYPE_IMPORT = 1
LAYER_TYPE_VECTOR = 2
LAYER_TYPE_FLOAT = 4
LAYER_TYPE_GROUP = 8
VERS_AFRAME = 3                   # EdAFrame.VERS_DEFAULT
VERS_EPOSE = 4                    # EdPose.writeToBytes 里硬编码的 byte(4)


# ---------------------------------------------------------------- 写工具（大端）
class W:
    def __init__(self):
        self.b = bytearray()

    def u8(self, v):  self.b += struct.pack(">B", v & 0xFF); return self
    def i8(self, v):  self.b += struct.pack(">b", v); return self
    def u16(self, v): self.b += struct.pack(">H", v & 0xFFFF); return self
    def i16(self, v): self.b += struct.pack(">h", int(v)); return self
    def u32(self, v): self.b += struct.pack(">I", v & 0xFFFFFFFF); return self
    def f64(self, v): self.b += struct.pack(">d", float(v)); return self
    def raw(self, b): self.b += bytes(b); return self
    def tag(self, t):
        assert len(t) == SCT_LEN
        return self.raw(t)

    def string(self, s):
        """Str.writeString: u16 长度(截断到 65535) + UTF-8 字节。"""
        enc = s.encode("utf-8")
        if len(enc) > 65535:
            enc = enc[:65535]
        return self.u16(len(enc)).raw(enc)


def png_bytes(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def make_images():
    """生成 1 张 4x4 图：I=正常色图；P=parts 色遮罩（不透明像素填 0xFF787878）。"""
    w = h = 4
    i_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # 画一个 2x2 的红色块，用来确认图片方向
    for y in range(1, 3):
        for x in range(1, 3):
            i_img.putpixel((x, y), (0xFF, 0x40, 0x40, 0xFF))
    p_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for y in range(h):
        for x in range(w):
            if i_img.getpixel((x, y))[3] != 0:
                # EDI.considerParts: 不透明像素 -> 0xFF787878
                p_img.putpixel((x, y), (0x78, 0x78, 0x78, 0xFF))
    return i_img, p_img


# ---------------------------------------------------------------- 各结构写出
def write_edimg(w: W, img_id: int, img_id2: float, png_i: bytes, png_p: bytes,
                img_type: int = EDIMG_TYPE_LUSTER, vers: int = 0):
    """EdImg.writeToBytes（type=0/8 luster 分支）。
    byte  type+22
    byte  vers (写 0；读取端当前不校验)
    u32   id
    f64   id2
    [type 带 luster 位时]
      u32 len + bytes   PNG(I)   -- 原图
      u32 len + bytes   PNG(P)   -- parts 色图；len 可以是 0 但会导致加载等不到 P 任务
    [type 带 vector 位时]
      f64 l2v_quality_; u32 len + EdVectorData 字节（最小文件不用）
    """
    w.u8(img_type + TYPE_ADD).u8(vers).u32(img_id).f64(img_id2)
    if img_type in (EDIMG_TYPE_LUSTER, EDIMG_TYPE_LUSTER_VECTOR):
        w.u32(len(png_i)).raw(png_i)
        w.u32(len(png_p)).raw(png_p)
    if img_type in (EDIMG_TYPE_VECTOR, EDIMG_TYPE_LUSTER_VECTOR):
        w.f64(3.0)      # l2v_quality_ 默认 3
        w.u32(0)        # 无矢量数据


def write_edlayer(w: W, img_id: int, img_id2: float, name: str, ltype: int = LAYER_TYPE_LUSTER,
                  alpha: float = 100.0, x: float = 0.0, y: float = 0.0,
                  zmx: float = 1.0, zmy: float = 1.0, rotR: float = 0.0,
                  blend_variable: int = 0, important: bool = False, pinned: bool = False):
    """EdALayer.writeToBytes（无 group / 无 ClipGetter 的情况）。
    注意：只有 type > 0 时才写 zmx/zmy/rotR 三个 f64；type==0 的图层在读取时
    会被 stabilizePosition 强制拉回 zmx=zmy=1, rotR=0（变换丢失）。
    """
    w.u32(img_id).f64(img_id2).u8(ltype)      # 图层引用图像 key
    w.string(name)
    w.i16(int(alpha * 100))                   # readShort()/100 并 clamp 0..100
    w.i16(int(x * 10))                        # 读取端 /10
    w.i16(int(y * 10))
    if ltype > 0:
        w.f64(zmx).f64(zmy).f64(rotR)
    w.i16(blend_variable & 0xFFFF)            # 低 8 位 lblend，高 8 位 ablend
    w.u32(0)                                  # reserved
    w.u8(0).u8(0)                             # reserved
    # 注：important/pinned 是帧级字段，不在这里序列化


def write_edframe(w: W, name: str, crf60: int, layers, important: bool = False, pinned: bool = False):
    """EdAFrame.writeToBytes:
      byte   VERS_DEFAULT(3)
      i16    countLayers
      i16    crf60
      str    name
      byte   flags = important | pinned<<1
      ...    layers
    """
    w.u8(VERS_AFRAME).i16(len(layers)).i16(crf60).string(name or "")
    w.u8((1 if important else 0) | (2 if pinned else 0))
    for L in layers:
        L(w)


def write_edsequence(w: W, width: int, height: int, frames, body=(0, 0), shift=(0, 0), loop_to=0,
                     sounds=(), stopped=True, cframe=0, loop_start=0, loop_end=1):
    """EdSequence.writeToBytes:
      byte 1
      i16  maisu (65535 表示 ignore_frames)
      i16  width, height          (读取用 readUShort)
      i16  bodyx, bodyy, shiftx, shifty, loop_to
      ...  frames
      i16  sound count + str*
      bool stopped
      i16  cframe
      i16  loop_start, loop_end  (读取端 vers>=1 才读，写 vers=1)
    """
    w.u8(1).i16(len(frames)).i16(width).i16(height)
    w.i16(body[0]).i16(body[1]).i16(shift[0]).i16(shift[1]).i16(loop_to)
    for F in frames:
        F(w)
    w.i16(len(sounds))
    for s in sounds:
        w.string(s or "")
    w.u8(1 if stopped else 0)
    w.i16(cframe).i16(loop_start).i16(loop_end)


def write_empty_object(w: W):
    """Str.writeObject(Ba, {}) 的结果：仅一个 u16=0 终止符。"""
    w.u16(0)


def write_edpose(w: W, title: str, cvw: int, cvh: int, sequences, aliases=(),
                 end_jump_title: str = "", data_auto_flip: bool = False, tetra_pose: bool = False,
                 auto_flip_flag: bool = False, comment: str = "", edit_layer: str = "",
                 end_jump_loop_count: int = 0):
    """EdPose.writeToBytes:
      byte 4 (vers)
      bool data_auto_flip
      str  title
      i16  cvw, cvh
      (byte aim+10, EdSequence)* ; byte 0 结束          <- 一个 pose 内最多 8 个 aim
      i16  alias count + str*
      str  end_jump_title
      i16  flags = writeFlags(tetra_pose, auto_flip)   (bit0=tetra, bit1=auto_flip)
      object Oadditional_var (空对象 = u16 0)
      str  comment
      str  edit_layer
      byte end_jump_loop_count
    """
    w.u8(VERS_EPOSE).u8(1 if data_auto_flip else 0).string(title)
    w.i16(cvw).i16(cvh)
    for aim, Sq in sequences:
        w.u8(10 + aim)
        Sq(w)
    w.u8(0)
    w.i16(len(aliases))
    for a in aliases:
        w.string(a)
    w.string(end_jump_title or "")
    flags = (1 if tetra_pose else 0) | (2 if auto_flip_flag else 0)
    w.i16(flags)
    write_empty_object(w)
    w.string(comment or "")
    w.string(edit_layer or "")
    w.u8(end_jump_loop_count & 0xFF)


# ---------------------------------------------------------------- 组装 .pxl
def build_minimal(title="MinimalTest", pose_title="Pose1", canvas=(128, 128),
                  img_id=114514, img_id2=998244353.0, img_type=EDIMG_TYPE_LUSTER):
    """返回完整 .pxl 字节（未压缩 %IMGS_SECTION% 变体）。

    文件总布局：
      [0]            EDF.headerKey (51B)
      [51]           %IMGS_SECTION% (14B)
      [65]           u32 imagesPayloadLen
      [69]           u32 imageCount
                     EdImg*
                     u32 x4 = 0  (16 字节保留)
      +              %POSE_SECTION% (14B)
                     u32 poseCount
                     EdPose*
                     str curPoseTitle
                     u32 x4 = 0  (16 字节保留)
      +              %OPTS_SECTION% ...（可选，本实现写出）
      +              %EXPT_SECTION% ...（可选，本实现写出）
    """
    i_img, p_img = make_images()
    png_i, png_p = png_bytes(i_img), png_bytes(p_img)

    # --- %IMGS_SECTION% 载荷 ---
    imgs = W().u32(1)
    write_edimg(imgs, img_id, img_id2, png_i, png_p, img_type=img_type)
    imgs_payload = imgs.b

    # --- %POSE_SECTION% 载荷 ---
    layer_w = W()
    write_edlayer(layer_w, img_id, img_id2, name="Layer", ltype=LAYER_TYPE_LUSTER,
                  alpha=100.0, x=0.0, y=0.0)
    frame_w = W()
    write_edframe(frame_w, name="", crf60=10, layers=[lambda w: w.raw(layer_w.b)])
    seq_w = W()
    write_edsequence(seq_w, width=canvas[0], height=canvas[1],
                     frames=[lambda w: w.raw(frame_w.b)], loop_end=1)

    pose_w = W()
    write_edpose(pose_w, title=pose_title, cvw=canvas[0], cvh=canvas[1],
                 sequences=[(0, lambda w: w.raw(seq_w.b))])
    pose_payload = W().u32(1).raw(pose_w.b)
    pose_payload = bytes(pose_payload.b) + bytes(W().string(pose_title).b) + b"\0" * 16

    # --- %OPTS_SECTION% ---
    opts = W().string(title)
    opts.u32(0)                        # ColorData 长度 = 0（读取端会退回默认调色板）
    opts.u32(0xFFFFFFFF).u32(0xFF808080).u32(0xFF404040).u32(0xFF202020)  # Abgcol[0..3]
    opts.u8(4)                         # opvers = 4
    opts.u8(0)                         # sub_cvs_script 数
    opts.u8(0)                         # ghost_script 数
    opts.u8(0)                         # remember_export_path = false
    opts_payload = bytes(opts.b)

    # --- %EXPT_SECTION% ---  u32 长度 + 空 writeObject
    expt = W(); write_empty_object(expt)
    expt_payload = bytes(expt.b)

    out = W()
    out.raw(HEADER_KEY)
    out.tag(TAG_IMGS).u32(len(imgs_payload)).raw(imgs_payload).raw(b"\0" * 16)
    out.tag(TAG_POSE).u32(1).raw(pose_w.b).string(pose_title).raw(b"\0" * 16)
    out.tag(TAG_OPTS).raw(opts_payload)
    out.tag(TAG_EXPT).u32(len(expt_payload)).raw(expt_payload)
    return bytes(out.b)


# ---------------------------------------------------------------- 镜像读取（自检）
class R:
    def __init__(self, b):
        self.b = b
        self.p = 0

    def u8(self):
        v = self.b[self.p]; self.p += 1; return v

    def i8(self):
        v = self.b[self.p]; self.p += 1
        return v - 256 if v > 127 else v

    def u16(self):
        v = struct.unpack_from(">H", self.b, self.p)[0]; self.p += 2; return v

    def i16(self):
        v = struct.unpack_from(">h", self.b, self.p)[0]; self.p += 2; return v

    def u32(self):
        v = struct.unpack_from(">I", self.b, self.p)[0]; self.p += 4; return v

    def f64(self):
        v = struct.unpack_from(">d", self.b, self.p)[0]; self.p += 8; return v

    def raw(self, n):
        v = self.b[self.p:self.p + n]; self.p += n; return v

    def string(self):
        n = self.u16()
        if n == 0:
            return ""
        v = self.b[self.p:self.p + n].decode("utf-8"); self.p += n; return v

    def left(self):
        return len(self.b) - self.p


def parse_edimg(r: R, log):
    t = r.i8() - TYPE_ADD
    vers = r.u8()
    img_id = r.u32()
    img_id2 = r.f64()
    rec = {"type": t, "vers": vers, "id": img_id, "id2": img_id2}
    if t in (EDIMG_TYPE_LUSTER, EDIMG_TYPE_LUSTER_VECTOR):
        il = r.u32(); rec["png_i_len"] = il; rec["png_i"] = r.raw(il)
        pl = r.u32(); rec["png_p_len"] = pl; rec["png_p"] = r.raw(pl)
    if t in (EDIMG_TYPE_VECTOR, EDIMG_TYPE_LUSTER_VECTOR):
        rec["quality"] = r.f64()
        vl = r.u32(); rec["vector"] = r.raw(vl)
    log.append(rec)
    return rec


def parse_edlayer(r: R, log):
    img_id = r.u32(); img_id2 = r.f64(); ltype = r.i8()
    name = r.string()
    alpha = r.i16() / 100.0
    rec = {"id": img_id, "id2": img_id2, "type": ltype, "name": name, "alpha": alpha}
    if ltype & LAYER_TYPE_GROUP:
        # EdGroupContainer.writeToBytes: byte vers(0), bool toggled, u32 preserve_contain_layers
        rec["group_vers"] = r.u8()
        rec["group_toggled"] = r.u8() != 0
        rec["group_preserve"] = r.u32()
    rec["x"] = r.i16() / 10.0
    rec["y"] = r.i16() / 10.0
    if ltype > 0:
        rec["zmx"] = r.f64(); rec["zmy"] = r.f64(); rec["rotR"] = r.f64()
    rec["blend_variable"] = r.u16()
    rec["reserved_u32"] = r.u32()
    rec["reserved_u8"] = (r.u8(), r.u8())
    log.append(rec)
    return rec


def parse_edframe(r: R, log):
    vers = r.u8()
    n = r.i16()
    crf60 = r.i16()
    name = r.string()
    flags = r.u8()
    rec = {"vers": vers, "layers": [], "crf60": crf60, "name": name,
           "important": bool(flags & 1), "pinned": bool(flags & 2)}
    for _ in range(n):
        rec["layers"].append(parse_edlayer(r, log))
    log.append(("frame", rec))
    return rec


def parse_edsequence(r: R, log):
    vers = r.u8()
    maisu = r.u16()
    ignore = maisu == 65535
    width = r.u16(); height = r.u16()
    bodyx, bodyy, shiftx, shifty, loop_to = (r.i16(), r.i16(), r.i16(), r.i16(), r.i16())
    rec = {"vers": vers, "maisu": maisu, "width": width, "height": height,
           "body": (bodyx, bodyy), "shift": (shiftx, shifty), "loop_to": loop_to, "frames": []}
    if not ignore:
        for _ in range(maisu):
            rec["frames"].append(parse_edframe(r, log))
    nsnd = r.u16()
    rec["sounds"] = [r.string() for _ in range(nsnd)]
    rec["stopped"] = r.u8() != 0
    rec["cframe"] = r.i16()
    if vers >= 1:
        rec["loop_start"] = r.u16()
        rec["loop_end"] = r.u16()
    log.append(("seq", rec))
    return rec


def parse_edpose(r: R, log):
    vers = r.u8()
    rec = {"vers": vers, "data_auto_flip": r.u8() != 0, "title": r.string()}
    if vers >= 1:
        rec["cvw"] = r.u16(); rec["cvh"] = r.u16()
    rec["sequences"] = []
    while True:
        a = r.u8()
        if a == 0:
            break
        rec["sequences"].append((a - 10, parse_edsequence(r, log)))
    n = r.i16()
    rec["aliases"] = [r.string() for _ in range(n)]
    rec["end_jump_title"] = r.string()
    rec["flags"] = r.i16()
    rec["additional_var"] = parse_object(r)
    if vers >= 2:
        rec["comment"] = r.string()
        if vers >= 3:
            rec["edit_layer"] = r.string()
            if vers >= 4:
                rec["end_jump_loop_count"] = r.u8()
    log.append(("pose", rec))
    return rec


def parse_object(r: R):
    """Str.readObject: (u16 keylen + key + u8 type + value)* u16 0"""
    obj = {}
    while True:
        klen = r.u16()
        if klen == 0:
            break
        key = r.raw(klen).decode("utf-8")
        t = r.u8()
        if t == 5: obj[key] = r.u32()
        elif t == 6: obj[key] = struct.unpack(">i", r.raw(4))[0]
        elif t == 7: obj[key] = r.string()
        elif t == 8: obj[key] = struct.unpack(">f", r.raw(4))[0]
        elif t == 9: obj[key] = r.f64()
        elif t == 4: obj[key] = r.u8() != 0
        elif t == 15: obj[key] = r.u16()
        elif t in (16,): obj[key] = r.i16()
        elif t == 25: obj[key] = r.u8()
        elif t == 26: obj[key] = r.i8()
        else: raise ValueError("unknown object value type %d" % t)
    return obj


def parse_pxl(data: bytes, verbose=True):
    r = R(data)
    log = []
    assert r.raw(len(HEADER_KEY)) == HEADER_KEY, "bad header"
    tag = r.raw(SCT_LEN)
    if tag == TAG_IMGS:
        compressed = False
    elif tag == TAG_IMGD:
        compressed = True
    else:
        raise AssertionError("first section is not IMGS/IMGD: %r" % tag)
    plen = r.u32()
    payload = r.raw(plen)
    if compressed:
        import zlib
        payload = zlib.decompress(payload)
    ir = R(payload)
    icount = ir.u32()
    images = [parse_edimg(ir, []) for _ in range(icount)]
    assert ir.left() == 0, "image payload leftover=%d" % ir.left()
    r.raw(16)
    assert r.raw(SCT_LEN) == TAG_POSE, "pose section missing"
    pcount = r.u32()
    poses = [parse_edpose(r, log) for _ in range(pcount)]
    cur_title = r.string()
    r.raw(16)
    opts = expt = None
    while r.left() > 0:
        tag = r.raw(SCT_LEN)
        if tag == TAG_OPTS:
            o = {"title": r.string()}
            cdlen = r.u32(); o["color_data"] = r.raw(cdlen)
            o["bgcol"] = [r.u32() for _ in range(4)]
            o["opvers"] = r.u8()
            o["sub_cvs_script"] = [r.string() for _ in range(r.u8())]
            if o["opvers"] >= 2:
                o["ghost_script"] = [r.string() for _ in range(r.u8())]
                if o["opvers"] >= 3:
                    o["remember_export_path"] = r.u8() != 0
                    if o["remember_export_path"]:
                        o["export_path"] = r.string()
            opts = o
        elif tag == TAG_EXPT:
            ln = r.u32()
            expt = parse_object(R(r.raw(ln)))
        else:
            raise AssertionError("unknown section %r at %d" % (tag, r.p - SCT_LEN))
    if verbose:
        print("== self-check ==")
        print(" header      :", HEADER_KEY.decode())
        print(" images      :", len(images), "entries; payload", plen, "bytes",
              "(compressed)" if compressed else "(raw)")
        for im in images:
            print("   key id=%d id2=%s type=%d I=%dB P=%dB" %
                  (im["id"], im["id2"], im["type"], im["png_i_len"], im["png_p_len"]))
        print(" poses       :", len(poses))
        p0 = poses[0]
        print("   pose[0]   : title=%r cv=%dx%d autoFlip=%s seq=%d aliases=%d" %
              (p0["title"], p0["cvw"], p0["cvh"], p0["data_auto_flip"],
               len(p0["sequences"]), len(p0["aliases"])))
        for aim, sq in p0["sequences"]:
            print("   aim=%d seq: %dx%d frames=%d loop=%d..%d" %
                  (aim, sq["width"], sq["height"], len(sq["frames"]),
                   sq["loop_start"], sq["loop_end"]))
            for fr in sq["frames"]:
                print("     frame: crf60=%d name=%r layers=%d" % (fr["crf60"], fr["name"], len(fr["layers"])))
                for L in fr["layers"]:
                    print("       layer: name=%r type=%d alpha=%.1f x=%.1f y=%.1f key=(%d,%s)" %
                          (L["name"], L["type"], L["alpha"], L["x"], L["y"], L["id"], L["id2"]))
        print(" curPose     :", repr(cur_title))
        print(" opts        :", "yes" if opts else "no",
              json_round(opts) if opts else "")
        print(" expt        :", repr(expt) if expt is not None else "no")
        print(" total bytes :", len(data))
    return {"images": images, "poses": poses, "cur_title": cur_title,
            "opts": opts, "expt": expt}


def json_round(o):
    return {k: (v if not isinstance(v, bytes) else ("<%dB>" % len(v))) for k, v in o.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="minimal.pxl")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    data = build_minimal()
    with open(args.out, "wb") as f:
        f.write(data)
    print("written:", args.out, len(data), "bytes")
    parse_pxl(data, verbose=not args.quiet)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""表情包一键导出工具（Windows）
支持：微信 4.x、QQ（QQNT 新版）、Telegram（官方接口）
- 微信：自动找到当前登录的微信号 -> 解密导出全部收藏表情
- QQ：  直接读取本地缓存的收藏表情、聊天里收到的表情（不加密，按真实格式还原）
- Telegram：用官方接口导出收藏贴纸 / 最近贴纸 / 保存的 GIF，统一转成 GIF（见 tg_export.py）
最后把所有 GIF 单独挑出来。
微信部分基于开源项目 Circumsized/Wechat-Emoticon-Export (MIT)。
"""
import glob
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT_ROOT = os.path.join(HERE, "导出结果")
X_LIMIT = 15 * 1024 * 1024  # X 的 GIF 上限

MAGIC = [(b"GIF8", "gif"), (b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpg"),
         (b"RIFF", "webp"), (b"BM", "bmp")]


def sniff(path):
    try:
        with open(path, "rb") as f:
            head = f.read(12)
    except OSError:
        return None
    for m, ext in MAGIC:
        if head.startswith(m):
            if ext == "webp" and head[8:12] != b"WEBP":
                continue
            return ext
    return None


def documents_dirs():
    """真实的「文档」位置（可能被挪到了 D 盘）+ 默认位置"""
    out = []
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        v, _ = winreg.QueryValueEx(k, "Personal")
        out.append(os.path.expandvars(v))
    except Exception:
        pass
    out.append(os.path.expanduser(r"~\Documents"))
    return out


def uniq_dirs(cands):
    seen, out = set(), []
    for c in cands:
        c = os.path.normpath(c)
        if c.lower() not in seen and os.path.isdir(c):
            seen.add(c.lower())
            out.append(c)
    return out


def process_running(exe):
    r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/NH"],
                       capture_output=True, text=True)
    return exe.lower() in r.stdout.lower()


def collect_gifs(src_dir, gif_dir):
    """把 src_dir 下所有 GIF 按内容去重后复制到 gif_dir，返回 (数量, 超 15MB 数量)"""
    os.makedirs(gif_dir, exist_ok=True)
    seen, n, big = set(), 0, 0
    for f in sorted(glob.glob(os.path.join(src_dir, "**", "*.gif"), recursive=True)):
        if os.path.dirname(f) == gif_dir:
            continue
        with open(f, "rb") as fh:
            h = hashlib.md5(fh.read()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        n += 1
        shutil.copy2(f, os.path.join(gif_dir, f"{n:03d}.gif"))
        if os.path.getsize(f) > X_LIMIT:
            big += 1
    return n, big


# ==================== 微信 ====================
def wechat_roots():
    cands = [os.path.join(d, "xwechat_files") for d in documents_dirs()]
    cands.append(os.path.expandvars(r"%USERPROFILE%\xwechat_files"))
    for ini in glob.glob(os.path.expandvars(r"%APPDATA%\Tencent\xwechat\config\*.ini")):
        try:
            p = open(ini, encoding="utf-8", errors="ignore").read().strip()
            if p and os.path.isdir(p):
                cands.insert(0, p if p.lower().endswith("xwechat_files") else os.path.join(p, "xwechat_files"))
        except OSError:
            pass
    for d in "CDEFGH":
        cands += [rf"{d}:\xwechat_files", rf"{d}:\Documents\xwechat_files"]
    return uniq_dirs(cands)


def latest_mtime(acc_dir):
    m = 0
    for f in glob.glob(os.path.join(acc_dir, "db_storage", "*", "*")):
        try:
            m = max(m, os.path.getmtime(f))
        except OSError:
            pass
    return m


def export_wechat():
    print("\n---------- 微信 ----------")
    if not process_running("Weixin.exe"):
        print("[跳过] 电脑微信没开。要导出微信表情，请先打开并登录微信。")
        return None
    accs = []
    for root in wechat_roots():
        for d in os.listdir(root):
            p = os.path.join(root, d)
            if d.startswith("wxid_") and os.path.isdir(os.path.join(p, "business", "emoticon")):
                accs.append(p)
    if not accs:
        print("[跳过] 没找到微信数据文件夹。")
        return None
    acc = max(accs, key=latest_mtime)  # 正在登录的号，数据库最近被写过
    import emoticon_export as ee
    wxid = ee.auto_wxid(acc)
    print(f"[*] 当前微信号数据: {acc}")
    out = os.path.join(OUT_ROOT, f"微信_{wxid}")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)
    ee.run_export(acc, wxid, ee.find_emoticon_dir(acc), out)
    gif_dir = os.path.join(out, "只看GIF动图")
    n, big = collect_gifs(out, gif_dir)
    return ("微信", wxid, n, big, gif_dir)


# ==================== QQ ====================
def qq_accounts():
    roots = uniq_dirs([os.path.join(d, "Tencent Files") for d in documents_dirs()] +
                      [rf"{d}:\Tencent Files" for d in "CDEFGH"])
    accs = []
    for root in roots:
        for d in os.listdir(root):
            emo = os.path.join(root, d, "nt_qq", "nt_data", "Emoji")
            if d.isdigit() and os.path.isdir(emo):
                accs.append((d, emo))
    return accs


def copy_sniffed(files, dst):
    os.makedirs(dst, exist_ok=True)
    seen, n = set(), 0
    for f in files:
        ext = sniff(f)
        if not ext:
            continue
        with open(f, "rb") as fh:
            h = hashlib.md5(fh.read()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        n += 1
        shutil.copy2(f, os.path.join(dst, f"{n:03d}.{ext}"))
    return n


def export_qq():
    print("\n---------- QQ ----------")
    accs = qq_accounts()
    if not accs:
        print("[跳过] 没找到 QQ 数据文件夹（只支持新版 QQ / QQNT）。")
        return []
    results = []
    for qq, emo in accs:
        out = os.path.join(OUT_ROOT, f"QQ_{qq}")
        shutil.rmtree(out, ignore_errors=True)
        fav = sorted(glob.glob(os.path.join(emo, "personal_emoji", "Ori", "*")))
        recv = sorted(glob.glob(os.path.join(emo, "emoji-recv", "*", "Ori", "*")))
        n_fav = copy_sniffed(fav, os.path.join(out, "收藏的表情"))
        n_recv = copy_sniffed(recv, os.path.join(out, "聊天收到的表情"))
        print(f"[*] QQ {qq}: 收藏 {n_fav} 个，聊天收到 {n_recv} 个")
        gif_dir = os.path.join(out, "只看GIF动图")
        n, big = collect_gifs(out, gif_dir)
        results.append(("QQ", qq, n, big, gif_dir))
    return results


def main():
    print("=" * 50)
    print("   表情包一键导出（微信 + QQ + Telegram）")
    print("=" * 50)
    results = []
    def export_tg():
        import tg_export
        return tg_export.export_telegram(OUT_ROOT, collect_gifs)

    for job in (export_wechat, export_qq, export_tg):
        try:
            r = job()
        except Exception as e:
            print(f"[!] 出错了: {e}")
            continue
        if isinstance(r, list):
            results += r
        elif r:
            results.append(r)

    print("\n" + "=" * 50)
    if not results:
        print("  什么都没导出来。微信要先登录；QQ 需要新版 QQ；Telegram 要先运行「设置Telegram.bat」。")
    for app, acc, n, big, gif_dir in results:
        print(f"  {app} {acc}: {n} 个 GIF -> {gif_dir}")
        if big:
            print(f"    注意: {big} 个超过 15MB，X 上发不了")
    print("=" * 50)
    if results:
        os.startfile(OUT_ROOT)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[!] 出错了: {e}")
    print()
    os.system("pause")

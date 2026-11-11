# -*- coding: utf-8 -*-
"""微信表情包一键导出工具（Windows 微信 4.x）
自动找到当前登录的微信号 -> 解密导出全部收藏表情 -> 把 GIF 单独挑出来。
基于开源项目 Circumsized/Wechat-Emoticon-Export (MIT)。
"""
import glob
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def documents_dir():
    """读取注册表里真实的「文档」位置（可能被挪到了 D 盘）"""
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        v, _ = winreg.QueryValueEx(k, "Personal")
        return os.path.expandvars(v)
    except Exception:
        return os.path.expanduser(r"~\Documents")


def find_roots():
    cands = [os.path.join(documents_dir(), "xwechat_files"),
             os.path.expandvars(r"%USERPROFILE%\Documents\xwechat_files"),
             os.path.expandvars(r"%USERPROFILE%\xwechat_files")]
    # 微信配置文件里可能写着自定义存储位置
    for ini in glob.glob(os.path.expandvars(r"%APPDATA%\Tencent\xwechat\config\*.ini")):
        try:
            p = open(ini, encoding="utf-8", errors="ignore").read().strip()
            if p and os.path.isdir(p):
                cands.insert(0, p if p.lower().endswith("xwechat_files") else os.path.join(p, "xwechat_files"))
        except OSError:
            pass
    for d in "CDEFGH":
        cands += [rf"{d}:\xwechat_files", rf"{d}:\Documents\xwechat_files"]
    seen, out = set(), []
    for c in cands:
        c = os.path.normpath(c)
        if c.lower() not in seen and os.path.isdir(c):
            seen.add(c.lower())
            out.append(c)
    return out


def latest_mtime(acc_dir):
    m = 0
    for f in glob.glob(os.path.join(acc_dir, "db_storage", "*", "*")):
        try:
            m = max(m, os.path.getmtime(f))
        except OSError:
            pass
    return m


def pick_account():
    accs = []
    for root in find_roots():
        for d in os.listdir(root):
            p = os.path.join(root, d)
            if d.startswith("wxid_") and os.path.isdir(os.path.join(p, "business", "emoticon")):
                accs.append(p)
    if not accs:
        return None
    # 正在登录的号，数据库文件最近被写过
    return max(accs, key=latest_mtime)


def wechat_running():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/NH"],
                       capture_output=True, text=True)
    return "Weixin.exe" in r.stdout


def main():
    print("=" * 46)
    print("   微信表情包一键导出")
    print("=" * 46)
    if not wechat_running():
        print("\n[!] 电脑微信没开。请先打开并登录微信，再运行本工具。")
        return
    acc = pick_account()
    if not acc:
        print("\n[!] 没找到微信数据文件夹。")
        return
    import emoticon_export as ee
    wxid = ee.auto_wxid(acc)
    print(f"\n[*] 当前微信号数据: {acc}")
    out = os.path.join(HERE, "导出结果", wxid)
    if os.path.isdir(out):
        shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)

    ee.run_export(acc, wxid, ee.find_emoticon_dir(acc), out)

    # 把 GIF 单独挑出来
    gif_dir = os.path.join(out, "只看GIF动图")
    os.makedirs(gif_dir, exist_ok=True)
    n = 0
    for sub in ("favorite", "store", "unknown"):
        for f in sorted(glob.glob(os.path.join(out, sub, "**", "*.gif"), recursive=True)):
            n += 1
            shutil.copy2(f, os.path.join(gif_dir, f"{n:03d}.gif"))
    big = [f for f in glob.glob(os.path.join(gif_dir, "*.gif")) if os.path.getsize(f) > 15 * 1024 * 1024]
    print("\n" + "=" * 46)
    print(f"  完成！共 {n} 个 GIF 动图 -> {gif_dir}")
    if big:
        print(f"  注意: {len(big)} 个超过 15MB，X 上发不了")
    print("=" * 46)
    os.startfile(gif_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[!] 出错了: {e}")
    print()
    os.system("pause")

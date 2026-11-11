# -*- coding: utf-8 -*-
"""Telegram 贴纸 / GIF 导出（走 Telegram 官方接口，不碰本地加密缓存）

导出：收藏的贴纸、最近用过的贴纸、保存的 GIF，统一转成 GIF（静态贴纸转 PNG）。
首次使用先运行「设置Telegram.bat」：填 api_id / api_hash，并用手机验证码登录一次。
登录信息保存在本文件夹的 tg.session 里，相当于你的 Telegram 登录状态，不要发给任何人。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, "tg_config.txt")
SESSION = os.path.join(HERE, "tg")  # -> tg.session


# ---------- 配置 ----------
def load_conf():
    if not os.path.isfile(CONF):
        return None
    d = {}
    for line in open(CONF, encoding="utf-8"):
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    if d.get("api_id", "").isdigit() and d.get("api_hash"):
        return int(d["api_id"]), d["api_hash"]
    return None


def system_proxy():
    """读取 Windows 系统代理（Clash / v2rayN 等开了「系统代理」时会写在这里）"""
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        if not winreg.QueryValueEx(k, "ProxyEnable")[0]:
            return None
        srv = winreg.QueryValueEx(k, "ProxyServer")[0]
    except Exception:
        return None
    # 形如 127.0.0.1:7890 或 http=127.0.0.1:7890;https=...
    if "=" in srv:
        parts = dict(p.split("=", 1) for p in srv.split(";") if "=" in p)
        srv = parts.get("https") or parts.get("http") or next(iter(parts.values()), "")
    srv = srv.replace("http://", "").strip()
    if ":" not in srv:
        return None
    host, port = srv.rsplit(":", 1)
    if not port.isdigit():
        return None
    return ("http", host, int(port))


def make_client():
    from telethon.sync import TelegramClient
    conf = load_conf()
    if not conf:
        return None
    proxy = system_proxy()
    if proxy:
        print(f"[*] 使用系统代理 {proxy[1]}:{proxy[2]} 连接 Telegram")
    return TelegramClient(SESSION, conf[0], conf[1], proxy=proxy)


# ---------- 格式转换 ----------
def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def video_to_gif(src, dst, alpha=False):
    ff = ffmpeg_exe()
    if not ff:
        return False
    pre = ["-c:v", "libvpx-vp9"] if alpha else []  # webm 贴纸带透明通道
    vf = ("fps=20,scale='min(512,iw)':-1:flags=lanczos,split[a][b];"
          "[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse")
    r = subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", *pre, "-i", src,
                        "-vf", vf, "-loop", "0", dst],
                       capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 and alpha:  # 某些 webm 不是 vp9，退回默认解码器
        return video_to_gif(src, dst, alpha=False)
    return r.returncode == 0 and os.path.isfile(dst)


def tgs_to_gif(src, dst):
    try:
        from rlottie_python import LottieAnimation
        anim = LottieAnimation.from_tgs(src)
        anim.save_animation(dst)
        return os.path.isfile(dst)
    except Exception as e:
        print(f"  ! 动画贴纸转换失败: {e}")
        return False


def webp_to_png(src, dst):
    try:
        from PIL import Image
        Image.open(src).save(dst)
        return True
    except Exception:
        return False


def convert(raw, mime, base):
    """raw: 下载下来的原始文件。返回最终文件路径或 None"""
    if mime == "application/x-tgsticker":
        out = base + ".gif"
        ok = tgs_to_gif(raw, out)
    elif mime == "video/webm":
        out = base + ".gif"
        ok = video_to_gif(raw, out, alpha=True)
    elif mime == "video/mp4":
        out = base + ".gif"
        ok = video_to_gif(raw, out)
    elif mime == "image/webp":
        out = base + ".png"
        ok = webp_to_png(raw, out)
    elif mime == "image/gif":
        out = base + ".gif"
        os.replace(raw, out)
        return out
    else:
        return None
    try:
        os.remove(raw)
    except OSError:
        pass
    return out if ok else None


# ---------- 导出 ----------
def dl_list(client, docs, dst):
    os.makedirs(dst, exist_ok=True)
    seen, n = set(), 0
    for doc in docs:
        if doc.id in seen:
            continue
        seen.add(doc.id)
        n += 1
        base = os.path.join(dst, f"{n:03d}")
        raw = base + ".raw"
        try:
            client.download_media(doc, file=raw)
        except Exception as e:
            print(f"  ! 下载失败: {e}")
            n -= 1
            continue
        if not convert(raw, doc.mime_type, base):
            n -= 1
        print(f"\r  {os.path.basename(dst)}: {n} 个", end="", flush=True)
    print()
    return n


def export_telegram(out_root, collect_gifs):
    print("\n---------- Telegram ----------")
    if not load_conf() or not os.path.isfile(SESSION + ".session"):
        print("[跳过] 还没设置 Telegram。要导出 Telegram 贴纸，先双击「设置Telegram.bat」。")
        return None
    from telethon.tl import functions
    client = make_client()
    client.connect()
    if not client.is_user_authorized():
        client.disconnect()
        print("[跳过] Telegram 登录已失效，请重新运行「设置Telegram.bat」。")
        return None
    me = client.get_me()
    name = me.username or str(me.id)
    out = os.path.join(out_root, f"Telegram_{name}")
    import shutil
    shutil.rmtree(out, ignore_errors=True)

    fav = client(functions.messages.GetFavedStickersRequest(hash=0)).stickers
    recent = client(functions.messages.GetRecentStickersRequest(hash=0)).stickers
    gifs = client(functions.messages.GetSavedGifsRequest(hash=0)).gifs
    print(f"[*] 收藏贴纸 {len(fav)}，最近用过 {len(recent)}，保存的 GIF {len(gifs)}，开始下载并转换 ...")
    dl_list(client, fav, os.path.join(out, "收藏的贴纸"))
    dl_list(client, recent, os.path.join(out, "最近用过的贴纸"))
    dl_list(client, gifs, os.path.join(out, "保存的GIF"))
    client.disconnect()

    gif_dir = os.path.join(out, "只看GIF动图")
    n, big = collect_gifs(out, gif_dir)
    return ("Telegram", name, n, big, gif_dir)


# ---------- 首次设置 ----------
def setup():
    print("=" * 50)
    print("   Telegram 设置（只需要做一次）")
    print("=" * 50)
    print("\n第 1 步：打开 https://my.telegram.org ，用手机号登录，")
    print("        点 API development tools，随便填个名字创建，")
    print("        页面上会显示 api_id（一串数字）和 api_hash（一串字母数字）。\n")
    conf = load_conf()
    if conf:
        print(f"[*] 已有配置 api_id={conf[0]}，直接登录。（要换就删掉 tg_config.txt 再运行）")
    else:
        api_id = input("请粘贴 api_id: ").strip()
        api_hash = input("请粘贴 api_hash: ").strip()
        if not api_id.isdigit() or len(api_hash) < 16:
            print("[!] 格式不对，api_id 应该是纯数字，api_hash 是 32 位字母数字。")
            return
        with open(CONF, "w", encoding="utf-8") as f:
            f.write(f"api_id={api_id}\napi_hash={api_hash}\n")
    print("\n第 2 步：登录。按提示输入手机号（带国家码，如 +8613800000000），")
    print("        然后输入 Telegram 发给你的验证码。设了二步验证的还要输密码。\n")
    client = make_client()
    client.start()
    me = client.get_me()
    print(f"\n[OK] 登录成功：{me.first_name or ''} (@{me.username or me.id})")
    print("以后双击「一键导出表情包.bat」就会自动导出 Telegram 贴纸。")
    print("注意：tg.session 文件就是你的登录状态，不要发给任何人。")
    client.disconnect()


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "setup":
    try:
        setup()
    except Exception as e:
        print(f"\n[!] 出错了: {e}")
        print("如果连不上，请确认代理软件（如 Clash）已开启「系统代理」。")
    print()
    os.system("pause")

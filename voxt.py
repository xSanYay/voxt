#!/usr/bin/env python3
"""voxt — video → transcript via ffmpeg + whisper-cli"""

import subprocess
import sys
import os
import platform

CONFIG_FILE = os.path.expanduser("~/.config/voxt/config")

# ── config ────────────────────────────────────────────────────────────────────

def read_config():
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
    return config


def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        for k, v in config.items():
            f.write(f"{k} = {v}\n")


def ask_path(label, hint=""):
    prompt = f"  {label} path"
    if hint:
        prompt += f" (e.g. {hint})"
    prompt += ": "
    while True:
        path = input(prompt).strip()
        path = os.path.expanduser(path)
        if os.path.exists(path):
            return path
        print(f"  ✗ not found: {path} — try again")


def resolve(name, arg_value, config_key, hint, config):
    if arg_value:
        path = os.path.expanduser(arg_value)
        if os.path.exists(path):
            return path
        print(f"✗ {name} not found at: {path}")
        sys.exit(1)
    if config_key in config:
        path = os.path.expanduser(config[config_key])
        if os.path.exists(path):
            return path
        print(f"⚠  saved {name} path no longer valid: {path}")
    print(f"\n{name} not configured — please enter the path:")
    path = ask_path(name, hint)
    config[config_key] = path
    save_config(config)
    print(f"  ✓ saved to {CONFIG_FILE}")
    return path


# ── pipeline ──────────────────────────────────────────────────────────────────

def run(cmd, label):
    print(f"\n▶ {label}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"✗ {label} failed (exit {result.returncode})")
        sys.exit(result.returncode)
    print(f"✓ {label} done")


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_help():
    print("""
voxt — video to transcript

USAGE
  voxt <video>              transcribe a video file
  voxt install              install voxt as a command (run once from the repo)
  voxt setup                guided setup (install or locate ffmpeg + whisper)
  voxt help                 show this help
  voxt config               show current saved config
  voxt set-whisper          update whisper-cli path
  voxt set-model            update model path

OPTIONS (override saved config for one run)
  voxt <video> --model   /path/to/model.bin
  voxt <video> --whisper /path/to/whisper-cli

OUTPUT
  transcript saved as <video>.txt in the same folder

EXAMPLES
  python3 voxt.py install   <- first time only, then just use 'voxt'
  voxt episode.mp4
  voxt clip.mkv --model ~/models/ggml-large.bin
  voxt setup
  voxt config
""")


def cmd_install():
    os_name  = detect_os()
    src      = os.path.abspath(__file__)   # wherever voxt.py lives right now

    if os_name == "windows":
        # on Windows: create a voxt.bat in a directory that's on PATH
        # best cross-user choice is the Python Scripts folder
        import sysconfig
        scripts_dir = sysconfig.get_path("scripts")
        wrapper     = os.path.join(scripts_dir, "voxt.bat")
        content     = f'@echo off\npython "{src}" %*\n'
        try:
            with open(wrapper, "w") as f:
                f.write(content)
            print(f"✓ installed  →  {wrapper}")
            print("  open a new terminal and run: voxt help")
        except PermissionError:
            print(f"✗ permission denied writing to {scripts_dir}")
            print(f"  try running this as Administrator, or manually copy:")
            print(f'  echo @echo off > "{wrapper}"')
            print(f'  echo python "{src}" %* >> "{wrapper}"')
        return

    # mac / linux: write a shell wrapper to /usr/local/bin/voxt
    wrapper = "/usr/local/bin/voxt"
    content = f'#!/bin/sh\nexec python3 "{src}" "$@"\n'

    try:
        with open(wrapper, "w") as f:
            f.write(content)
        os.chmod(wrapper, 0o755)
        print(f"✓ installed  →  {wrapper}")
        print("  open a new terminal and run: voxt help")
    except PermissionError:
        # offer to retry with sudo
        print(f"  needs permission to write to {wrapper}")
        print(f"  will run: sudo tee {wrapper}")
        ans = input("  ok? [y/n]: ").strip().lower()
        if ans not in ("y", "yes"):
            print("  skipped — you can install manually:")
            print(f'  echo \'#!/bin/sh\\nexec python3 "{src}" "$@"\' | sudo tee {wrapper} && sudo chmod +x {wrapper}')
            return
        cmd = f'echo \'#!/bin/sh\nexec python3 "{src}" "$@"\' | sudo tee {wrapper} && sudo chmod +x {wrapper}'
        result = subprocess.run(cmd, shell=True)
        if result.returncode == 0:
            print(f"✓ installed  →  {wrapper}")
            print("  open a new terminal and run: voxt help")
        else:
            print("✗ install failed — try manually:")
            print(f'  echo \'#!/bin/sh\\nexec python3 "{src}" "$@"\' | sudo tee {wrapper} && sudo chmod +x {wrapper}')


def cmd_config():
    config = read_config()
    if not config:
        print(f"no config saved yet  ({CONFIG_FILE})")
        return
    print(f"\nconfig  →  {CONFIG_FILE}\n")
    for k, v in config.items():
        exists = "✓" if os.path.exists(os.path.expanduser(v)) else "✗ missing"
        print(f"  {k:<12} {v}  [{exists}]")
    print()


def cmd_set_whisper():
    config = read_config()
    print("enter new whisper-cli path:")
    path = ask_path("whisper-cli", "/opt/homebrew/bin/whisper-cli")
    config["whisper"] = path
    save_config(config)
    print(f"✓ saved")


def cmd_set_model():
    config = read_config()
    print("enter new model path:")
    path = ask_path("model (.bin)", "~/models/ggml-base.en.bin")
    config["model"] = path
    save_config(config)
    print(f"✓ saved")


def detect_os():
    s = platform.system()
    if s == "Darwin":  return "mac"
    if s == "Linux":   return "linux"
    if s == "Windows": return "windows"
    return "unknown"


def verify_binary(path, flag="-version"):
    try:
        r = subprocess.run([path, flag], capture_output=True, text=True, timeout=10)
        out = (r.stdout + r.stderr).strip().splitlines()
        return r.returncode == 0, out[0] if out else ""
    except Exception as e:
        return False, str(e)


def ask_yes_no(question):
    while True:
        ans = input(f"{question} [y/n]: ").strip().lower()
        if ans in ("y", "yes"): return True
        if ans in ("n", "no"):  return False


def install_ffmpeg(os_name):
    cmds = {
        "mac":     "brew install ffmpeg",
        "linux":   "sudo apt install ffmpeg",
        "windows": "winget install ffmpeg",
    }
    cmd = cmds.get(os_name)
    if not cmd:
        print("  ✗ unknown OS — install ffmpeg manually and re-run voxt setup")
        return False
    print(f"\n  will run:  {cmd}")
    if not ask_yes_no("  ok to run this?"):
        print("  skipped — install ffmpeg manually and re-run voxt setup")
        return False
    print()
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("  ✗ install failed — check the output above")
        return False
    print("  ✓ ffmpeg installed")
    return True


def install_whisper(os_name):
    cmds = {
        "mac":     "brew install whisper-cpp",
        "linux":   "sudo apt install whisper-cpp",
        "windows": "winget install whisper-cpp",
    }
    cmd = cmds.get(os_name)
    if not cmd:
        print("  ✗ unknown OS — install whisper-cpp manually and re-run voxt setup")
        return False
    print(f"\n  will run:  {cmd}")
    if not ask_yes_no("  ok to run this?"):
        print("  skipped — install whisper-cpp manually and re-run voxt setup")
        return False
    print()
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("  ✗ install failed — check the output above")
        return False
    print("  ✓ whisper-cpp installed")
    return True


def cmd_setup():
    os_name = detect_os()
    config  = read_config()

    print("\n── voxt setup ───────────────────────────────────────\n")

    # ── ffmpeg ────────────────────────────────────────────
    print("[ ffmpeg ]")
    already = ask_yes_no("  already installed?")

    if already:
        ffmpeg_path = input("  ffmpeg path (leave blank for 'ffmpeg' in PATH): ").strip()
        ffmpeg_path = ffmpeg_path or "ffmpeg"
        ok, info = verify_binary(ffmpeg_path, "-version")
        if ok:
            print(f"  ✓ {info}")
        else:
            print(f"  ✗ could not run ffmpeg: {info}")
            print("  check the path and try again, or re-run voxt setup")
            sys.exit(1)
    else:
        ok = install_ffmpeg(os_name)
        if not ok:
            sys.exit(1)
        ffmpeg_path = "ffmpeg"
        ok, info = verify_binary(ffmpeg_path, "-version")
        if ok:
            print(f"  ✓ verified: {info}")
        else:
            print(f"  ✗ installed but still can't run ffmpeg — try opening a new terminal")
            sys.exit(1)

    # ── whisper-cli ───────────────────────────────────────
    print("\n[ whisper-cli ]")
    already = ask_yes_no("  already installed?")

    if already:
        whisper_path = input("  whisper-cli path (e.g. /opt/homebrew/bin/whisper-cli): ").strip()
        whisper_path = os.path.expanduser(whisper_path)
        ok, info = verify_binary(whisper_path, "--help")
        if ok or "usage" in info.lower() or "whisper" in info.lower():
            print(f"  ✓ found: {whisper_path}")
        else:
            print(f"  ✗ could not run whisper-cli: {info}")
            sys.exit(1)
    else:
        ok = install_whisper(os_name)
        if not ok:
            sys.exit(1)
        candidates = [
            "/opt/homebrew/bin/whisper-cli",
            "/usr/local/bin/whisper-cli",
            "/usr/bin/whisper-cli",
        ]
        whisper_path = None
        for c in candidates:
            if os.path.exists(c):
                whisper_path = c
                break
        if not whisper_path:
            print("  installed — enter the whisper-cli path:")
            whisper_path = ask_path("whisper-cli", "/opt/homebrew/bin/whisper-cli")
        print(f"  ✓ found: {whisper_path}")

    # ── model ─────────────────────────────────────────────
    print("\n[ model (.bin) ]")
    print("  enter the path to your ggml model file:")
    model_path = ask_path("model", "~/models/ggml-base.en.bin")
    if not model_path.endswith(".bin"):
        print("  ⚠  that doesn't look like a .bin file — continuing anyway")
    else:
        print(f"  ✓ found: {model_path}")

    # ── save ─────────────────────────────────────────────
    config["whisper"] = whisper_path
    config["model"]   = model_path
    save_config(config)

    print(f"\n✓ setup complete — config saved to {CONFIG_FILE}")
    print(f"\n  whisper  {whisper_path}")
    print(f"  model    {model_path}")
    print("\nrun:  voxt <video_file>\n")


def cmd_transcribe(video, model_arg=None, whisper_arg=None):
    if not os.path.exists(video):
        print(f"✗ file not found: {video}")
        sys.exit(1)

    config = read_config()
    whisper = resolve("whisper-cli", whisper_arg, "whisper", "/opt/homebrew/bin/whisper-cli", config)
    model   = resolve("model (.bin)", model_arg,   "model",   "~/models/ggml-base.en.bin",    config)

    base    = os.path.splitext(video)[0]
    audio   = base + "_audio.wav"
    out_txt = base + ".txt"

    run([
        "ffmpeg", "-y", "-i", video,
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        audio,
    ], "ffmpeg: extract audio")

    run([
        whisper, "-m", model, "-f", audio,
        "--output-txt", "-of", base,
    ], "whisper: transcribe")

    if os.path.exists(out_txt):
        print(f"\n📄 transcript → {out_txt}  ({os.path.getsize(out_txt):,} bytes)")
    else:
        print("\n⚠  whisper finished but .txt not found")

    os.remove(audio)
    print(f"🗑  removed {audio}")


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args or args[0] in ("help", "--help", "-h"):
        cmd_help()
        return

    if args[0] == "install":
        cmd_install()
        return

    if args[0] == "setup":
        cmd_setup()
        return

    if args[0] == "config":
        cmd_config()
        return

    if args[0] == "set-whisper":
        cmd_set_whisper()
        return

    if args[0] == "set-model":
        cmd_set_model()
        return

    # transcribe
    video       = args[0]
    model_arg   = None
    whisper_arg = None

    i = 1
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model_arg = args[i + 1]; i += 2
        elif args[i] == "--whisper" and i + 1 < len(args):
            whisper_arg = args[i + 1]; i += 2
        else:
            print(f"✗ unknown argument: {args[i]}")
            cmd_help()
            sys.exit(1)

    cmd_transcribe(video, model_arg, whisper_arg)


if __name__ == "__main__":
    main()
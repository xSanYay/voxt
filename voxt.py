#!/usr/bin/env python3
import subprocess
import sys
import os

CONFIG_FILE = os.path.expanduser("~/.config/voxt/config")

# -- config ---------------------------------------------------------------

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
        print(f"  X not found: {path} - try again")


def resolve(name, arg_value, config_key, hint, config):
    if arg_value:
        path = os.path.expanduser(arg_value)
        if os.path.exists(path):
            return path
        print(f"X {name} not found at: {path}")
        sys.exit(1)
    if config_key in config:
        path = os.path.expanduser(config[config_key])
        if os.path.exists(path):
            return path
        print(f" saved {name} path no longer valid: {path}")
    print(f"\n{name} not configured - please enter the path:")
    path = ask_path(name, hint)
    config[config_key] = path
    save_config(config)
    print(f" saved to {CONFIG_FILE}")
    return path


# -- pipeline --------------------------------------------------------------

def run(cmd, label):
    print(f"\n> {label}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"X {label} failed (exit {result.returncode})")
        sys.exit(result.returncode)
    print(f"OK {label} done")


# -- commands --------------------------------------------------------------

def cmd_help():
    print("""
voxt - video to transcript

USAGE
  voxt <video>              transcribe a video file
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
  voxt episode.mp4
  voxt clip.mkv --model ~/models/ggml-large.bin
  voxt config
""")


def cmd_config():
    config = read_config()
    if not config:
        print(f"no config saved yet  ({CONFIG_FILE})")
        return
    print(f"\nconfig  ->  {CONFIG_FILE}\n")
    for k, v in config.items():
        exists = "OK" if os.path.exists(os.path.expanduser(v)) else "X missing"
        print(f"  {k:<12} {v}  [{exists}]")
    print()


def cmd_set_whisper():
    config = read_config()
    print("enter new whisper-cli path:")
    path = ask_path("whisper-cli", "/opt/homebrew/bin/whisper-cli")
    config["whisper"] = path
    save_config(config)
    print(f"OK saved")


def cmd_set_model():
    config = read_config()
    print("enter new model path:")
    path = ask_path("model (.bin)", "~/models/ggml-base.en.bin")
    config["model"] = path
    save_config(config)
    print(f"OK saved")


def cmd_transcribe(video, model_arg=None, whisper_arg=None):
    if not os.path.exists(video):
        print(f"X file not found: {video}")
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
        print(f"\n transcript -> {out_txt}  ({os.path.getsize(out_txt):,} bytes)")
    else:
        print("\n whisper finished but .txt not found")

    os.remove(audio)
    print(f" removed {audio}")


# -- entry point ----------------------------------------------------------

def main():
    args = sys.argv[1:]

    if not args or args[0] in ("help", "--help", "-h"):
        cmd_help()
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
    video      = args[0]
    model_arg  = None
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
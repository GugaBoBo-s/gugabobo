import pathlib
import subprocess

# --- config.py: add telegram_proxy field after telegram_group_wake_words ---
cfg = pathlib.Path("/opt/gugabobo/repo/src/gugabobo/config.py")
t = cfg.read_text(encoding="utf-8")
if "telegram_proxy" not in t:
    anchor = '    telegram_group_wake_words: str = "gugabobo,咕嘎BoBo"\n'
    assert anchor in t, "config anchor not found"
    t = t.replace(anchor, anchor + '    telegram_proxy: str = ""\n')
    cfg.write_text(t, encoding="utf-8")
    print("config.py: added telegram_proxy")
else:
    print("config.py: telegram_proxy already present")

# --- telegram_client.py: add _proxy property + pass proxy to httpx.Client ---
tc = pathlib.Path("/opt/gugabobo/repo/src/gugabobo/infra/telegram_client.py")
s = tc.read_text(encoding="utf-8")

if "_proxy" not in s:
    base_prop_end = (
        '        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}"\n'
    )
    assert base_prop_end in s, "base_url anchor not found"
    prop = base_prop_end + (
        "\n"
        "    @property\n"
        "    def _proxy(self) -> str | None:\n"
        "        return self.settings.telegram_proxy or None\n"
    )
    s = s.replace(base_prop_end, prop, 1)

s = s.replace(
    "with httpx.Client(timeout=35) as client:",
    "with httpx.Client(timeout=35, proxy=self._proxy) as client:",
)
s = s.replace(
    "with httpx.Client(timeout=timeout, follow_redirects=True) as client:",
    "with httpx.Client(timeout=timeout, follow_redirects=True, proxy=self._proxy) as client:",
)
tc.write_text(s, encoding="utf-8")
print("telegram_client.py patched")

print("--- grep proxy in telegram_client ---")
print(subprocess.run(["grep", "-n", "proxy", str(tc)], capture_output=True, text=True).stdout)
print("--- grep telegram_proxy in config ---")
print(subprocess.run(["grep", "-n", "telegram_proxy", str(cfg)], capture_output=True, text=True).stdout)

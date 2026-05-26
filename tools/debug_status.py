import json
import os
import re
import urllib.request
import ssl

cli_root = os.path.expanduser("~/.gemini/antigravity-cli")
settings_path = os.path.join(cli_root, "settings.json")
log_path = os.path.join(cli_root, "cli.log")
ssl_context = ssl._create_unverified_context()

def get_rpc_port():
    if not os.path.exists(log_path):
        return None
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for line in reversed(lines):
            match = re.search(r"Language server listening on random port at (\d+) for HTTPS \(gRPC\)", line)
            if match:
                return int(match.group(1))
    except Exception as e:
        pass
    return None

def query_user_status(port):
    if not port:
        return None
    url = f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
    headers = {
        'Content-Type': 'application/json',
        'Connect-Protocol-Version': '1',
        'X-Codeium-Csrf-Token': '00000000-0000-0000-0000-000000000000'
    }
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers=headers,
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, context=ssl_context, timeout=2) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        return str(e)

port = get_rpc_port()
print(f"Port: {port}")
status = query_user_status(port)
print(json.dumps(status, indent=2))

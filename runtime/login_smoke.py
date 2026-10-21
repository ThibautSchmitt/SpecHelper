"""Verify an official browser authorization can start. Does not sign into an account."""

import json
import sys
import time
from urllib.parse import parse_qs, urlsplit

from core.login import ACTIVE, TerminalLogin

provider = sys.argv[1]
output = []
login = TerminalLogin(provider, lambda home, env: {}, ttl=40, on_output=output.append)
login.start()
deadline = time.monotonic() + 30
try:
    while time.monotonic() < deadline:
        state = login.public()
        if state["verification_uri"] and (provider == "claude" or state["user_code"]):
            url = urlsplit(state["verification_uri"])
            print(
                json.dumps(
                    {
                        "provider": provider,
                        "status": "AUTHORIZATION_READY",
                        "host": url.hostname,
                        "path": url.path,
                        "device_code_present": bool(state["user_code"]),
                        "input_required": state["input_required"],
                        "redirect_uri": parse_qs(url.query).get("redirect_uri", [None])[0],
                    }
                )
            )
            break
        if state["status"] not in ACTIVE:
            raise RuntimeError(json.dumps(state))
        time.sleep(0.1)
    else:
        raise TimeoutError("The provider did not return a sign-in link")
finally:
    login.cancel()
    stop = time.monotonic() + 5
    while login.public()["status"] in ACTIVE and time.monotonic() < stop:
        time.sleep(0.1)
    if login.public()["status"] == "ERROR" or not login.public()["verification_uri"]:
        # This probe uses a new temporary home and never completes authentication.
        # Print diagnostic text only after cancelling the unapproved authorization.
        import re

        for candidate in re.findall(r"https://[^\s]+", "".join(output)):
            parsed = urlsplit(candidate)
            print(
                json.dumps(
                    {
                        "observed_host": parsed.hostname,
                        "observed_path": parsed.path,
                        "redirect_uri": parse_qs(parsed.query).get("redirect_uri", [None])[0],
                    }
                )
            )
        text = re.sub(r"https://[^\s]+", "[authorization-url]", "".join(output))
        text = re.sub(r"\b[A-Z0-9]{4,5}-[A-Z0-9]{4,5}\b", "[device-code]", text)
        print(text[-4000:])

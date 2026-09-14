"""Manual provider smoke test; importing this module performs no network I/O."""

import os
from pathlib import Path
from urllib.error import HTTPError, URLError

from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "CapstoneProject.settings")
    from Pathway.services.gemini import DEFAULT_GEMINI_TEXT_MODEL, call_gemini_text

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY before running this command.")
    try:
        reply = call_gemini_text(
            api_key=api_key,
            model=os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_TEXT_MODEL),
            system_prompt="Reply briefly.",
            context_message="Connection check. No student data is included.",
            messages=[{"role": "user", "content": "Reply with: Connection successful."}],
        )
    except HTTPError as exc:
        raise SystemExit(
            f"Provider returned HTTP {exc.code}. Check your model and credentials."
        ) from None
    except (URLError, ValueError, TimeoutError):
        raise SystemExit("Provider request failed. Check connectivity and configuration.") from None
    print(reply)


if __name__ == "__main__":
    main()

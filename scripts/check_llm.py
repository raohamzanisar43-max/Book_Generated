"""Verify the configured LLM provider(s) with a tiny request.  Usage: python -m scripts.check_llm"""
import sys

from backend.config import settings
from backend.services.llm_service import LLMError, llm_service


def main() -> int:
    print(f"LLM_PROVIDER={settings.LLM_PROVIDER}  ->  active provider: {llm_service.active_provider()}")
    try:
        outline = llm_service.generate_outline("The Future of AI Automation", "Cover FastAPI, n8n and agents.")
    except LLMError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print("[OK] Outline received:\n")
    print(outline[:1200])
    return 0


if __name__ == "__main__":
    sys.exit(main())

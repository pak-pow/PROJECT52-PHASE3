"""Zero-Emoji compliance scanner."""

import sys
from pathlib import Path


def has_emoji(text: str):
    """Check text for unicode emojis."""
    for ch in text:
        cp = ord(ch)
        if (
            0x1F600 <= cp <= 0x1F64F
            or 0x1F300 <= cp <= 0x1F5FF
            or 0x1F680 <= cp <= 0x1F6FF
            or 0x1F700 <= cp <= 0x1F77F
            or 0x1F780 <= cp <= 0x1F7FF
            or 0x1F800 <= cp <= 0x1F8FF
            or 0x1F900 <= cp <= 0x1F9FF
            or 0x1FA00 <= cp <= 0x1FA6F
            or 0x1FA70 <= cp <= 0x1FAFF
            or 0x2600 <= cp <= 0x26FF
            or 0x2700 <= cp <= 0x27BF
            or 0xFE00 <= cp <= 0xFE0F
            or 0x1F1E6 <= cp <= 0x1F1FF
        ):
            return True, ch, hex(cp)
    return False, "", ""


def main():
    """Scan key files for zero emoji compliance."""
    base_dir = Path(__file__).resolve().parent.parent
    frontend_dir = base_dir.parent / "frontend"
    doc_dir = (
        base_dir.parent.parent.parent
        / "PROJECT52"
        / "Documentation"
        / "Phase3"
        / "week46_oauth_provider"
    )

    paths = [
        frontend_dir / "public" / "index.html",
        frontend_dir / "src" / "css" / "base.css",
        frontend_dir / "src" / "js" / "app.js",
        frontend_dir / "src" / "js" / "sandbox_playground.js",
        frontend_dir / "src" / "js" / "client_portal.js",
        frontend_dir / "src" / "js" / "user_manager.js",
        frontend_dir / "src" / "js" / "metadata_viewer.js",
        base_dir / "app" / "routes" / "static_routes.py",
        base_dir / "app" / "templates" / "callback.html",
        base_dir / "app" / "services" / "token_service.py",
        base_dir / "tests" / "test_static_routes.py",
        base_dir / "tests" / "test_e2e_oauth_lifecycle.py",
        base_dir / "tests" / "test_concurrency.py",
        base_dir / "scripts" / "run_benchmarks.py",
        base_dir / "scripts" / "audit_emojis.py",
        base_dir.parent / "README.md",
        doc_dir
        / (
            "Dev log Day 6 - Mobile-First Frontend, "
            "Scope Consent UI & Interactive OAuth Playground.md"
        ),
        doc_dir
        / (
            "Dev log Day 7 - Concurrency Benchmarks, Chaos Testing, "
            "Quality Gates & Handover.md"
        ),
    ]

    all_clean = True
    for p in paths:
        if not p.exists():
            print("Missing:", p)
            continue
        content = p.read_text(encoding="utf-8")
        found, ch, code = has_emoji(content)
        if found:
            print(f"EMOJI DETECTED in {p.name}: char={ch} codepoint={code}")
            all_clean = False
        else:
            print(f"[OK] Clean: {p.name}")

    if all_clean:
        print("\n>> AUDIT PASSED: ALL FILES ARE 100% EMOJI FREE!")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

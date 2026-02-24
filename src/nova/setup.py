from pathlib import Path


def main():
    base = Path.home() / ".nova"
    dirs = [
        base / "logs",
        base / "memory" / "captures",
        base / "memory" / "knowledge" / "global",
        base / "memory" / "archive" / "captures",
        base / "memory" / "archive" / "knowledge",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    state_file = base / "state.json"
    if not state_file.exists():
        state_file.write_text('{"last_dream_run": null, "sessions": {}}\n')

    print(f"Nova directories created at {base}")


if __name__ == "__main__":
    main()

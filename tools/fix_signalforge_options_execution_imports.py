from pathlib import Path

root = Path("src/signalforge/options_execution")

for path in root.glob("*.py"):
    text = path.read_text(encoding="utf-8")

    text = text.replace(
        "from src.options_execution.",
        "from src.signalforge.options_execution.",
    )

    text = text.replace(
        "import src.options_execution.",
        "import src.signalforge.options_execution.",
    )

    path.write_text(text, encoding="utf-8")
    print("patched", path)

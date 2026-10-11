"""Live check of both providers. Prints model ids, answers and token usage only, never secrets."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lamarck import config, llm  # noqa: E402


def main() -> None:
    from google import genai

    lister = genai.Client(api_key=os.environ["GEMINI_API_KEY"])  # keep a reference: the pager fetches lazily
    names = sorted(m.name.removeprefix("models/") for m in lister.models.list())
    print("gemini-3 models:", ", ".join(n for n in names if n.startswith("gemini-3")))
    client = llm.GeminiClient(os.environ["GEMINI_API_KEY"])
    for level in config.THINKING_LEVELS:
        text, _, usage = client.generate(config.DEFAULT_WORKER, "Answer briefly.",
                                         [llm.Turn("user", "What is 17*23? End with 'FINAL: <n>'.")], level)
        print(f"gemini thinking={level}: {text.strip()[-60:]!r} usage={usage}")
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"],
              "additionalProperties": False}
    print("claude structured output:", llm.claude_json("Propose a name for a cat.", "You name cats.", schema))


if __name__ == "__main__":
    main()

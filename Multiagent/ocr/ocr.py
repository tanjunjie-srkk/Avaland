import base64
import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from openai import AzureOpenAI, OpenAI

# Add Multiagent/ to path so we can import the shared config
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import (
    AZURE_OPENAI_ENDPOINT as endpoint,
    AZURE_OPENAI_API_KEY as subscription_key,
    AZURE_OPENAI_DEPLOYMENT as deployment,
    AZURE_OPENAI_API_VERSION as api_version,
)

model_name = deployment

client = AzureOpenAI(
    api_version=api_version,
    azure_endpoint=endpoint,
    api_key=subscription_key,
)


def _image_file_to_data_url(image_path: Path) -> str:
  mime_type, _ = mimetypes.guess_type(str(image_path))
  if not mime_type:
    mime_type = "application/octet-stream"
  b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
  return f"data:{mime_type};base64,{b64}"

SYSTEM_PROMPT = """
You are a GENERAL OCR and DOCUMENT TRANSCRIPTION engine.

Your role is STRICTLY LIMITED to faithful transcription.
You are NOT a reasoning, calculation, interpretation, or rule-making system.

CORE RESPONSIBILITIES:
1. Extract ALL visible text from the provided document images.
2. Preserve original wording, spelling, punctuation, numbers, and formatting.
3. Preserve document structure (titles, headings, paragraphs, bullet points, notes).
4. Preserve legal, financial, and contractual language EXACTLY as written.
5, If any extracted text could be interpreted as a rule or instruction, preserve it verbatim and DO NOT simplify it.


STRICT PROHIBITIONS (CRITICAL):
- DO NOT interpret, summarize, infer, normalize, or rephrase content.
- DO NOT convert text into rules, conditions, formulas, or logic.
- DO NOT calculate percentages, totals, or derived values.
- DO NOT merge, reconstruct, or reason across tables.
- DO NOT assume relationships between sections or statements.

TABLE HANDLING (IMPORTANT):
- If a table is detected, extract it ONLY as raw text content.
- Do NOT assign table IDs, headers, rows, or continuity logic.
- Do NOT infer column meaning or align values.
- Mark partially visible or cut-off tables as [PARTIAL].

UNCERTAINTY & QUALITY HANDLING:
- If text is unreadable, output exactly: [UNREADABLE]
- If content is cut off or incomplete, output exactly: [PARTIAL]
- If handwriting is unclear, output best-guess text and mark uncertainty with [?]

OUTPUT FORMAT:
Return a SINGLE valid JSON object using the schema below.
Do NOT include markdown.
Do NOT include explanations.

{
  "pages": [
    {
      "page_number": <number>,
      "sections": [
        {
          "type": "title | header | paragraph | bullet | table | footnote | note | signature | stamp | handwritten",
          "content": "exact extracted text",
          "confidence": 0.00–1.00
        }
      ]
    }
  ],
  "metadata": {
    "language_detected": ["en", "zh", "ms"],
    "quality": "clear | noisy | blurry | low_resolution"
  }
}

DOCUMENT SCOPE RULES:
- Treat all provided images as ONE continuous document.
- Preserve original page order.
- Do NOT skip any visible content, even if repetitive.

FAIL-SAFE BEHAVIOR:
- If no text is detected on a page, return an empty page object with reason.
- If extraction is uncertain, lower confidence rather than guessing.
- Always prioritize faithful transcription over completeness.
"""


def ocr_image_with_chat_model(image_path: Path, user_prompt: str) -> str:
  data_url = _image_file_to_data_url(image_path)

  try:
    completion = client.chat.completions.create(
      model=deployment,
      messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {
          "role": "user",
          "content": [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
          ],
        },
      ],
      temperature=1.0,
    )
    return completion.choices[0].message.content or ""
  except Exception as e:
    # Common cause: Azure content filter flags the *prompt* (often when referencing system messages).
    return json.dumps(
      {
        "error": "ocr_failed",
        "message": str(e),
      },
      ensure_ascii=False,
    )


def ocr_images_with_chat_model(image_paths: list[Path], user_prompt: str) -> str:
  content: list[dict] = [
    {
      "type": "text",
      "text": (
        f"{user_prompt}\n\n"
        "You will receive multiple images, and treat it as a whole as a single documents. "
        "Use the schema from the instructions. Include one entry per image in pages[], in the same order. "
        "For each page, set page_number starting from 1 and include the filename in a field named file_name."
      ),
    }
  ]

  for idx, image_path in enumerate(image_paths, start=1):
    content.append({"type": "text", "text": f"Image {idx} filename: {image_path.name}"})
    content.append({"type": "image_url", "image_url": {"url": _image_file_to_data_url(image_path)}})

  try:
    completion = client.chat.completions.create(
      model=deployment,
      messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
      ],
      temperature=1.0,
    )
    return completion.choices[0].message.content or ""
  except Exception as e:
    return json.dumps(
      {
        "error": "ocr_failed",
        "message": str(e),
      },
      ensure_ascii=False,
    )


def _maybe_parse_json(text: str) -> object:
  try:
    return json.loads(text)
  except Exception:
    return text


def main() -> None:
  parser = argparse.ArgumentParser(description="OCR images in memo folder")
  parser.add_argument(
    "--batch",
    action="store_true",
    help="Send all images in ONE request (may hit context limits for many/large images).",
  )
  args = parser.parse_args()

  memo_dir = Path(__file__).resolve().parents[1] / "memo"
  image_paths = sorted(
    [p for p in memo_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
  )
  if not image_paths:
    raise RuntimeError(f"No images found in: {memo_dir}")

  user_prompt = (
    "Perform OCR on the image. Output only valid JSON (no markdown, no extra text). "
    "Follow the JSON schema described in the instructions and set confidence values realistically."
  )

  if args.batch:
    content = ocr_images_with_chat_model(image_paths=image_paths, user_prompt=user_prompt)
    output_obj = {
      "mode": "batch",
      "files": [p.name for p in image_paths],
      "model_output": _maybe_parse_json(content),
    }
  else:
    outputs: list[dict] = []
    for idx, image_path in enumerate(image_paths, start=1):
      content = ocr_image_with_chat_model(image_path=image_path, user_prompt=user_prompt)
      outputs.append(
        {
          "page_number": idx,
          "file": image_path.name,
          "model_output": _maybe_parse_json(content),
        }
      )
    output_obj = {"mode": "per_image", "results": outputs}

  with open("Multiagent/artifact/output-text.json", "w", encoding="utf-8") as f:
    json.dump(output_obj, f, ensure_ascii=False, indent=2)

  #print(json.dumps({"results": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
  main()
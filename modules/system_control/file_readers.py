import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

from core.logger import logger


TEXT_EXTENSIONS = {
    ".txt", ".md", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".csv", ".log",
    ".html", ".css", ".scss", ".sql", ".xml", ".java", ".c", ".cpp",
    ".h", ".hpp", ".go", ".rs", ".sh",
}

MAX_TEXT_CHARS = 16000
READ_PREVIEW_CHARS = 2200


def read_file_text(filepath, max_chars=MAX_TEXT_CHARS):
    extension = os.path.splitext(filepath)[1].lower()

    try:
        if extension in TEXT_EXTENSIONS:
            return _read_plain_text(filepath, max_chars=max_chars)
        if extension == ".docx":
            return _read_docx(filepath, max_chars=max_chars)
        if extension == ".pdf":
            return _read_pdf(filepath, max_chars=max_chars)
    except Exception as exc:
        logger.error(f"Failed to read file '{filepath}': {exc}")
        return None

    return None


def read_file_preview(filepath, max_chars=READ_PREVIEW_CHARS):
    text = read_file_text(filepath, max_chars=max_chars)
    if not text:
        extension = os.path.splitext(filepath)[1].lower() or "unknown"
        size = _safe_size(filepath)
        return (
            f"I can open '{os.path.basename(filepath)}', but I can't read that file type directly yet. "
            f"Extension: {extension}. Size: {size} bytes."
        )

    cleaned = _clean_text(text)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip() + "..."
    return f"Preview of {os.path.basename(filepath)}:\n{cleaned}"


def summarize_file_offline(filepath, llm=None):
    text = read_file_text(filepath, max_chars=MAX_TEXT_CHARS)
    if not text:
        return (
            f"I opened '{os.path.basename(filepath)}', but I couldn't extract readable text from it yet."
        )

    cleaned = _clean_text(text)
    if not cleaned:
        return f"'{os.path.basename(filepath)}' appears to be empty."

    llm_summary = _summarize_with_llm(filepath, cleaned, llm)
    if llm_summary:
        return llm_summary

    return _heuristic_summary(filepath, cleaned)


def _read_plain_text(filepath, max_chars=MAX_TEXT_CHARS):
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            with open(filepath, "r", encoding=encoding) as handle:
                return handle.read(max_chars)
        except UnicodeError:
            continue
    with open(filepath, "r", encoding="utf-8", errors="ignore") as handle:
        return handle.read(max_chars)


def _read_docx(filepath, max_chars=MAX_TEXT_CHARS):
    chunks = []
    with zipfile.ZipFile(filepath) as archive:
        with archive.open("word/document.xml") as doc_xml:
            root = ET.fromstring(doc_xml.read())
            for element in root.iter():
                if element.tag.endswith("}t") and element.text:
                    chunks.append(element.text)
                    if sum(len(part) for part in chunks) >= max_chars:
                        break
    return " ".join(chunks)[:max_chars]


def _read_pdf(filepath, max_chars=MAX_TEXT_CHARS):
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(filepath)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
            if sum(len(part) for part in pages) >= max_chars:
                break
        return "\n".join(pages)[:max_chars]
    except Exception:
        pass

    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return None

    result = subprocess.run(
        [pdftotext, "-layout", filepath, "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout[:max_chars]


def _summarize_with_llm(filepath, text, llm):
    if llm is None:
        return None

    prompt = (
        "You are FRIDAY, an offline desktop assistant.\n"
        "Summarize the following file in 3-5 concise bullet-like sentences. "
        "Mention the main purpose, key points, and any actionable items.\n\n"
        f"Filename: {os.path.basename(filepath)}\n\n"
        f"Content:\n{text[:12000]}"
    )

    try:
        if hasattr(llm, "create_chat_completion"):
            response = llm.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=220,
                temperature=0.2,
            )
            summary = response["choices"][0]["message"]["content"].strip()
        else:
            response = llm(prompt, max_tokens=220, temperature=0.2)
            summary = response["choices"][0].get("text", "").strip()
        return f"Summary of {os.path.basename(filepath)}:\n{summary}" if summary else None
    except Exception as exc:
        logger.warning(f"LLM file summary failed for '{filepath}': {exc}")
        return None


def _heuristic_summary(filepath, text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first_lines = []
    for line in lines:
        if len(first_lines) >= 4:
            break
        if line not in first_lines:
            first_lines.append(line)

    sentences = re.split(r"(?<=[.!?])\s+", text)
    key_sentences = []
    for sentence in sentences:
        cleaned = sentence.strip()
        if len(cleaned) < 30:
            continue
        if cleaned not in key_sentences:
            key_sentences.append(cleaned)
        if len(key_sentences) >= 3:
            break

    summary_parts = first_lines if first_lines else key_sentences
    if not summary_parts:
        summary_parts = [text[:300].strip()]

    joined = "\n".join(f"- {part[:220]}" for part in summary_parts if part)
    return f"Summary of {os.path.basename(filepath)}:\n{joined}"


def _clean_text(text):
    if not text:
        return ""

    cleaned = text
    try:
        if cleaned.lstrip().startswith("{") or cleaned.lstrip().startswith("["):
            parsed = json.loads(cleaned)
            cleaned = json.dumps(parsed, indent=2)
    except Exception:
        pass

    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _safe_size(filepath):
    try:
        return os.path.getsize(filepath)
    except OSError:
        return 0

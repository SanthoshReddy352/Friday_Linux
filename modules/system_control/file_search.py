import difflib
import os
import platform
import re
import subprocess

from core.logger import logger


EXTENSION_ALIASES = {
    "pdf": ".pdf",
    ".pdf": ".pdf",
    "text": ".txt",
    "txt": ".txt",
    ".txt": ".txt",
    "markdown": ".md",
    "md": ".md",
    ".md": ".md",
    "json": ".json",
    ".json": ".json",
    "csv": ".csv",
    ".csv": ".csv",
    "python": ".py",
    "py": ".py",
    ".py": ".py",
    "word": ".docx",
    "docx": ".docx",
    ".docx": ".docx",
}

IGNORED_SUFFIXES = (".resolved", ".resolved.0", ".metadata.json")


def search_files_raw(filename, search_dir=None, folder_path=None, extension=None, limit=5):
    """
    Search for files by filename or stem. Returns a ranked list of absolute paths.
    """
    query = normalize_token(filename)
    if not query:
        return []

    desired_ext = canonicalize_extension(extension)
    candidates = []
    seen = set()

    try:
        for root, dirs, files in _iter_search_space(search_dir=search_dir, folder_path=folder_path):
            dirs[:] = [dirname for dirname in dirs if not dirname.startswith(".")]

            for file_name in files:
                if file_name.startswith(".") or file_name.endswith(IGNORED_SUFFIXES):
                    continue

                filepath = os.path.join(root, file_name)
                if filepath in seen:
                    continue

                score = _score_file_candidate(file_name, query, desired_ext)
                if score <= 0:
                    continue

                seen.add(filepath)
                candidates.append((score, filepath))

        candidates.sort(key=lambda item: (-item[0], len(item[1]), item[1].lower()))
        return [filepath for _, filepath in candidates[:limit]]
    except Exception as exc:
        logger.error(f"Error while searching for file '{filename}': {exc}")
        return []


def search_folders_raw(folder_name, search_dir=None, limit=10):
    query = normalize_token(folder_name)
    if not query:
        return []

    matches = []
    seen = set()

    try:
        for root, dirs, _ in _iter_search_space(search_dir=search_dir):
            dirs[:] = [dirname for dirname in dirs if not dirname.startswith(".")]
            for dirname in dirs:
                folder_path = os.path.join(root, dirname)
                if folder_path in seen:
                    continue

                score = _score_folder_candidate(dirname, query)
                if score <= 0:
                    continue

                seen.add(folder_path)
                matches.append((score, folder_path))

        matches.sort(key=lambda item: (-item[0], len(item[1]), item[1].lower()))
        return [folder_path for _, folder_path in matches[:limit]]
    except Exception as exc:
        logger.error(f"Error while searching for folder '{folder_name}': {exc}")
        return []


def resolve_folder_path(folder_name, search_dir=None):
    if not folder_name:
        return None

    if os.path.isdir(folder_name):
        return os.path.abspath(folder_name)

    matches = search_folders_raw(folder_name, search_dir=search_dir, limit=5)
    return matches[0] if matches else None


def list_folder_contents(folder_path, limit=50):
    if not folder_path or not os.path.isdir(folder_path):
        return []

    entries = []
    for entry in sorted(os.listdir(folder_path), key=lambda value: value.lower()):
        if entry.startswith("."):
            continue
        full_path = os.path.join(folder_path, entry)
        if os.path.isfile(full_path):
            entries.append(full_path)
        if len(entries) >= limit:
            break
    return entries


def format_search_results(matches, filename):
    if not matches:
        return f"I couldn't find any file matching '{filename}'."

    result = [f"I found {len(matches)} matching file(s):"]
    for match in matches:
        result.append(f"- {match}")
    return "\n".join(result)


def format_folder_listing(folder_path, matches):
    folder_name = os.path.basename(folder_path.rstrip(os.sep)) if folder_path else "that folder"
    if not matches:
        return f"I couldn't find any visible files in {folder_name}."

    lines = [f"Files in {folder_name}:"]
    for match in matches:
        lines.append(f"- {os.path.basename(match)}")
    return "\n".join(lines)


def open_file(filepath):
    """
    Cross-platform logic to open a file with its default application.
    """
    return open_path(filepath, label="file")


def open_folder(folder_path):
    return open_path(folder_path, label="folder")


def open_path(target_path, label="item"):
    try:
        os_name = platform.system()
        if os_name == "Windows":
            os.startfile(target_path)
        elif os_name == "Linux":
            subprocess.Popen(["xdg-open", target_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os_name == "Darwin":
            subprocess.Popen(["open", target_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        logger.info(f"Opened {label}: {target_path}")
        return f"Opening {os.path.basename(target_path)}..."
    except Exception as exc:
        logger.error(f"Failed to open {label} '{target_path}': {exc}")
        return f"Failed to open the {label}: {exc}"


def canonicalize_extension(value):
    if not value:
        return None
    return EXTENSION_ALIASES.get(value.lower().strip())


def extract_extension_from_text(text):
    if not text:
        return None

    match = re.search(r"\.(pdf|txt|md|json|csv|py|docx)\b", text.lower())
    if match:
        return canonicalize_extension(match.group(0))

    for alias, extension in EXTENSION_ALIASES.items():
        if alias.startswith("."):
            continue
        if re.search(rf"\b{re.escape(alias)}\b", text.lower()):
            return extension
    return None


def choose_candidate_from_text(selection_text, candidates):
    cleaned = normalize_token(selection_text)
    if not cleaned or not candidates:
        return None, None

    index_match = re.fullmatch(r"(?:option\s+)?(\d+)", cleaned)
    if index_match:
        index = int(index_match.group(1)) - 1
        if 0 <= index < len(candidates):
            return candidates[index], None
        return None, "That number is outside the available options."

    extension = extract_extension_from_text(selection_text)
    if extension:
        filtered = [candidate for candidate in candidates if os.path.splitext(candidate)[1].lower() == extension]
        if len(filtered) == 1:
            return filtered[0], None
        if len(filtered) > 1:
            names = ", ".join(os.path.basename(path) for path in filtered)
            return None, f"I still have multiple {extension} files: {names}."

    normalized_map = {}
    for candidate in candidates:
        basename = os.path.basename(candidate)
        stem, _ = os.path.splitext(basename)
        normalized_map[normalize_token(basename)] = candidate
        normalized_map[normalize_token(stem)] = candidate

    if cleaned in normalized_map:
        return normalized_map[cleaned], None

    fuzzy = difflib.get_close_matches(cleaned, list(normalized_map), n=1, cutoff=0.8)
    if fuzzy:
        return normalized_map[fuzzy[0]], None

    return None, "I couldn't tell which file you meant."


def normalize_token(value):
    cleaned = re.sub(r"[^a-z0-9.\-_ ]+", " ", (value or "").lower())
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split())


def _iter_search_space(search_dir=None, folder_path=None):
    if folder_path:
        yield from os.walk(folder_path)
        return

    search_dirs = []
    if search_dir:
        search_dirs.append(search_dir)
    else:
        search_dirs.extend([os.getcwd(), os.path.expanduser("~")])
        try:
            import psutil

            for partition in psutil.disk_partitions():
                if "rw" not in partition.opts and "ro" not in partition.opts:
                    continue
                if platform.system() == "Linux" and partition.mountpoint == "/":
                    continue
                if partition.mountpoint not in search_dirs:
                    search_dirs.append(partition.mountpoint)
        except Exception as exc:
            logger.warning(f"Could not load disk partitions: {exc}")

    seen = set()
    for directory in search_dirs:
        if not directory or directory in seen or not os.path.exists(directory):
            continue
        seen.add(directory)
        yield from os.walk(directory)


def _score_file_candidate(file_name, query, desired_ext):
    basename = file_name.lower()
    stem, extension = os.path.splitext(basename)
    normalized_basename = normalize_token(basename)
    normalized_stem = normalize_token(stem)

    if desired_ext and extension != desired_ext:
        return 0

    if normalized_basename == query:
        return 320
    if normalized_stem == query:
        return 300
    if basename == query:
        return 280
    if normalized_basename.startswith(query):
        return 250
    if normalized_stem.startswith(query):
        return 240
    if query in normalized_basename:
        return 190

    ratio = difflib.SequenceMatcher(None, query, normalized_stem).ratio()
    if ratio >= 0.82:
        return int(140 + ratio * 50)

    return 0


def _score_folder_candidate(folder_name, query):
    normalized_name = normalize_token(folder_name)
    if normalized_name == query:
        return 300
    if normalized_name.startswith(query):
        return 230
    if query in normalized_name:
        return 180

    ratio = difflib.SequenceMatcher(None, query, normalized_name).ratio()
    if ratio >= 0.84:
        return int(130 + ratio * 50)
    return 0

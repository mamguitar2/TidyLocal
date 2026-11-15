"""Local-only file organization suggestions based on names, types, and bounded text."""
from __future__ import annotations

import os
import re
import stat
import zipfile
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

MAX_TEXT_BYTES = 64 * 1024
PERSONAL_SUBFOLDERS = ("Music", "Bad Caddy Apparel Co", "Rent", "Power of Attorney", "Wedding")

# Terms are intentionally explicit. Ambiguous or unrecognized files stay for review.
KEYWORDS = {
    "Taxes": ("tax return", "tax form", "taxes", "tax", "irs", "1040", "w2", "w 2", "1099", "1098", "wage and tax", "federal return"),
    "Finances": ("bank statement", "credit card", "invoice", "receipt", "utility bill", "rent payment", "mortgage", "checking account", "savings account", "budget", "financial statement", "statement", "paystub", "pay stub", "investment"),
    "Career": ("resume", "résumé", "curriculum vitae", "cover letter", "job application", "job description", "offer letter", "work experience", "portfolio", "performance review", "employment", "linkedin", "certification"),
    "Personal/Music": ("music", "song", "album", "playlist", "lyrics", "audio", "recording", "track list", "midi"),
    "Personal/Bad Caddy Apparel Co": ("bad caddy", "bad caddy apparel", "apparel co", "caddy apparel", "shirt order", "merch order"),
    "Personal/Rent": ("lease agreement", "rental agreement", "rent", "landlord", "tenant", "security deposit", "lease"),
    "Personal/Power of Attorney": ("power of attorney", "attorney in fact", "durable power", "poa"),
    "Personal/Wedding": ("wedding", "wedding planner", "wedding venue", "guest list", "rsvp", "bride", "groom"),
    "Personal": ("personal", "family", "vacation", "hobby", "recipe", "medical records", "family photos", "personal notes"),
}

READABLE_SUFFIXES = {".txt", ".md", ".csv", ".tsv", ".rtf", ".html", ".htm", ".xml", ".json", ".yaml", ".yml", ".docx", ".odt"}
AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".mid", ".midi"}
NON_DOCUMENT_CONTEXT_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".tif", ".tiff", ".bmp", ".svg",
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", *AUDIO_SUFFIXES,
    ".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".go", ".rs", ".sh",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".dmg", ".pkg", ".iso",
}
SYSTEM_METADATA_NAMES = {".ds_store", ".localized", "thumbs.db", "desktop.ini"}


def is_system_metadata(path: Path) -> bool:
    """Identify OS-generated sidecar/desktop metadata, not user content files."""
    name = path.name.casefold()
    return name in SYSTEM_METADATA_NAMES or name.startswith("._")


PROTECTED_PATH_PARTS = {".git", ".venv", "venv", "node_modules", "Library", "System", "Applications"}


def is_protected_path(path: Path) -> bool:
    """Whether a path lies inside a system or code-managed protected directory."""
    return any(part in PROTECTED_PATH_PARTS for part in path.parts)


GIT_HOOK_NAMES = {
    "applypatch-msg", "commit-msg", "post-applypatch", "post-checkout", "post-commit",
    "post-merge", "post-receive", "post-rewrite", "pre-applypatch", "pre-commit",
    "pre-merge-commit", "prepare-commit-msg", "pre-push", "pre-rebase", "pre-receive",
    "push-to-checkout", "sendemail-validate", "update",
}


def is_non_actionable_artifact(path: Path) -> bool:
    """Skip opaque index/cache and Git hook artifacts from organizer actions."""
    stem = path.stem.casefold()
    if stem in {"index", "indexfile", "index_file", *GIT_HOOK_NAMES}:
        return True
    if any(part.casefold() in {".git", "node_modules", ".vscode"} for part in path.parts):
        return True
    return (len(stem) >= 12 and stem.isdigit()) or (len(stem) >= 16 and re.fullmatch(r"[0-9a-f]+", stem) is not None)


FILE_TYPE_NAMES = {
    ".pdf": "PDF document", ".doc": "Word document", ".docx": "Word document",
    ".odt": "OpenDocument text", ".xls": "Spreadsheet", ".xlsx": "Spreadsheet",
    ".csv": "CSV spreadsheet", ".ppt": "Presentation", ".pptx": "Presentation",
    ".jpg": "Photo", ".jpeg": "Photo", ".png": "Photo", ".heic": "Photo",
    ".webp": "Photo", ".tif": "Photo", ".tiff": "Photo", ".bmp": "Photo",
    ".gif": "Animated image", ".svg": "Vector image", ".mp4": "Video", ".mov": "Video",
    ".mkv": "Video", ".avi": "Video", ".webm": "Video", ".m4v": "Video",
    ".mp3": "Audio", ".m4a": "Audio",
    ".wav": "Audio", ".flac": "Audio", ".zip": "Archive", ".tar": "Archive",
    ".gz": "Archive", ".dmg": "Disk image", ".pkg": "Installer", ".py": "Python code",
    ".js": "JavaScript code", ".ts": "TypeScript code", ".html": "HTML document",
    ".css": "Stylesheet", ".json": "JSON data", ".xml": "XML data",
    ".swift": "Swift code", ".rb": "Ruby code", ".ipynb": "Jupyter notebook",
}


def describe_file_type(path: Path) -> str:
    """Human-readable type labels; hidden macOS metadata is not media."""
    if path.name.casefold() == ".ds_store":
        return "macOS Finder metadata"
    if path.name.startswith("._"):
        return "macOS resource-fork metadata"
    if is_system_metadata(path):
        return "System metadata"
    suffix = path.suffix.lower()
    return FILE_TYPE_NAMES.get(suffix, f"{suffix.lstrip('.').upper()} file" if suffix else "File")


FOLDER_ALIASES = {
    "Taxes": {
        "tax", "taxes", "tax files", "tax folder", "taxes folder", "tax documents",
        "tax docs", "tax returns", "tax return", "tax paperwork", "tax papers",
        "tax records", "tax documentation", "income tax",
    },
    "Finances": {"finance", "finances", "financial", "financial records"},
    "Career": {"career", "careers", "career folder", "career files", "career documents", "my career", "work", "professional", "professional documents", "job search", "resume", "resumes", "cv"},
    "Personal": {"personal", "personal files"},
    "Music": {"music", "audio", "songs"},
    "Bad Caddy Apparel Co": {"bad caddy", "bad caddy apparel", "bad caddy apparel co"},
    "Rent": {"rent", "rental", "lease"},
    "Power of Attorney": {"power of attorney", "poa"},
    "Wedding": {"wedding", "weddings", "wedding folder"},
}
ORGANIZER_DESTINATIONS = (
    "Taxes", "Finances", "Career", "Personal", "Personal/Music",
    "Personal/Bad Caddy Apparel Co", "Personal/Rent", "Personal/Power of Attorney",
    "Personal/Wedding",
)


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def read_local_text(path: Path) -> str:
    """Read at most 64 KiB from supported text formats; never sends it elsewhere."""
    suffix = path.suffix.lower()
    if suffix not in READABLE_SUFFIXES:
        return ""
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return ""
            if suffix in {".docx", ".odt"}:
                member = "word/document.xml" if suffix == ".docx" else "content.xml"
                with zipfile.ZipFile(stream) as archive:
                    info = archive.getinfo(member)
                    if info.file_size > MAX_TEXT_BYTES * 8:
                        return ""
                    raw = archive.read(member)[: MAX_TEXT_BYTES * 8]
                root = ElementTree.fromstring(raw)
                return " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))[:MAX_TEXT_BYTES]
            raw = stream.read(MAX_TEXT_BYTES)
        text = raw.decode("utf-8", errors="replace")
        if suffix in {".html", ".htm"}:
            parser = _TextOnly()
            parser.feed(text)
            text = " ".join(parser.parts)
        elif suffix == ".rtf":
            text = re.sub(r"\\'[0-9a-fA-F]{2}|\\[a-zA-Z]+-?\d* ?|[{}]", " ", text)
        return text
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        return ""


def _normalized(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text.casefold()).strip()


def _folder_names_match(normalized: str, aliases: set[str]) -> bool:
    for alias in aliases:
        if normalized == alias or SequenceMatcher(None, normalized, alias).ratio() >= 0.90:
            return True
        if len(alias) >= 5 and (normalized.startswith(f"{alias} ") or normalized.endswith(f" {alias}")):
            return True
    return False


def _matches(text: str, terms: tuple[str, ...]) -> list[str]:
    normalized = f" {_normalized(text)} "
    found = []
    for term in terms:
        phrase = _normalized(term)
        if phrase and f" {phrase} " in normalized:
            found.append(term)
    return found


def find_similar_folder(parent: Path, name: str) -> Path | None:
    """Find an existing directory whose normalized name matches a known alias."""
    if not parent.is_dir():
        return None
    aliases = {_normalized(name), *(_normalized(alias) for alias in FOLDER_ALIASES.get(name, set()))}
    candidates = []
    try:
        for child in parent.iterdir():
            if not child.is_symlink() and child.is_dir():
                normalized = _normalized(child.name)
                ratio = max((SequenceMatcher(None, normalized, alias).ratio() for alias in aliases), default=0)
                if _folder_names_match(normalized, aliases):
                    candidates.append((ratio, child))
    except OSError:
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1].name.casefold()))
    return candidates[0][1]


def _folder_destination_context(path: Path, location_root: Path) -> tuple[str, str] | None:
    """Recognize known destination names in the file's current folder path."""
    destinations = {
        "Taxes": "Taxes", "Finances": "Finances", "Career": "Career", "Personal": "Personal",
        "Music": "Personal/Music", "Bad Caddy Apparel Co": "Personal/Bad Caddy Apparel Co",
        "Rent": "Personal/Rent", "Power of Attorney": "Personal/Power of Attorney", "Wedding": "Personal/Wedding",
    }
    try:
        folders = path.parent.relative_to(location_root).parts
    except ValueError:
        return None
    for folder in reversed(folders):
        normalized = _normalized(folder)
        for name, destination in destinations.items():
            aliases = {_normalized(name), *(_normalized(alias) for alias in FOLDER_ALIASES.get(name, set()))}
            if _folder_names_match(normalized, aliases):
                return destination, folder
    return None


def resolve_destination_folder(root: Path, category: str, subcategory: str = "") -> Path:
    """Resolve to a similar existing folder when possible; otherwise return the canonical path."""
    if subcategory:
        direct = find_similar_folder(root, subcategory)
        if direct:
            return direct
    category_folder = find_similar_folder(root, category) or (root / category)
    if subcategory:
        return find_similar_folder(category_folder, subcategory) or (category_folder / subcategory)
    return category_folder


def suggest_file(path: Path, *, location_root: Path, destination_options: dict[str, str] | None = None) -> dict:
    """Classify conservatively and return a reviewable, editable destination proposal."""
    filename = path.name
    suffix = path.suffix.lower()
    content = read_local_text(path)
    protected = is_system_metadata(path)
    folder_context = _folder_destination_context(path, location_root)
    context_conflicts_with_type = bool(
        suffix in NON_DOCUMENT_CONTEXT_SUFFIXES
        and folder_context
        and folder_context[0] in {"Taxes", "Finances", "Career"}
    )
    if context_conflicts_with_type:
        folder_context = None
    scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}
    for target, terms in KEYWORDS.items():
        filename_hits = _matches(path.stem, terms)
        content_hits = _matches(content, terms)
        score = 3.0 * len(filename_hits) + 1.5 * len(content_hits)
        if folder_context and folder_context[0] == target:
            score = max(score, 8.0)
        if target == "Personal/Music" and suffix in AUDIO_SUFFIXES:
            score += 4.0
        if score:
            scores[target] = score
            evidence[target] = filename_hits[:2] + content_hits[:2]

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    brand_target = "Personal/Bad Caddy Apparel Co"
    explicit_brand_name = bool(_matches(path.stem, KEYWORDS[brand_target]))
    if context_conflicts_with_type:
        chosen = None
        score = 0.0
        ambiguous = False
    elif explicit_brand_name:
        chosen = brand_target
        score = max(scores.get(brand_target, 0.0), 6.0)
        ambiguous = False
    elif folder_context:
        # A recognized destination folder is explicit user intent; do not reclassify
        # its contents based on conflicting words inside the file.
        chosen = folder_context[0]
        score = max(scores.get(chosen, 0.0), 8.0)
        ambiguous = False
    else:
        chosen = ordered[0][0] if ordered else None
        score = ordered[0][1] if ordered else 0.0
        ambiguous = len(ordered) > 1 and ordered[0][1] - ordered[1][1] < 1.5
    confidence = min(0.98, 0.52 + score * 0.075)
    needs_review = chosen is None or ambiguous or confidence < 0.70
    category, separator, subcategory = chosen.partition("/") if chosen else ("", "", "")
    if protected:
        category, subcategory = "", ""
        needs_review = True
        confidence = 1.0
        reason = "macOS Finder metadata; this system file stays in place."
    elif needs_review:
        category, subcategory = "", ""
        confidence = min(confidence, 0.55)
        reason = "No clear category match; review the file before moving it."
    else:
        filename_hits = _matches(path.stem, KEYWORDS[chosen])
        content_hits = _matches(content, KEYWORDS[chosen])
        if folder_context and folder_context[0] == chosen:
            reason = f"Current folder “{folder_context[1]}” matches this destination; keeping the file here."
        elif suffix in AUDIO_SUFFIXES and chosen == "Personal/Music" and not filename_hits and not content_hits:
            reason = f"Audio file type ({suffix}) suggests Music."
        elif filename_hits:
            reason = f"Filename matches {filename_hits[0]!r}."
        else:
            reason = f"Readable file text matches {content_hits[0]!r}."
        if content:
            reason += " Checked supported text locally; contents were not uploaded."

    key = f"{category}/{subcategory}" if subcategory else category
    destination = (destination_options or {}).get(key, "") if category else ""
    if category and not destination:
        destination = str(resolve_destination_folder(location_root, category, subcategory))
    suggested_folder = Path(destination) if destination else None
    already_organized = bool(suggested_folder) and (
        path.parent.is_relative_to(suggested_folder)
        or bool(folder_context and folder_context[0] == chosen)
    )
    if already_organized and not (folder_context and folder_context[0] == chosen):
        reason = "Already in the suggested folder."
    return {
        "name": filename,
        "source": str(path),
        "location_root": str(location_root),
        "category": category,
        "subcategory": subcategory,
        "destination": destination,
        "destination_options": destination_options or {},
        "existing_destinations": {key: Path(value).is_dir() for key, value in (destination_options or {}).items()},
        "confidence": round(confidence, 2),
        "needs_review": needs_review,
        "protected": protected,
        "already_organized": already_organized,
        "reason": reason,
        "file_type": describe_file_type(path),
        "content_checked": bool(content),
    }


def _is_obsolete_chatgpt_atlas_installer(path: Path) -> bool:
    """Identify the specific old installer the user asked to review for Trash."""
    if path.suffix.lower() not in {".dmg", ".pkg", ".mpkg", ".iso"}:
        return False
    name = _normalized(path.stem)
    return "chatgpt" in name and "atlas" in name


def organization_suggestions(
    files: list[dict], roots: dict[str, Path], selected_locations: tuple[str, ...] | list[str] | None = None,
) -> list[dict]:
    """Suggest paths using existing folders in the selected roots before proposing new ones."""
    search_roots = [roots[name] for name in (selected_locations or roots.keys()) if name in roots]
    options_by_location = {}
    for location, root in roots.items():
        options = {}
        for key in ORGANIZER_DESTINATIONS:
            category, _, subcategory = key.partition("/")
            candidate = resolve_destination_folder(root, category, subcategory)
            if not candidate.is_dir():
                candidate = next((
                    match for other_root in search_roots if other_root != root
                    for match in [resolve_destination_folder(other_root, category, subcategory)]
                    if match.is_dir()
                ), candidate)
            options[key] = str(candidate)
        options_by_location[location] = options

    suggestions = []
    for item in files:
        root = roots.get(item.get("location"))
        if root is None:
            continue
        source = Path(item["path"])
        if (is_system_metadata(source) or is_non_actionable_artifact(source)
                or item.get("category") == "code"):
            continue
        suggestion = suggest_file(
            source, location_root=root,
            destination_options=options_by_location[item["location"]],
        )
        suggestion["file_category"] = item.get("category", "other")
        if _is_obsolete_chatgpt_atlas_installer(source):
            suggestion.update({
                "recommended_action": "trash",
                "category": "",
                "subcategory": "",
                "destination": "",
                "needs_review": False,
                "already_organized": False,
                "reason": "You noted ChatGPT Atlas is no longer needed. This installer can go to Trash; that will not uninstall an installed app.",
            })
        if suggestion.get("already_organized"):
            continue
        suggestion["size"] = item.get("size", 0)
        suggestion["location"] = item.get("location", "")
        suggestions.append(suggestion)
    return suggestions

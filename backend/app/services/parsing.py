"""
Layout-aware parsing. Produces a list of ParsedSection with page ranges,
which is what makes exact-source citation possible later.

Real path:   Azure AI Document Intelligence, prebuilt-layout model.
             Gives paragraph roles (title/sectionHeading/text) + page numbers.
Fallback:    pypdf page-by-page text extraction + regex heading detection.
             Lower fidelity (no bounding boxes) but zero cost, fully offline,
             and keeps the exact same output contract so nothing downstream
             needs to change when you switch to real Azure.
"""
import re
from app.config import get_settings
from app.schemas import ParsedSection, SectionType

HEADING_PATTERNS: list[tuple[SectionType, str]] = [
    ("abstract", r"^\s*abstract\s*$"),
    ("introduction", r"^\s*(\d+\.?\s*|[ivxlcdm]+\.?\s*)?introduction\s*$"),
    ("related_work", r"^\s*(\d+\.?\s*|[ivxlcdm]+\.?\s*)?(related work|background|prior work)\s*$"),
    ("method", r"^\s*(\d+\.?\s*|[ivxlcdm]+\.?\s*)?(method|methodology|approach|model|proposed method|system design|design)s?\s*$"),
    ("experiments", r"^\s*(\d+\.?\s*|[ivxlcdm]+\.?\s*)?(experiments?|experimental setup|evaluation|case study)\s*$"),
    ("results", r"^\s*(\d+\.?\s*|[ivxlcdm]+\.?\s*)?(results?|findings)\s*$"),
    ("discussion", r"^\s*(\d+\.?\s*|[ivxlcdm]+\.?\s*)?discussion\s*$"),
    ("limitations", r"^\s*(\d+\.?\s*|[ivxlcdm]+\.?\s*)?(limitations?|threats to validity)\s*$"),
    ("conclusion", r"^\s*(\d+\.?\s*|[ivxlcdm]+\.?\s*)?(conclusions?|future work)\s*$"),
    ("references", r"^\s*(\d+\.?\s*|[ivxlcdm]+\.?\s*)?(references|bibliography|acknowledgy?ments?)\s*$"),
]


def _classify_heading(line: str) -> SectionType | None:
    clean = line.strip().lower()
    for section_type, pattern in HEADING_PATTERNS:
        if re.match(pattern, clean):
            return section_type
    return None


def parse_pdf(file_path: str) -> tuple[list[ParsedSection], int]:
    settings = get_settings()
    if settings.use_docint:
        try:
            return _parse_with_document_intelligence(file_path)
        except Exception as e:
            print(f"[Document Intelligence] Service call failed ({type(e).__name__}: {e}). Falling back to pypdf parser.")
            return _parse_with_pypdf_fallback(file_path)
    return _parse_with_pypdf_fallback(file_path)


def _parse_with_document_intelligence(file_path: str) -> tuple[list[ParsedSection], int]:
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    settings = get_settings()
    client = DocumentIntelligenceClient(
        endpoint=settings.document_intelligence_endpoint,
        credential=AzureKeyCredential(settings.document_intelligence_key),
    )
    with open(file_path, "rb") as f:
        poller = client.begin_analyze_document("prebuilt-layout", body=f)
    result = poller.result()

    sections: list[ParsedSection] = []
    current_type: SectionType = "title"
    buffer: list[str] = []
    buf_start_page = 1
    last_page = 1

    def flush(end_page: int):
        if buffer:
            sections.append(ParsedSection(
                section_type=current_type,
                text="\n".join(buffer).strip(),
                page_start=buf_start_page,
                page_end=end_page,
            ))

    for para in result.paragraphs or []:
        page_no = para.bounding_regions[0].page_number if para.bounding_regions else last_page
        last_page = page_no
        role = getattr(para, "role", None)
        text = para.content or ""
        # Prefer Document Intelligence's own role tag when present, but
        # don't require it -- for some layouts (e.g. this paper) DI never
        # tags headings as "sectionHeading"/"title" at all, so relying on
        # role alone left every section stuck as "title" forever. The regex
        # patterns are tightly anchored (whole-line-only) and short-text-only
        # below, so it's safe to also try classifying any short paragraph
        # regardless of role.
        is_heading_role = role in ("sectionHeading", "title")
        is_short_line = len(text.strip()) <= 60
        heading = _classify_heading(text) if (is_heading_role or is_short_line) else None
        if heading and heading != current_type:
            flush(page_no)
            current_type = heading
            buffer = []
            buf_start_page = page_no
        buffer.append(text)

    flush(last_page)
    num_pages = len(result.pages) if result.pages else last_page
    return sections, num_pages


def _parse_with_pypdf_fallback(file_path: str) -> tuple[list[ParsedSection], int]:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    num_pages = len(reader.pages)

    sections: list[ParsedSection] = []
    current_type: SectionType = "title"
    buffer: list[str] = []
    buf_start_page = 1

    def flush(end_page: int):
        if buffer:
            text = "\n".join(buffer).strip()
            if text:
                sections.append(ParsedSection(
                    section_type=current_type,
                    text=text,
                    page_start=buf_start_page,
                    page_end=end_page,
                ))

    for page_idx, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        for line in raw.split("\n"):
            heading = _classify_heading(line)
            if heading and heading != current_type:
                flush(page_idx)
                current_type = heading
                buffer = []
                buf_start_page = page_idx
            elif line.strip():
                buffer.append(line.strip())

    flush(num_pages)
    if not sections:
        # single-blob fallback if heading detection found nothing
        full_text = "\n".join((p.extract_text() or "") for p in reader.pages)
        sections = [ParsedSection(section_type="other", text=full_text,
                                   page_start=1, page_end=num_pages)]
    return sections, num_pages

import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import EmptyFileError, FileNotDecryptedError, PdfReadError

from curriculum.documents import DocumentConversionError, convert_word_document


class PodBookDocumentError(Exception):
    pass


_CHAPTER_HEADING = re.compile(
    r'^\s*(?:(?:chapter|part|section)\s+'
    r'(?:\d{1,3}|[ivxlcdm]+|[a-z]+)(?:\s*[:.\-].*)?|'
    r'(?:prologue|epilogue|appendix)(?:\s+[a-z0-9]+)?(?:\s*[:.\-].*)?)\s*$',
    re.IGNORECASE,
)
_MAX_BOOK_PAGES = 2000
_MAX_READER_PDF_BYTES = 50 * 1024 * 1024


def prepare_book_document(uploaded_file, duration_weeks):
    """Return readable PDF bytes and balanced page sections for the reading schedule."""
    if Path(uploaded_file.name).suffix.lower() == '.pdf':
        uploaded_file.seek(0)
        pdf_content = uploaded_file.read()
        uploaded_file.seek(0)
    else:
        try:
            pdf_content, _ = convert_word_document(uploaded_file)
        except DocumentConversionError as error:
            raise PodBookDocumentError(str(error)) from error

    if len(pdf_content) > _MAX_READER_PDF_BYTES:
        raise PodBookDocumentError('The prepared reader PDF must be 50 MB or smaller.')

    try:
        reader = PdfReader(BytesIO(pdf_content), strict=False)
        if reader.is_encrypted and not reader.decrypt(''):
            raise PodBookDocumentError(
                'Password-protected books are not supported. Upload an unlocked file.'
            )
        page_count = len(reader.pages)
        if not page_count:
            raise PodBookDocumentError('The uploaded book has no readable pages.')
        if page_count > _MAX_BOOK_PAGES:
            raise PodBookDocumentError(
                f'Books must have {_MAX_BOOK_PAGES} pages or fewer.'
            )

        page_texts = [(page.extract_text() or '').strip() for page in reader.pages]
    except PodBookDocumentError:
        raise
    except (EmptyFileError, FileNotDecryptedError, PdfReadError, OSError, ValueError) as error:
        raise PodBookDocumentError(
            'The book could not be read as a PDF. Check the file and try again.'
        ) from error

    headings = []
    for page_number, text in enumerate(page_texts, start=1):
        for line in text.splitlines():
            candidate = ' '.join(line.split())
            if len(candidate) <= 160 and _CHAPTER_HEADING.fullmatch(candidate):
                headings.append((page_number, candidate))
                break

    chapter_markers = []
    for page_number, title in headings:
        if not chapter_markers or chapter_markers[-1][0] != page_number:
            chapter_markers.append((page_number, title))
    if chapter_markers and chapter_markers[0][0] > 1:
        chapter_markers.insert(0, (1, 'Beginning'))

    sections = []
    use_chapter_boundaries = len(chapter_markers) >= duration_weeks
    for week_number in range(1, duration_weeks + 1):
        if use_chapter_boundaries:
            first_marker_index = ((week_number - 1) * len(chapter_markers)) // duration_weeks
            next_marker_index = (week_number * len(chapter_markers)) // duration_weeks
            start_page = chapter_markers[first_marker_index][0]
            end_page = (
                chapter_markers[next_marker_index][0] - 1
                if next_marker_index < len(chapter_markers)
                else page_count
            )
            section_headings = [
                title
                for _, title in chapter_markers[first_marker_index:next_marker_index]
            ]
        else:
            start_page = ((week_number - 1) * page_count) // duration_weeks + 1
            end_page = (week_number * page_count) // duration_weeks
            start_page = min(start_page, page_count)
            end_page = max(start_page, end_page)
            section_headings = [
                title
                for page_number, title in headings
                if start_page <= page_number <= end_page
            ]
        if section_headings:
            title = section_headings[0]
            if len(section_headings) > 1:
                title = f'{title} - {section_headings[-1]}'
        else:
            title = f'Pages {start_page}-{end_page}'
        sections.append({
            'week_number': week_number,
            'title': title[:200],
            'start_page': start_page,
            'end_page': end_page,
        })

    uploaded_file.seek(0)
    return pdf_content, sections

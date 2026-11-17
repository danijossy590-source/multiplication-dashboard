import re


_MARKER = re.compile(
    r'(?im)(?:^|[\n\t ]{2,})'
    r'(?P<label>Text|Scriptures?|Proposition)\s*:\s*'
    r'|(?:^|[\n\t ]{2,})(?P<heading>Introduction|Outlines|Conclusion):?(?=[\t ]|$)'
    r'|(?:^|[\n\t ]{2,})(?P<outline>\d+[.)]\s+[^:\n]{2,120}:)\s*'
)

_REQUIRED_SECTIONS = ('Scripture', 'Proposition', 'Introduction', 'Outline', 'Conclusion')


def structure_lesson(content):
    """Split common lesson labels into display sections without rewriting the text."""
    matches = list(_MARKER.finditer(content))
    sections = []

    if matches and content[:matches[0].start()].strip():
        sections.append({
            'heading': 'Lesson notes',
            'body': content[:matches[0].start()].strip(),
        })

    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip()

        if match.group('label'):
            label = match.group('label').rstrip(':').lower()
            label = 'Scripture' if label in {'text', 'scripture', 'scriptures'} else 'Proposition'
            heading = label
        elif match.group('heading'):
            heading = match.group('heading').title()
            if heading == 'Outlines':
                continue
        else:
            heading = match.group('outline').rstrip(':').strip()

        sections.append({'heading': heading, 'body': body})

    found = {
        section['heading']
        for section in sections
        if section['body']
    }
    if any(heading[0].isdigit() for heading in found):
        found.add('Outline')
    missing_sections = [
        section for section in _REQUIRED_SECTIONS
        if section not in found
    ]
    return {
        'sections': sections,
        'missing_sections': missing_sections,
        'is_structured': bool(sections),
    }

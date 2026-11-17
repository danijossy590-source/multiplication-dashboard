import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


class LessonAIError(Exception):
    pass


def generate_lesson_suggestions(content):
    base_url = settings.OLLAMA_BASE_URL.rstrip('/')
    if not base_url:
        raise LessonAIError('Local AI is not configured. Lesson structure checks still work.')

    prompt = (
        "You are assisting an editor of a Christian discipleship lesson. "
        "Use only the supplied lesson. Do not change, correct, interpret, or add doctrine, "
        "scripture references, or claims. Return JSON only with keys: "
        '"summary" (one short factual paragraph), "discussion_questions" '
        "(3 to 5 neutral questions based only on the lesson). "
        "If the lesson is unclear, describe only what is present.\n\n"
        f"LESSON:\n{content}"
    )
    request = Request(
        f'{base_url}/api/generate',
        data=json.dumps({
            'model': settings.OLLAMA_MODEL,
            'prompt': prompt,
            'stream': False,
            'format': 'json',
            'options': {'num_predict': 500, 'num_ctx': 4096},
        }).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urlopen(request, timeout=settings.OLLAMA_TIMEOUT) as response:
            payload = json.loads(response.read().decode('utf-8'))
        suggestions = json.loads(payload['response'])
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise LessonAIError(
            'Local AI is unavailable right now. Check that Ollama is running and the configured model is installed.'
        ) from error
    except (KeyError, TypeError, ValueError) as error:
        raise LessonAIError('Local AI returned an invalid response. Please try again.') from error

    summary = suggestions.get('summary')
    questions = suggestions.get('discussion_questions')
    if not isinstance(summary, str) or not isinstance(questions, list):
        raise LessonAIError('Local AI returned an invalid response. Please try again.')

    return {
        'summary': summary.strip()[:1200],
        'discussion_questions': [
            question.strip()[:500]
            for question in questions[:5]
            if isinstance(question, str) and question.strip()
        ],
    }

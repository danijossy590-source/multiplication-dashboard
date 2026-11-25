# multiplication-dashboard

## Curriculum assistant

Lesson upload remains available without AI. Lesson editors can run a section check and optionally request draft summaries and discussion questions from an AI provider. AI suggestions are not saved until an editor reviews and applies them. Set `AI_PROVIDER` in `.env` to `gemini`, `openrouter`, or `deepseek`. Docker Compose defaults to Gemini; all provider keys remain in `.env` and must not be committed.

### Ollama

The Docker Compose setup uses the `qwen2.5:1.5b` model by default. Set `AI_PROVIDER=ollama` in `.env`, then start the services and download the model once:

```powershell
docker compose --profile local-ai up -d --build
docker compose exec ollama ollama pull qwen2.5:1.5b
```

The optional `local-ai` profile starts Ollama. The model is stored in the `ollama_data` volume. Pulling it requires an internet connection and disk space; inference runs on the host allocated to Docker, so there is no AI API charge but it still uses memory, CPU/GPU, and electricity. If it is stopped or the model is missing, section checks and normal lesson uploads continue to work and AI suggestions are unavailable.

To use another Ollama model, set `OLLAMA_MODEL` in the environment and pull that model in the Ollama container. Outside Docker Compose, configure `OLLAMA_BASE_URL` and `OLLAMA_MODEL` for Django; leave `OLLAMA_BASE_URL` empty to disable Ollama requests.

### Gemini

Set these values in `.env` to use Google's Gemini API:

```text
AI_PROVIDER=gemini
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-3.5-flash-lite
```

Create an API key in [Google AI Studio](https://aistudio.google.com/apikey). Keep it secret and out of source control. The model can be changed with `GEMINI_MODEL`; check Google's [model and pricing information](https://ai.google.dev/gemini-api/docs/pricing) for current availability and free-tier limits. Requests send lesson text to Google's API, and free-tier data handling may differ from paid-tier handling.

### OpenRouter

Set these values in `.env` to use [OpenRouter](https://openrouter.ai/keys):

```text
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=your_api_key
OPENROUTER_MODEL=provider/model-name
```

Use the model identifier shown in your OpenRouter account. The API base defaults to `https://openrouter.ai/api/v1`; optional `OPENROUTER_SITE_URL` and `OPENROUTER_APP_NAME` values provide OpenRouter's application attribution headers.

### DeepSeek

Set these values in `.env` to use [DeepSeek](https://platform.deepseek.com/):

```text
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_MODEL=deepseek-chat
```

The API base defaults to `https://api.deepseek.com`.

Changing `AI_PROVIDER` switches both lesson assistance and AI course generation. For the hosted providers, lesson text is sent to the selected provider for processing; use the provider's current privacy, retention, and pricing terms when deciding what to submit. Restart the web service after changing `.env` (for example, `docker compose up -d --build web`).

## Courses and learner progress

Admins and pod leaders can create courses from **Curriculum**, then add ordered modules. Upload lessons and select their module to include them in the course. Course managers can set up one multiple-choice quiz per module and choose a passing score. Learners open a course, complete lessons in order, and pass each configured quiz; progress is saved per learner and a printable completion certificate becomes available when the course requirements are met.

Use **Create Progressive Course** to name a course, choose its audience, and select up to 24 unassigned lessons (up to 20,000 combined content characters). The configured AI provider organizes them into an ordered progression of up to 12 modules, with learning objectives, step-by-step guidance, and multiple-choice quizzes for every module. Courses are published immediately, so managers should review the result afterward. The original lesson text is not rewritten. Apply database changes with `python manage.py migrate` during deployment.

## Community Q&A

The public Community Q&A board is available at `/questions/` and is linked from the dashboard and site navigation. Visitors can post questions and browse questions and replies; only signed-in users can reply. Authors can choose whether to display their name, and signed-in users can choose anonymity separately for each reply. Questions and replies are public, so users should not include private information. Signed-in users can report content, and staff can review reports and hide content in Django admin at `/django-admin/`.

## Pod access and administration

Pod admins and leaders can share the Pod's reusable access code from its detail page. Signed-in users can enter the code from the Pods page to join as members; leaders and admins can rotate the code to invalidate the previous one. Only admins can delete a Pod. Deleting a Pod permanently removes its memberships, chat, meetings, book assignments, courses, lessons, and related progress.

Pod leaders can assign a PDF or Word book to their Pod and set a reading schedule of up to 52 weeks. Pod participants can download the book, see who is on track or behind, and submit or update one review for each available week. Members, leaders, and participating mentors can comment on reviews and reply in threads. Assigning a new book starts a new schedule while retaining the previous assignment and its reviews. Pod-scoped courses and their lessons are available to Pod members from Curriculum, even before the course is published globally.

## Account recovery email

The login page includes a password-reset flow. For local development, reset emails are written to the Django console. Configure SMTP for delivery in a deployed environment using `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, and `DEFAULT_FROM_EMAIL`. Keep mail credentials in environment variables; never commit them. New accounts require an email address so members can recover their passwords.
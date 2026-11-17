# multiplication-dashboard

## Local curriculum assistant

Lesson upload remains available without AI. Lesson editors can run a section check and optionally request draft summaries and discussion questions from a locally hosted Ollama model. AI suggestions are not saved until an editor reviews and applies them.

The Docker Compose setup uses the `qwen2.5:1.5b` model by default. Start the services, then download the model once:

```powershell
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:1.5b
```

The model is stored in the `ollama_data` volume. Pulling it requires an internet connection and disk space; inference runs on the host allocated to Docker, so there is no AI API charge but it still uses memory, CPU/GPU, and electricity. The lesson assistant sends lesson text to this Ollama service. If it is stopped or the model is missing, section checks and normal lesson uploads continue to work and AI suggestions are unavailable.

To use another Ollama model, set `OLLAMA_MODEL` in the environment and pull that model in the Ollama container. Outside Docker Compose, configure `OLLAMA_BASE_URL` and `OLLAMA_MODEL` for Django; leave `OLLAMA_BASE_URL` empty to disable AI requests.

## Courses and learner progress

Admins and pod leaders can create courses from **Curriculum**, then add ordered modules. Upload lessons and select their module to include them in the course. Course managers can set up one multiple-choice quiz per module and choose a passing score. Learners open a course, complete lessons in order, and pass each configured quiz; progress is saved per learner and a printable completion certificate becomes available when the course requirements are met. Apply database changes with `python manage.py migrate` during deployment.
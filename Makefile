.PHONY: run-dev up down scheduler worker runserver-dev dashboard

COMPOSE = docker compose -f compose.yaml -f compose-dev.yaml

# db, rabbitmq (and migrations via `init`) in Docker; django, celery-beat
# and celery-worker turned off (compose-dev.yaml) — run them locally with
# `make runserver-dev` / `make scheduler` / `make worker`. `scheduler` and
# `worker` bring the Docker infra up first (detached); `runserver-dev` only
# starts Django, so run `make up` beforehand if the infra isn't running.
# `run-dev` also starts the dashboard and spark containers.
run-dev:
	DASHBOARD_UPSTREAM=dashboard:8501 $(COMPOSE) --profile dashboard --profile spark up
up:
	$(COMPOSE) up -d
	$(COMPOSE) wait init

down:
	$(COMPOSE) down

runserver-dev:
	uv run python manage.py runserver 0.0.0.0:8000

scheduler:
	uv run celery -A core.frameworks.celery_app.app beat -l info

worker:
	uv run celery -A core.frameworks.celery_app.app worker -l info

dashboard:
	uv run streamlit run src/core/frameworks/streamlit_app/app.py --server.address=0.0.0.0

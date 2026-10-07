# ordy

Ordonnanceur (job scheduler) — Django, Django Admin, PostgreSQL, Celery Beat, RabbitMQ.

## Architecture

Le projet suit une architecture en oignon / hexagonale (Clean Architecture) :
le domaine ne dépend de rien, et toute dépendance pointe vers l'intérieur.

```
interfaces  --->  frameworks  --->  application  --->  domain
(CLI, admin)      (Django,          (use cases,        (entités, VOs,
                   Celery,           ports)              events, repos
                   RabbitMQ)                              interfaces)
```

- **`core.domain`** — logique métier pure. Entités, value objects,
  événements de domaine, exceptions, interfaces de repository. Zéro
  import de Django/Celery/RabbitMQ.
- **`core.application`** — use cases qui orchestrent le domaine via des
  *ports* (interfaces abstraites : `Clock`, `TaskDispatcher`,
  `EventPublisher`, ...). Ne dépend que de `core.domain`.
- **`core.frameworks`** — adapters concrets : Django (ORM, admin,
  settings), Celery (app, tasks, Celery Beat), implémentations des
  repositories et des ports. Dépend de `application` et `domain`, jamais
  l'inverse.
- **`core.interfaces`** *(à venir)* — points d'entrée : CLI (Typer),
  éventuellement une API.

Organisation par bounded context : un sous-package par contexte métier
(`scheduling` pour l'instant), présent à la fois sous `domain/` et
`application/`.

```
src/core/
├── domain/
│   └── scheduling/
│       ├── entities.py       # Job (aggregate root), Execution (aggregate root)
│       ├── value_objects.py  # JobId, ExecutionId, JobStatus, Schedule (Cron/Interval), TaskReference
│       ├── events.py         # JobCreated, ExecutionFailed, ...
│       ├── exceptions.py
│       ├── repositories.py   # JobRepository, ExecutionRepository (interfaces)
│       └── services.py       # CronCalculator (interface)
├── application/
│   └── scheduling/
│       ├── ports.py          # Clock, TaskDispatcher, EventPublisher (interfaces)
│       └── use_cases.py      # SchedulingUseCases : create_job, trigger_job_now, ...
└── frameworks/
    └── django_app/           # squelette, à implémenter (settings, models, admin, repos Django)
```

### Modèle de domaine (contexte "scheduling")

- **`Job`** (aggregate root) : un travail récurrent — nom, référence
  vers la tâche à exécuter (`TaskReference`, ex. un nom de tâche
  Celery), son `Schedule` (`IntervalSchedule` ou `CronSchedule`), son
  statut (`draft` / `active` / `paused` / `archived`).
- **`Execution`** (aggregate root séparé, référence `job_id`) : une
  exécution donnée d'un `Job` — statut (`pending` / `running` /
  `succeeded` / `failed` / `cancelled`), horodatages, erreur éventuelle.
  Séparé de `Job` pour que l'historique des exécutions grossisse sans
  alourdir l'agrégat `Job`.

### Point à trancher : `django-celery-beat` vs scheduler custom

`pyproject.toml` liste `celery-beat` comme dépendance — ce n'est pas le
paquet standard (qui est `django-celery-beat`, table Django dédiée aux
periodic tasks). Deux options pour la prochaine étape (bootstrap
Django/Celery) :

1. **`django-celery-beat`** : rapide à mettre en place, mais source de
   vérité dupliquée (sa propre table `PeriodicTask` en plus de notre
   agrégat `Job`).
2. **Scheduler Celery Beat custom** lisant directement via
   `JobRepository` : notre `Job` reste l'unique source de vérité, plus
   fidèle au DDD, un peu plus de code à écrire.

À valider avant le bootstrap Django/Celery.

## Dev

```bash
uv sync
uv run python -c "import core"  # vérifie que le package est bien installable
```

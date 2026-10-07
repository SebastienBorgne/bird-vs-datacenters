"""Idempotently ensure the bootstrap Django superuser exists.

Reads credentials from `core.settings` (env vars `APP_RUN__DJANGO_USER_NAME`
/ `APP_RUN__DJANGO_USER_PASSWORD`). Run by the `init` container after
migrations — `python -m core.frameworks.django_app.entrypoints.ensure_superuser`.
Safe to run on every startup: it upserts rather than failing when the user
already exists, unlike `manage.py createsuperuser --noinput`.
"""

from __future__ import annotations

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.frameworks.django_app.config.settings")
django.setup()

from django.contrib.auth import get_user_model

from core.settings import config


def main() -> None:
    username = config.django.DJANGO_SUPERUSER_USERNAME
    password = config.django.DJANGO_SUPERUSER_PASSWORD
    if not username or not password:
        print(
            "APP_RUN__DJANGO_USER_NAME / APP_RUN__DJANGO_USER_PASSWORD not set — "
            "skipping superuser bootstrap."
        )
        return

    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        username=username,
        defaults={"is_staff": True, "is_superuser": True},
    )
    user.is_staff = True
    user.is_superuser = True
    user.set_password(password)
    user.save()
    print(f"Superuser {'created' if created else 'updated'}: {username}")


if __name__ == "__main__":
    main()

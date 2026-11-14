import os
import pathlib
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

ADMIN_URL = os.environ.get("TEST_ADMIN_DATABASE_URL", "postgresql://postgres@localhost:5432/postgres")
MIGRATIONS = pathlib.Path(__file__).resolve().parents[2] / "supabase" / "migrations"


@pytest.fixture()
def db_url():
    """Her test için boş bir veritabanı oluşturur ve migration'ları uygular."""
    name = f"fds_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
    url = ADMIN_URL.rsplit("/", 1)[0] + f"/{name}"
    with psycopg.connect(url, autocommit=True) as conn:
        for f in sorted(MIGRATIONS.glob("*.sql")):
            conn.execute(f.read_text())
    yield url
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'drop database "{name}" with (force)')


@pytest.fixture()
def conn(db_url):
    with psycopg.connect(db_url, autocommit=True, row_factory=dict_row) as c:
        yield c


def make_project(conn, slug="pompei-son-gunu"):
    pid = conn.execute(
        "insert into projects (slug, title, topic) values (%s, %s, %s) returning id",
        (slug, "Pompei'nin Son Günü", "Pompei'nin Son Günü — Vezüv'ün Yok Ettiği Şehir"),
    ).fetchone()["id"]
    job = conn.execute("select create_pipeline_job(%s) as id", (pid,)).fetchone()["id"]
    return pid, job


def steps(conn, job):
    return {r["step_key"]: r for r in conn.execute(
        "select * from job_steps where job_id=%s order by seq", (job,)).fetchall()}

import json
from dataclasses import dataclass
from uuid import uuid4
from .db import one, query

MAX_ATTEMPTS = 3

@dataclass
class JobError(Exception):
    message: str
    retryable: bool = False

class LeaseLost(Exception):
    pass

def enqueue(conn, owner, kind, target, dedupe, payload=None):
    return one(conn, """
      INSERT INTO jobs(owner,kind,target,dedupe,payload) VALUES (:o,:k,:t,:d,CAST(:p AS jsonb))
      ON CONFLICT(dedupe) DO UPDATE SET dedupe=excluded.dedupe
      RETURNING id AS job_id, target AS target_id, status
    """, o=owner, k=kind, t=target, d=dedupe, p=json.dumps(payload or {}))

def claim(conn):
    query(conn, """
        UPDATE jobs SET status=CASE WHEN cancel_requested THEN 'cancelled' ELSE 'failed' END,
          error=CASE WHEN cancel_requested THEN NULL ELSE 'El proceso se interrumpió tres veces. Puedes reintentar.' END,
          lease=NULL,lease_until=NULL
        WHERE (status='running' AND lease_until<=now() AND (attempts>=:maximum OR cancel_requested))
           OR (status='queued' AND cancel_requested)
    """, maximum=MAX_ATTEMPTS)
    row = one(conn, """
        WITH next_job AS (
          SELECT id FROM jobs WHERE (status='queued' OR (status='running' AND lease_until<=now()))
            AND NOT cancel_requested AND available<=now() AND attempts<:maximum
          ORDER BY available,created FOR UPDATE SKIP LOCKED LIMIT 1
        )
        UPDATE jobs SET status='running', attempts=attempts+1, lease=:lease,
          lease_until=now()+interval '45 seconds', progress=5
        WHERE id=(SELECT id FROM next_job) RETURNING *
    """, lease=uuid4(), maximum=MAX_ATTEMPTS)
    return dict(row) if row else None

def renew(conn, job, progress=None):
    row = one(conn, """
        UPDATE jobs SET lease_until=now()+interval '45 seconds',progress=coalesce(:p,progress)
        WHERE id=:id AND lease=:lease AND status='running' AND lease_until>now() AND NOT cancel_requested
        RETURNING id
    """, id=job["id"], lease=job["lease"], p=progress)
    if row is None:
        raise LeaseLost()

def guard(conn, job):
    row = one(conn, """SELECT id FROM jobs WHERE id=:id AND lease=:lease AND status='running'
      AND lease_until>now() AND NOT cancel_requested FOR UPDATE""", id=job["id"], lease=job["lease"])
    if row is None:
        raise LeaseLost()

def complete(conn, job):
    query(conn, """UPDATE jobs SET status='done',progress=100,error=NULL,lease=NULL,lease_until=NULL
                   WHERE id=:id AND lease=:lease""", id=job["id"], lease=job["lease"])

def fail(conn, job, exc):
    retry = exc.retryable and job["attempts"] < MAX_ATTEMPTS
    query(conn, """UPDATE jobs SET status=CASE WHEN cancel_requested THEN 'cancelled' ELSE :state END,
                   error=CASE WHEN cancel_requested THEN NULL ELSE :error END,
                   available=now()+(:delay * interval '1 second'),lease=NULL,lease_until=NULL
                   WHERE id=:id AND lease=:lease AND lease_until>now()""",
          id=job["id"], lease=job["lease"], state="queued" if retry else "failed",
          error=exc.message, delay=4 ** job["attempts"])

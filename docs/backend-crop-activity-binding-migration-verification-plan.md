# Crop activity binding migration 071 verification plan

Status: source proposal only; execution requires separate approval.

## Scope

The verifier targets one freshly provisioned, dedicated, empty, local
PostgreSQL database. Its name must match
`agrios_migration_071_disposable_*`, and the operator must set
`MIGRATION_071_DISPOSABLE_APPROVED=YES`. PostgreSQL does not retain trustworthy
provenance for the template used to create a database, so the operator must
provision it from the reviewed clean `template0` command and separately attest
that fact with `MIGRATION_071_CLEAN_TEMPLATE=template0`. This is an explicit
operator assertion, not database-derived proof.

The server must make both PostGIS and `pg_trgm` available to the migration
chain. The script accepts only psycopg2 PostgreSQL URLs with a loopback host and
an explicit port `5432`, refuses URL query options, and verifies the actual
server address is loopback and the actual server port is `5432` on every
admitted connection, including reopen. It also refuses other database names,
unexpected user schemas or extensions, pre-existing event triggers, and any
pre-existing public relations, types, or routines.

Every Alembic operation runs on the exact SQLAlchemy connection that passed the
database-name, primary-server, empty-target, and search-path checks. The
connection is pinned to `public, pg_catalog`; the Alembic version table is
pinned to `public`; and bounded lock, statement, and idle-transaction timeouts
apply before migration work starts.

On the verifier-supplied connection path, Alembic neither replaces the URL from
application settings nor reinitializes logging. The supplied SQLAlchemy engine
hides SQL parameter values. The ordinary application Alembic path retains its
existing settings URL and logging behavior.

The script does not create or drop a database. It does not read application
data, call HTTP, start the application, or enable activity submission.

## Verified sequence

1. Apply the committed migration chain to revision `070` in the empty database.
2. Insert one synthetic activity containing no real tenant, farmer, or actor
   data and retain its complete PostgreSQL JSON representation.
3. Upgrade to `071`; inspect complete additive column types, lengths,
   precision, scale, timestamp type and timezone, nullability and defaults;
   exact binding-table column sets; primary and foreign-key targets and delete
   actions; executable check-constraint truth tables; nonunique, nonpartial
   indexes and their column order; uniqueness; empty binding tables; revision;
   NULL irrigation defaults; and retained activity values.
4. Downgrade cleanly to `070`; confirm removal of only the additive schema and
   value-equivalent retained activity fields.
5. Upgrade again to `071`, dispose the engine, open a fresh physical
   connection, and confirm the revision, complete schema, NULL defaults, and
   retained activity values.
6. Insert synthetic processed-event and binding rows; snapshot all three rows;
   require downgrade to fail with `071_DOWNGRADE_BLOCKED`; and require the
   revision, complete schema, activity, processed event, and both bindings to
   retain their exact PostgreSQL values before scoped cleanup. Each cleanup
   statement is limited to the synthetic keys and must affect exactly one row.
7. Set `irrigation_source` alone, reread and require its exact seeded value while
   `duration_hours` remains NULL, and require the same refusal with exact
   activity preservation. Clear it, then independently seed and reread
   `duration_hours` while requiring `irrigation_source` to remain NULL before
   repeating the refusal and preservation checks.
8. Clear the synthetic duration, complete one final clean downgrade and upgrade,
   dispose the engine, and verify through a fresh physical connection that the
   database is at revision `071` with the complete additive schema, empty
   binding tables, NULL irrigation values, and the original synthetic activity
   intact.

## Evidence boundary

Success is limited to the exact local PostgreSQL instance, migration sources,
and disposable database used by the operator. It does not establish production
upgrade safety, application startup, live data compatibility, command-path
behavior, concurrency under application traffic, or deployment readiness.

The operator should retain only the sanitized phase-marker output and source
commit/hash context. At startup the verifier prints SHA-256 identities for the
verifier, migration `071`, the Alembic environment, and a deterministic digest
of the complete sorted migration chain. The database URL and credentials must
not be captured. The verifier disposes its engine but does not remove the
database. After evidence review, database deletion is a separate operator
action.

`PRODUCTION_RECOVERY_LIVE_NOT_APPROVED` remains closed.

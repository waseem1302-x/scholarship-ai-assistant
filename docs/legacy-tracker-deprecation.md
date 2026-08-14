# Legacy Tracker deprecation

Applications are the canonical student application resource. The React client no longer writes
`/saved-opportunities`, and `/tracker` redirects to `/applications`.

The legacy endpoints remain available temporarily for rolling-deployment and old-client safety.
Every response includes `Deprecation`, `Sunset`, `Link`, and `Warning` headers pointing clients to
`/applications`. The compatibility table must not be dropped until all of these conditions hold:

1. the backfill/no-loss migration check passes on a production-like PostgreSQL copy;
2. legacy write telemetry is zero for at least one complete client-support window;
3. exports and account deletion include both canonical and compatibility records;
4. the contract migration is deployed only after every live API/worker revision supports it.

The announced compatibility sunset is 1 February 2027. Changing it requires an API compatibility
review. A later contract migration may archive and drop the legacy table; it must not be bundled
with the expand/deprecate release.

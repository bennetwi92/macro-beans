// Neon endpoints for the cockpit's Requests (wishlist) page.
// These are PUBLIC by design — security is enforced by Neon Auth (JWT) + Postgres
// Row-Level Security at the database, not by hiding these URLs. No secrets here;
// the DB connection string / passwords never appear in the browser or the repo.
export const AUTH_URL = "https://ep-long-smoke-af2k10wy.neonauth.c-2.us-west-2.aws.neon.tech/neondb/auth";
export const DATA_API_URL = "https://ep-long-smoke-af2k10wy.apirest.c-2.us-west-2.aws.neon.tech/neondb/rest/v1";

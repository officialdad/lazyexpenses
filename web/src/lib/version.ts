// #62: the version the SERVED SHELL was built from. Baked at build time via
// VITE_APP_VERSION (Dockerfile ARG -> ENV in the node stage, fed from docker.yml's
// steps.meta.outputs.version). A bare `npm run build` or a `docker build` with no
// --build-arg gets `dev` — an honest non-release string, never a stale hardcoded semver.
export const VERSION: string = import.meta.env.VITE_APP_VERSION || 'dev';

/** What the footer prints. The shell and the pod can legitimately hold different builds —
 *  the PWA caches aggressively, the server does not — and that disagreement is the whole
 *  point, so both are shown only when they differ. Empty `server` = /healthz not answered
 *  (offline, or an older server with no version field): show what we do know. */
export function versionLabel(client: string, server: string): string {
	return !server || server === client ? client : `${client} · server ${server}`;
}

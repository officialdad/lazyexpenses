import { describe, it, expect } from 'vitest';
import { VERSION, versionLabel } from './version';

describe('version', () => {
	it('falls back to dev when nothing was baked in at build time', () => {
		// vitest runs with VITE_APP_VERSION unset, i.e. exactly the bare `npm run build`
		// / `docker build` case. A real semver here would mean a hardcoded version.
		expect(VERSION).toBe('dev');
	});
	it('shows one version when the shell and the server agree', () => {
		expect(versionLabel('0.11.0', '0.11.0')).toBe('0.11.0');
	});
	it('shows both when a cached shell is behind the server', () => {
		expect(versionLabel('0.11.0', '0.12.0')).toBe('0.11.0 · server 0.12.0');
	});
	it('shows the shell alone when the server did not answer', () => {
		expect(versionLabel('0.11.0', '')).toBe('0.11.0');
	});
});

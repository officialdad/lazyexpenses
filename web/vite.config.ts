import { sveltekit } from '@sveltejs/kit/vite';
import { SvelteKitPWA } from '@vite-pwa/sveltekit';
import { defineConfig } from 'vitest/config';
import tailwindcss from '@tailwindcss/vite';
import { svelteTesting } from '@testing-library/svelte/vite';

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit(),
		SvelteKitPWA({
			registerType: 'autoUpdate',
			strategies: 'generateSW',
			scope: '/',
			base: '/',
			manifest: {
				name: 'Credit-Card Spend',
				short_name: 'CC Spend',
				description: 'Lazy credit-card overview — am I overcommitting?',
				theme_color: '#000000',
				background_color: '#000000',
				display: 'standalone',
				start_url: '/',
				icons: [
					// Separate `any` from `maskable`: one "any maskable" icon is cropped by
					// the launcher's maskable safe-zone even when used as the plain `any` icon.
					// Keep un-cropped icons for `any` + a dedicated 512 for `maskable`.
					{ src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
					{ src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
					{
						src: '/pwa-512x512.png',
						sizes: '512x512',
						type: 'image/png',
						purpose: 'maskable'
					}
				]
			},
			workbox: {
				globPatterns: ['client/**/*.{js,css,ico,png,svg,webp,json}'],
				globIgnores: ['**/data/app.json', '**/data/paid.json'],
				navigateFallback: '/',
				runtimeCaching: [
					{
						urlPattern: ({ url }: { url: URL }) => url.pathname === '/data/app.json',
						handler: 'NetworkFirst' as const,
						options: { cacheName: 'app-data', expiration: { maxEntries: 1 } }
					},
					{
						// Cross-device paid-bill state — same NetworkFirst rule as app.json, else an
						// installed PWA caches the empty [] and never sees server updates.
						urlPattern: ({ url }: { url: URL }) => url.pathname === '/data/paid.json',
						handler: 'NetworkFirst' as const,
						options: { cacheName: 'paid-data', expiration: { maxEntries: 1 } }
					}
				]
			},
			devOptions: { enabled: true, type: 'module', navigateFallback: '/' }
		}),
		svelteTesting()
	],
	test: {
		environment: 'jsdom',
		setupFiles: ['./src/test-setup.ts']
	}
});

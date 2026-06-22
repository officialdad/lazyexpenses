import { sveltekit } from '@sveltejs/kit/vite';
import { SvelteKitPWA } from '@vite-pwa/sveltekit';
import { defineConfig } from 'vite';
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
				navigateFallback: '/'
			},
			devOptions: { enabled: true, type: 'module', navigateFallback: '/' }
		}),
		svelteTesting()
	],
	test: {
		environment: 'jsdom'
	}
});

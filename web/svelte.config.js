import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({ fallback: 'index.html', precompress: false, strict: true }),
    // Empty in the real deployment (the container serves the app at /). The GitHub Pages
    // demo builds with BASE_PATH=/lazyexpenses, so every runtime path has to go through
    // `base` from $app/paths rather than being written absolute.
    paths: { base: process.env.BASE_PATH ?? '' },
    alias: { $lib: 'src/lib' }
  }
};
export default config;

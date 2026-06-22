import fixture from '../static/data/app.json';
import { loadAppData } from './lib/data';

// Populate the runed store once per test file so component tests that read `app`
// synchronously see real data (mirrors the old static-import behavior).
await loadAppData((async () =>
  ({ ok: true, status: 200, json: async () => fixture })) as unknown as typeof fetch);

import raw from './data/app.json';
import type { AppData } from './types';
export const app = raw as unknown as AppData;
export const latestMonth = app.months[app.months.length - 1] ?? '';

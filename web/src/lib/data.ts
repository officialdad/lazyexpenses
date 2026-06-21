import raw from './data/app.json';
import type { AppData } from './types';
import { monthlySeries, byCategory, topMerchants } from './trends';

export const app = raw as unknown as AppData;
export const latestMonth = app.months[app.months.length - 1] ?? '';

// All-time aggregates computed once at import (not per chart-render).
// These depend on no reactive state, so the desktop/mobile dual subtree
// renders chart components twice but recomputes nothing.
export const monthlyAll = monthlySeries(app.rows, app.months, app.nonSpend);
export const byCategoryAll = byCategory(app.rows, null, app.nonSpend);
export const topMerchantsAll = topMerchants(app.rows, 20, app.nonSpend);

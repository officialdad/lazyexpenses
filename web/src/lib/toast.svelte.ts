// Minimal toast stack. Auto-dismisses. No library — add svelte-sonner only if we ever
// need stacking limits, actions, or swipe-to-dismiss.
export type ToastKind = 'info' | 'error';
export interface Toast {
  id: number;
  msg: string;
  kind: ToastKind;
}

let _id = 0;
export const toasts = $state<Toast[]>([]);

export function toast(msg: string, kind: ToastKind = 'info', ms = 2500): void {
  const id = ++_id;
  toasts.push({ id, msg, kind });
  setTimeout(() => {
    const i = toasts.findIndex((t) => t.id === id);
    if (i >= 0) toasts.splice(i, 1);
  }, ms);
}

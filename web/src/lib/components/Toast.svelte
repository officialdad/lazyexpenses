<script lang="ts">
  import { toasts } from '$lib/toast.svelte';
</script>

<!-- Always-present live region so inserted messages are announced. Sits above the
     mobile bottom nav; pointer-events-none so toasts never block taps underneath. -->
<div
  class="fixed inset-x-0 bottom-20 z-[60] flex flex-col items-center gap-2 px-4 pointer-events-none"
  aria-live="polite"
>
  {#each toasts as t (t.id)}
    <div
      class="w-full max-w-md border px-4 py-2 text-center text-sm font-bold shadow-lg"
      role={t.kind === 'error' ? 'alert' : 'status'}
      style="background:var(--surface3);border-color:var(--divider2);color:{t.kind === 'error'
        ? 'var(--danger-text)'
        : 'var(--text)'}"
    >
      {t.msg}
    </div>
  {/each}
</div>

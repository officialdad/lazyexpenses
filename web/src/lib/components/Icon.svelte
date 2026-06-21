<script lang="ts">
  import { app } from '$lib/data';
  let { name, size = 24, class: cls = '' }: { name: string; size?: number; class?: string } = $props();
  const d = $derived(app.icons[name] ?? '');
</script>
<svg viewBox="0 0 24 24" width={size} height={size} class={cls} fill="currentColor" aria-hidden="true">
  <path d={d} />
</svg>

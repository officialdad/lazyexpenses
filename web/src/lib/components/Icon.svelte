<script lang="ts">
  import { app } from '$lib/data';
  let { name, size = 24, class: cls = '' }: { name: string; size?: number; class?: string } = $props();
  // #64: an unknown name used to render `''` — an invisible icon and a silent failure.
  // The table arrives in app.json, which is only rewritten when the pipeline runs, so a
  // deploy that adds an icon renders nothing until then. Hardcoded (mdi square-outline)
  // rather than read from app.icons, because a stale table is exactly the failing case.
  const MISSING = 'M3,3H21V21H3V3M5,5V19H19V5H5Z';
  const d = $derived(app.icons[name] || MISSING);
</script>
<svg viewBox="0 0 24 24" width={size} height={size} class={cls} fill="currentColor" aria-hidden="true">
  <path d={d} />
</svg>

<script lang="ts">
  import { app } from '$lib/data';
  import { ceiling } from '$lib/ceiling.svelte';
  import { computeHeadroom } from '$lib/headroom';
  import { rm } from '$lib/fmt';

  let { month }: { month: string } = $props();

  let editingCeiling = $state(false);
  let ceilInput = $state(ceiling.value);

  const h = $derived(computeHeadroom({
    rows: app.rows, month, ceiling: ceiling.value, committed: app.committed, nonSpend: app.nonSpend
  }));
  const total = $derived(Math.max(ceiling.value, h.used));
  const w = (n: number) => Math.max(0, (n / total) * 100) + '%';
  const pill = $derived(
    h.status === 'over'
      ? { t: 'Over ceiling', c: 'var(--over)' }
      : h.status === 'warn'
      ? { t: 'Approaching', c: 'var(--accent)' }
      : { t: 'On track', c: 'var(--ok)' }
  );

  function openCeilingEditor() {
    ceilInput = ceiling.value;
    editingCeiling = true;
  }

  function applyEdit() {
    const v = Number(ceilInput);
    ceiling.set(v);
    editingCeiling = false;
  }

  function onCeilKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') applyEdit();
    if (e.key === 'Escape') editingCeiling = false;
  }
</script>

<section aria-label="Headroom hero">
  <p class="text-[11px] uppercase tracking-widest" style="color:var(--muted)">Free to spend</p>
  <p class="tnum font-extrabold leading-none" style="font-size:40px;color:var(--accent)">{rm(h.free)}</p>

  <div class="flex h-6 mt-3 text-[9px] font-extrabold overflow-hidden border" style="border-color:var(--divider)">
    <span class="flex items-center justify-center overflow-hidden" style="width:{w(h.locked)};background:var(--c-locked);color:#fff">{rm(h.locked).replace('RM','')}</span>
    <span class="flex items-center justify-center overflow-hidden" style="width:{w(h.spent)};background:var(--c-spent);color:#fff">{rm(h.spent).replace('RM','')}</span>
    <span class="flex items-center justify-center overflow-hidden" style="width:{w(Math.max(0,h.free))};background:var(--c-free);color:#000">{rm(Math.max(0,h.free)).replace('RM','')}</span>
  </div>

  <div class="flex gap-4 mt-2 text-[9px] uppercase font-bold" style="color:var(--muted)">
    <span><i class="inline-block w-2 h-2 mr-1" style="background:var(--c-locked)"></i>locked</span>
    <span><i class="inline-block w-2 h-2 mr-1" style="background:var(--c-spent)"></i>spent</span>
    <span><i class="inline-block w-2 h-2 mr-1" style="background:var(--c-free)"></i>free</span>
  </div>

  <div class="flex items-center gap-2 mt-3">
    <span
      class="inline-block px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wide text-black"
      style="background:{pill.c}"
    >
      {pill.t}
    </span>

    {#if editingCeiling}
      <label class="flex items-center gap-1 text-[10px] font-bold" style="color:var(--muted)">
        Ceiling:
        <input
          type="number"
          inputmode="numeric"
          min="1"
          aria-label="Monthly ceiling"
          class="w-24 px-2 py-0.5 text-[14px] font-extrabold tnum border"
          style="background:var(--surface);color:var(--text);border-color:var(--accent);outline:none"
          bind:value={ceilInput}
          onblur={applyEdit}
          onkeydown={onCeilKeydown}
          autofocus
        />
      </label>
    {:else}
      <button
        class="text-[10px] font-bold uppercase tracking-wide px-2 py-1 border"
        style="color:var(--muted);border-color:var(--divider);background:var(--surface)"
        onclick={openCeilingEditor}
        aria-label="Edit monthly ceiling, currently {rm(ceiling.value)}"
        title="Edit ceiling"
      >
        {rm(ceiling.value)} ceiling ✎
      </button>
    {/if}
  </div>
</section>

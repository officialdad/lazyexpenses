<script lang="ts">
  import { app } from '$lib/data';
  import { search, filterRows, MAGNIFY } from '$lib/search.svelte';
  import { rm, monthLabel } from '$lib/fmt';
  import Icon from '$lib/components/Icon.svelte';

  // MDI "close" path — also not in the app.icons dict.
  const CLOSE =
    'M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z';

  let query = $state('');
  let inputEl = $state<HTMLInputElement | null>(null);

  const res = $derived(filterRows(app.rows, query));

  function close() {
    search.open = false;
    query = '';
  }

  // On open: focus the input, trap Escape, restore focus on close.
  $effect(() => {
    if (!search.open) return;
    const prev = document.activeElement as HTMLElement | null;
    inputEl?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      prev?.focus();
    };
  });
</script>

{#if search.open}
  <div
    class="fixed inset-0 z-[60] flex flex-col"
    style="background:var(--bg)"
    role="dialog"
    aria-modal="true"
    aria-label="Search transactions"
  >
    <div class="flex items-center gap-2 border-b px-4 py-3" style="border-color:var(--divider)">
      <span style="color:var(--muted)">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
          <path d={MAGNIFY} />
        </svg>
      </span>
      <input
        bind:this={inputEl}
        bind:value={query}
        type="search"
        inputmode="search"
        autocomplete="off"
        placeholder="Search transactions…"
        class="flex-1 bg-transparent text-base outline-none"
        style="color:var(--text)"
      />
      <button
        type="button"
        onclick={close}
        aria-label="Close search"
        class="shrink-0 p-1"
        style="color:var(--muted)"
      >
        <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true">
          <path d={CLOSE} />
        </svg>
      </button>
    </div>

    <div class="flex-1 overflow-y-auto px-4 py-2">
      {#if !query.trim()}
        <p class="py-8 text-center text-sm" style="color:var(--muted)">
          Type to search {app.rows.length} transactions.
        </p>
      {:else if !res.total}
        <p class="py-8 text-center text-sm" style="color:var(--muted)">No matches for “{query}”.</p>
      {:else}
        <ul class="text-sm">
          {#each res.rows as r, i (i)}
            <li class="flex items-center gap-3 border-b py-2" style="border-color:var(--divider)">
              <span class="shrink-0" style="color:{app.colors[r.g] ?? 'var(--muted)'}">
                <Icon name={app.catIcon[r.g] ?? 'shape-outline'} size={18} />
              </span>
              <div class="min-w-0 flex-1">
                <div class="truncate" style="color:var(--text)">{r.d}</div>
                <div class="text-[12px]" style="color:var(--muted)">{r.g} · {monthLabel(r.m)}</div>
              </div>
              <span class="tnum shrink-0" style="color:{r.t === 1 ? 'var(--ok)' : 'var(--text)'}">
                {r.t === 1 ? '+' : ''}{rm(r.a, true)}
              </span>
            </li>
          {/each}
        </ul>
        {#if res.total > res.rows.length}
          <p class="py-3 text-center text-[12px]" style="color:var(--muted)">
            Showing {res.rows.length} of {res.total}. Refine your search.
          </p>
        {/if}
      {/if}
    </div>
  </div>
{/if}

<script lang="ts">
  import Icon from './Icon.svelte';
  import { app } from '$lib/data';
  import { rm } from '$lib/fmt';

  let { rec }: { rec: any } = $props();

  let open = $state(false);

  const cat = $derived(rec.cat ?? rec.category ?? rec.g ?? 'Other');
  const icon = $derived(app.catIcon[cat] ?? 'shape-outline');
  const name = $derived(rec.merchant ?? rec.name ?? rec.title ?? rec.cat ?? '—');

  // Annual figure for subs/creep/oneoff; monthly for installments/transfers
  const hasAnnual = $derived(rec.rmAnnual != null);
  const headline = $derived(hasAnnual ? rec.rmAnnual : (rec.monthly ?? 0));
  const headlineLabel = $derived(hasAnnual ? '/yr' : '/mo');

  function toggle() { open = !open; }

  function onkeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
  }

  // For installments: build a readable detail line
  const termLine = $derived((() => {
    if (rec.type !== 'installment') return null;
    const parts: string[] = [];
    if (rec.term) parts.push(`${rec.term}-month plan`);
    if (rec.remaining != null) {
      parts.push(rec.est ? `~${rec.remaining} mo remaining (est)` : `${rec.remaining} mo remaining`);
    }
    if (rec.endMonth) parts.push(`ends ${rec.endMonth}`);
    if (rec.remainBal != null) parts.push(`~${rm(rec.remainBal)} left`);
    return parts.length ? parts.join(' · ') : null;
  })());

  // For transfers: total paid so far
  const paidLine = $derived(rec.type === 'transfer' && rec.paidInWindow != null
    ? `${rm(rec.paidInWindow)} paid in window`
    : null);

  // Hint / stale badge for subs
  const hint = $derived(rec.hint ?? null);
  const stale = $derived(rec.stale ?? false);

  // Aggregate evidence by month (for installments/transfers that have multiple rows/month)
  const evidenceByMonth = $derived((() => {
    const ev: any[] = rec.evidence ?? [];
    const map = new Map<string, number>();
    for (const e of ev) {
      const month = e.m ?? e.month ?? '';
      map.set(month, (map.get(month) ?? 0) + (e.a ?? e.amount ?? 0));
    }
    // Return sorted by month desc, limit to 6 most recent
    return [...map.entries()]
      .sort((a, b) => b[0].localeCompare(a[0]))
      .slice(0, 6);
  })());
</script>

<div class="mb-2 overflow-hidden" style="border:1px solid var(--divider)">
  <!-- Header row — full-width button -->
  <button
    class="w-full flex items-center gap-3 px-4 py-3 text-left"
    style="background:var(--surface2)"
    aria-expanded={open}
    onclick={toggle}
    {onkeydown}
  >
    <!-- Category icon -->
    <span class="shrink-0" style="color:{app.colors[cat] ?? 'var(--muted)'}">
      <Icon name={icon} size={18} />
    </span>

    <!-- Name + badges -->
    <span class="flex-1 min-w-0">
      <span class="block font-semibold text-sm truncate" style="color:var(--text)">
        {name}
      </span>
      {#if stale}
        <span class="text-xs" style="color:var(--muted)">Already cancelled?</span>
      {:else if hint}
        <span class="text-xs" style="color:var(--muted)">{hint}</span>
      {/if}
    </span>

    <!-- Headline figure -->
    <span class="shrink-0 font-extrabold text-sm tabular-nums" style="color:var(--accent)">
      {rm(headline)}<span class="font-normal text-xs" style="color:var(--muted)">{headlineLabel}</span>
    </span>

    <!-- Chevron -->
    <span class="shrink-0 transition-transform duration-200" style="color:var(--muted); transform:{open ? 'rotate(180deg)' : 'rotate(0deg)'}">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
        <path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z"/>
      </svg>
    </span>
  </button>

  <!-- Expandable detail -->
  {#if open}
    <div class="px-4 pb-4 pt-2 text-xs space-y-1" style="color:var(--muted); border-top:1px solid var(--divider)">

      <!-- Monthly sub-figure (when headline is annual) -->
      {#if hasAnnual && rec.rmMonthly != null}
        <p class="tabular-nums" style="color:var(--muted)">
          ~{rm(rec.rmMonthly)}/mo
        </p>
      {/if}

      <!-- Installment details -->
      {#if termLine}
        <p>{termLine}</p>
      {/if}

      <!-- Balance transfer paid total -->
      {#if paidLine}
        <p class="tabular-nums">{paidLine}</p>
      {/if}

      <!-- Cat label -->
      <p class="uppercase tracking-wider text-xs" style="color:{app.colors[cat] ?? 'var(--muted)'}">{cat}</p>

      <!-- Evidence: creep shows per-merchant prev→recent breakdown -->
      {#if rec.type === 'creep'}
        {#if rec.evidence && rec.evidence.length > 0}
          <div class="mt-2 space-y-1">
            <p class="uppercase tracking-wider text-xs" style="color:var(--muted)">Merchant breakdown</p>
            {#each rec.evidence as ev}
              <div class="flex justify-between tabular-nums text-xs gap-2" style="color:var(--muted)">
                <span class="truncate">{ev.merchant}</span>
                <span class="shrink-0">{rm(ev.prev)} → {rm(ev.recent)} <span style="color:var(--over)">+{rm(ev.delta)}</span></span>
              </div>
            {/each}
          </div>
        {/if}
      {:else if evidenceByMonth.length > 0}
        <!-- Evidence: aggregated by month for sub/oneoff/installment/transfer -->
        <div class="mt-2 space-y-1">
          <p class="uppercase tracking-wider text-xs" style="color:var(--muted)">Charge history</p>
          {#each evidenceByMonth as [month, total]}
            <div class="flex justify-between tabular-nums text-xs" style="color:var(--muted)">
              <span>{month}</span>
              <span>{rm(total)}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>

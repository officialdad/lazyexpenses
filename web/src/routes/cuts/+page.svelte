<script lang="ts">
  import { app } from '$lib/data';
  import RecCard from '$lib/components/RecCard.svelte';

  // 5 groups in spec order
  const subs = $derived(app.recs.filter((r: any) => r.type === 'sub'));
  const installments = $derived(
    app.installments
      .filter((p: any) => !p.ended)
      .sort((a: any, b: any) => b.monthly - a.monthly)
  );
  const transfers = $derived(app.transfers.filter((t: any) => !t.ended));
  const creep = $derived(app.recs.filter((r: any) => r.type === 'creep'));
  const oneoffs = $derived(app.recs.filter((r: any) => r.type === 'oneoff'));

  type Group = { title: string; items: any[] };
  const groups = $derived<Group[]>([
    { title: 'Subscriptions', items: subs },
    { title: 'Installments', items: installments },
    { title: 'Balance transfers', items: transfers },
    { title: 'Creeping categories', items: creep },
    { title: 'One-offs', items: oneoffs },
  ].filter(g => g.items.length > 0));
</script>

<!-- Page header -->
<p class="text-[11px] uppercase tracking-widest mb-4 font-medium" style="color:var(--muted)">Cuts</p>

{#each groups as g}
  <!-- Group accent header -->
  <h2 class="text-[13px] font-semibold uppercase tracking-widest mt-5 mb-2 first:mt-0" style="color:var(--accent)">
    {g.title}
  </h2>

  {#each g.items as rec (rec.merchant ?? rec.name)}
    <RecCard {rec} />
  {/each}
{/each}

{#if groups.length === 0}
  <p class="text-sm mt-8 text-center" style="color:var(--muted)">No leaks detected.</p>
{/if}

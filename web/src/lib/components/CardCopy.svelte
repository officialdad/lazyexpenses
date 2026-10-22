<script lang="ts">
  import Icon from '$lib/components/Icon.svelte';
  import { app } from '$lib/data';
  import { prettyCard } from '$lib/cardpick';
  import { copyToClipboard } from '$lib/cardnum';
  import { toast } from '$lib/toast.svelte';

  let { card, size = 15 }: { card: string; size?: number } = $props();

  // Only cards whose statement printed the number unmasked have an entry; a masked card
  // (SC's `5520-40XX-XXXX-XXXX`) has none, and then this renders nothing at all.
  const num = $derived(app.cardNumbers[card] ?? '');

  async function copy() {
    if (!num) return;
    const ok = await copyToClipboard(num);
    toast(ok ? 'Card number copied' : 'Could not copy', ok ? 'info' : 'error');
  }
</script>

{#if num}
  <button
    type="button"
    class="cardcopy"
    onclick={copy}
    aria-label="Copy full card number for {prettyCard(card)}"
    title="Copy full card number"
  >
    <Icon name="content-copy" size={size} />
  </button>
{/if}

<style>
  .cardcopy {
    display: inline-flex;
    align-items: center;
    padding: 2px;
    border: 0;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
  }
  .cardcopy:hover {
    color: var(--text);
  }
  .cardcopy:focus-visible {
    outline: 2px solid var(--text);
    outline-offset: 2px;
  }
</style>

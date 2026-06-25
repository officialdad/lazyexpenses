<script lang="ts">
  import OverviewView from '$lib/components/views/OverviewView.svelte';
  import TrendsView from '$lib/components/views/TrendsView.svelte';
  import CutsView from '$lib/components/views/CutsView.svelte';
  import FeesView from '$lib/components/views/FeesView.svelte';
</script>

<div class="max-w-7xl mx-auto px-6 py-8 space-y-12">
  <section id="overview" style="scroll-margin-top:4rem"><OverviewView /></section>
  <section id="trends" style="scroll-margin-top:4rem"><TrendsView /></section>
  <section id="cuts" style="scroll-margin-top:4rem"><CutsView /></section>
  <section id="fees" style="scroll-margin-top:4rem"><FeesView /></section>
</div>

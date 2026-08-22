<script lang="ts">
  // First-run setup and Settings (#40) — the same four steps either way, because they
  // are the same four questions. `first` only changes the framing: on an empty volume
  // this IS the app, afterwards it is a page you came back to.
  //
  // Deliberately no <Icon>: icons ship inside app.json, which does not exist yet on the
  // volume this screen exists for. Numbers render everywhere.
  import { onMount } from 'svelte';
  import { loadAppData } from '$lib/data';
  import { push, togglePush } from '$lib/push.svelte';
  import {
    cfg, isLocked, loadSettings, saveSettings, testMail, testReminder, upload, reconLine
  } from '$lib/setup.svelte';

  let { first = false }: { first?: boolean } = $props();

  onMount(() => { loadSettings(); });

  const APP_PW_URL = 'https://myaccount.google.com/apppasswords';
  const pretty = (b: string) => (b === 'sc' ? 'Standard Chartered' : b.toUpperCase());
  const say = (ok: boolean, m: string) => ({ ok, m });

  // ---------------------------------------------------------------- 1. upload
  let bank = $state('');
  let files = $state<FileList | null>(null);
  let busy = $state(false);
  let uploaded = $state<{ ok: boolean; m: string } | null>(null);
  // The file that came back locked, kept so "Save and retry" can re-post the same bytes
  // instead of asking for it again. save_pdf names by content hash, so a retry is a
  // reparse of one file and not a second statement.
  let retry = $state<{ bank: string; file: File } | null>(null);
  let done = $state(0);

  async function send(e: SubmitEvent) {
    e.preventDefault();
    const file = files?.[0];
    if (!bank || !file) return;
    busy = true;
    uploaded = null;
    const res = await upload(bank, file);
    busy = false;
    if (!res.ok || !res.result) {
      uploaded = say(false, res.error ?? 'Upload failed');
      return;
    }
    const r = res.result;
    uploaded = say(!r.locked && !r.warning, reconLine(r));
    retry = r.locked ? { bank: r.bank, file } : null;
    if (!r.locked) {
      done += 1;
      files = null;
      await loadAppData();      // an empty volume becomes a dashboard right here
    }
  }

  // ---------------------------------------------------------------- 2. passwords
  let pw = $state<Record<string, string>>({});
  let pwSaved = $state('');

  async function savePw(b: string, thenRetry = false) {
    const key = `CC_PW_${b.toUpperCase()}`;
    pwSaved = '';
    busy = true;
    const err = await saveSettings({ [key]: pw[b] ?? '' });
    pw[b] = '';
    busy = false;
    if (err) { pwSaved = err; return; }
    pwSaved = `Saved the ${pretty(b)} password.`;
    if (thenRetry && retry) {
      const again = await upload(retry.bank, retry.file);
      if (again.ok && again.result) {
        uploaded = say(!again.result.locked && !again.result.warning, reconLine(again.result));
        if (!again.result.locked) { retry = null; done += 1; await loadAppData(); }
      }
    }
  }

  // ---------------------------------------------------------------- 3. mail
  let gmailUser = $state('');
  let gmailPw = $state('');
  let gmailLabel = $state('');
  let mailMsg = $state<{ ok: boolean; m: string } | null>(null);
  // Fill the non-secret fields once the server has answered. The secret stays blank on
  // purpose — there is nothing to prefill it with, and that is the contract (#40).
  $effect(() => {
    if (cfg.loaded && !gmailUser) gmailUser = cfg.values.GMAIL_USER ?? '';
    if (cfg.loaded && !gmailLabel) gmailLabel = cfg.values.GMAIL_LABEL ?? '';
  });

  async function saveMail(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    mailMsg = null;
    const patch: Record<string, string> = { GMAIL_USER: gmailUser, GMAIL_LABEL: gmailLabel };
    if (gmailPw) patch.GMAIL_APP_PASSWORD = gmailPw;   // blank = leave it alone
    const err = await saveSettings(patch);
    gmailPw = '';
    mailMsg = err ? say(false, err) : await testMail().then((r) => say(r.ok, r.message));
    busy = false;
  }

  // ---------------------------------------------------------------- 4. reminders
  let tgToken = $state('');
  let tgChat = $state('');
  let remindMsg = $state<{ ok: boolean; m: string } | null>(null);
  $effect(() => {
    if (cfg.loaded && !tgChat) tgChat = cfg.values.TELEGRAM_CHAT_ID ?? '';
  });

  async function saveTelegram(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    remindMsg = null;
    const patch: Record<string, string> = { TELEGRAM_CHAT_ID: tgChat };
    if (tgToken) patch.TELEGRAM_BOT_TOKEN = tgToken;
    const err = await saveSettings(patch);
    tgToken = '';
    busy = false;
    remindMsg = err ? say(false, err) : say(true, 'Saved.');
  }

  async function sendTest() {
    busy = true;
    remindMsg = null;
    const r = await testReminder();
    busy = false;
    remindMsg = say(r.ok, r.message);
  }

  const FIELD = 'w-full border px-2 py-1.5 text-sm';
  const FIELD_STYLE = 'background:var(--surface2);color:var(--text);border-color:var(--divider2)';
  const BTN = 'border px-3 py-1.5 text-xs font-bold uppercase tracking-wide';
  const BTN_STYLE = 'background:var(--surface2);color:var(--text);border-color:var(--divider2)';
</script>

{#snippet lock(name: string)}
  {#if isLocked(name)}
    <span class="text-[11px] uppercase tracking-wide" style="color:var(--accent)"
      >Locked — set by the environment</span
    >
  {/if}
{/snippet}

{#snippet result(r: { ok: boolean; m: string } | null)}
  {#if r}
    <p class="mt-2 text-xs" style="color:{r.ok ? 'var(--ok)' : '#f87171'}" role="status">{r.m}</p>
  {/if}
{/snippet}

<main class="mx-auto max-w-xl px-4 py-8">
  <header class="mb-6">
    <h1 class="text-lg font-extrabold tracking-tight">
      {first ? 'Nothing here yet' : 'Settings'}
    </h1>
    <p class="mt-1 text-sm" style="color:var(--muted)">
      {first
        ? 'Upload one credit-card statement and this becomes a dashboard. Everything below that is optional and can wait.'
        : 'Anything set in the environment wins and cannot be edited here.'}
    </p>
  </header>

  <!-- 1 ---------------------------------------------------------------- -->
  <section class="mb-5 border p-4" style="border-color:var(--divider)" aria-labelledby="s1">
    <h2 id="s1" class="text-xs uppercase tracking-widest" style="color:var(--muted)">
      1 · Add a statement
    </h2>
    <form class="mt-3 flex flex-col gap-3" onsubmit={send}>
      <div>
        <label class="mb-1 block text-xs" for="setup-bank" style="color:var(--muted)"
          >Which bank sent it?</label
        >
        <!-- No default, ever. `bank` is permanent: it picks the PDF password and the
             parser branch, and parse.py re-derives it from the stored filename on every
             later run. A wrong-but-valid guess misparses forever (#31). -->
        <select id="setup-bank" bind:value={bank} required class={FIELD} style={FIELD_STYLE}>
          <option value="" disabled>Choose a bank…</option>
          {#each cfg.banks as b (b)}<option value={b}>{pretty(b)}</option>{/each}
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs" for="setup-file" style="color:var(--muted)"
          >The PDF, straight out of the email</label
        >
        <input
          id="setup-file"
          type="file"
          accept="application/pdf,.pdf"
          bind:files
          required
          class={FIELD}
          style={FIELD_STYLE}
        />
      </div>
      <div class="flex items-center gap-3">
        <button type="submit" disabled={busy || !bank || !files?.length} class={BTN} style={BTN_STYLE}>
          {busy ? 'Reading…' : 'Upload'}
        </button>
        <span class="text-[11px]" style="color:var(--muted)">
          It stays on your volume — nothing is sent anywhere else.
        </span>
      </div>
    </form>
    {@render result(uploaded)}
    {#if done > 0}
      <p class="mt-2 text-xs" style="color:var(--muted)">
        {done} uploaded this session. <a href="/" class="underline">Go to the dashboard</a> — or add
        another above.
      </p>
    {/if}
  </section>

  <!-- 2 ---------------------------------------------------------------- -->
  <!-- Only ever asked when a real file came back locked, or from Settings where you
       came looking for it. An unprompted grid of six password boxes is the terminal
       experience this issue exists to delete. -->
  {#if retry || !first}
    <section class="mb-5 border p-4" style="border-color:var(--divider)" aria-labelledby="s2">
      <h2 id="s2" class="text-xs uppercase tracking-widest" style="color:var(--muted)">
        2 · Statement passwords
      </h2>
      {#if retry}
        <p class="mt-2 text-sm">
          That {pretty(retry.bank)} statement is password-protected. The covering email says what the
          password is — usually your IC or date of birth.
        </p>
        <div class="mt-3 flex flex-col gap-2">
          <label class="text-xs" for="pw-retry" style="color:var(--muted)"
            >{pretty(retry.bank)} PDF password</label
          >
          <input
            id="pw-retry"
            type="password"
            autocomplete="off"
            bind:value={pw[retry.bank]}
            class={FIELD}
            style={FIELD_STYLE}
          />
          <div>
            <button
              type="button"
              disabled={busy || !pw[retry.bank]}
              class={BTN}
              style={BTN_STYLE}
              onclick={() => savePw(retry!.bank, true)}>Save and retry</button
            >
          </div>
        </div>
      {:else}
        <p class="mt-2 text-xs" style="color:var(--muted)">
          Stored once per bank and reused for every statement it sends. Leave a box empty to keep
          what is already there.
        </p>
        <div class="mt-3 flex flex-col gap-3">
          {#each cfg.banks as b (b)}
            {@const key = `CC_PW_${b.toUpperCase()}`}
            <div class="flex items-end gap-2">
              <div class="flex-1">
                <label class="mb-1 block text-xs" for={'pw-' + b} style="color:var(--muted)">
                  {pretty(b)}
                  {#if cfg.secrets[key]}<span style="color:var(--ok)">· set</span>{:else}<span
                      >· not set</span
                    >{/if}
                  {@render lock(key)}
                </label>
                <input
                  id={'pw-' + b}
                  type="password"
                  autocomplete="off"
                  disabled={isLocked(key)}
                  bind:value={pw[b]}
                  class={FIELD}
                  style={FIELD_STYLE}
                />
              </div>
              <button
                type="button"
                disabled={busy || isLocked(key) || !pw[b]}
                class={BTN}
                style={BTN_STYLE}
                onclick={() => savePw(b)}>Save</button
              >
            </div>
          {/each}
        </div>
      {/if}
      {#if pwSaved}<p class="mt-2 text-xs" style="color:var(--muted)" role="status">{pwSaved}</p>{/if}
    </section>
  {/if}

  <!-- 3 ---------------------------------------------------------------- -->
  <section class="mb-5 border p-4" style="border-color:var(--divider)" aria-labelledby="s3">
    <h2 id="s3" class="text-xs uppercase tracking-widest" style="color:var(--muted)">
      3 · Fetch statements from Gmail <span style="color:var(--divider2)">(optional)</span>
    </h2>
    <p class="mt-2 text-xs" style="color:var(--muted)">
      Label the statement mail <code>CC</code> in Gmail and this checks for new ones every hour, so
      you never upload another by hand. Needs an app password, not your Google password —
      <a href={APP_PW_URL} target="_blank" rel="noreferrer" class="underline">make one here</a>.
    </p>
    <form class="mt-3 flex flex-col gap-3" onsubmit={saveMail}>
      <div>
        <label class="mb-1 block text-xs" for="gmail-user" style="color:var(--muted)"
          >Gmail address {@render lock('GMAIL_USER')}</label
        >
        <input
          id="gmail-user"
          type="email"
          autocomplete="username"
          disabled={isLocked('GMAIL_USER')}
          bind:value={gmailUser}
          class={FIELD}
          style={FIELD_STYLE}
        />
      </div>
      <div>
        <label class="mb-1 block text-xs" for="gmail-pw" style="color:var(--muted)">
          App password
          {#if cfg.secrets.GMAIL_APP_PASSWORD}<span style="color:var(--ok)">· set</span>{/if}
          {@render lock('GMAIL_APP_PASSWORD')}
        </label>
        <input
          id="gmail-pw"
          type="password"
          autocomplete="off"
          placeholder={cfg.secrets.GMAIL_APP_PASSWORD ? 'unchanged' : ''}
          disabled={isLocked('GMAIL_APP_PASSWORD')}
          bind:value={gmailPw}
          class={FIELD}
          style={FIELD_STYLE}
        />
      </div>
      <div>
        <label class="mb-1 block text-xs" for="gmail-label" style="color:var(--muted)"
          >Label {@render lock('GMAIL_LABEL')}</label
        >
        <input
          id="gmail-label"
          type="text"
          placeholder="CC"
          disabled={isLocked('GMAIL_LABEL')}
          bind:value={gmailLabel}
          class={FIELD}
          style={FIELD_STYLE}
        />
      </div>
      <div>
        <button type="submit" disabled={busy} class={BTN} style={BTN_STYLE}>
          {busy ? 'Connecting…' : 'Save and test connection'}
        </button>
      </div>
    </form>
    {@render result(mailMsg)}
  </section>

  <!-- 4 ---------------------------------------------------------------- -->
  <section class="mb-5 border p-4" style="border-color:var(--divider)" aria-labelledby="s4">
    <h2 id="s4" class="text-xs uppercase tracking-widest" style="color:var(--muted)">
      4 · Bill reminders <span style="color:var(--divider2)">(optional)</span>
    </h2>
    <p class="mt-2 text-xs" style="color:var(--muted)">
      One notification per bill, a few days before it is due.
    </p>

    <div class="mt-3 flex items-center gap-3">
      {#if push.status === 'off' || push.status === 'on' || push.status === 'busy'}
        <button
          type="button"
          class={BTN}
          style={BTN_STYLE}
          aria-pressed={push.status === 'on'}
          disabled={push.status === 'busy'}
          onclick={() => togglePush()}
        >
          {push.status === 'busy'
            ? '…'
            : push.status === 'on'
              ? 'Notifications on'
              : 'Turn on notifications'}
        </button>
      {/if}
      <span class="text-[11px]" style="color:var(--muted)">
        {push.note || 'Nothing to configure — your browser handles it.'}
      </span>
    </div>

    <details class="mt-4">
      <summary class="cursor-pointer text-xs" style="color:var(--muted)">
        Use Telegram instead (or as well)
      </summary>
      <form class="mt-3 flex flex-col gap-3" onsubmit={saveTelegram}>
        <div>
          <label class="mb-1 block text-xs" for="tg-token" style="color:var(--muted)">
            Bot token
            {#if cfg.secrets.TELEGRAM_BOT_TOKEN}<span style="color:var(--ok)">· set</span>{/if}
            {@render lock('TELEGRAM_BOT_TOKEN')}
          </label>
          <input
            id="tg-token"
            type="password"
            autocomplete="off"
            placeholder={cfg.secrets.TELEGRAM_BOT_TOKEN ? 'unchanged' : ''}
            disabled={isLocked('TELEGRAM_BOT_TOKEN')}
            bind:value={tgToken}
            class={FIELD}
            style={FIELD_STYLE}
          />
        </div>
        <div>
          <label class="mb-1 block text-xs" for="tg-chat" style="color:var(--muted)"
            >Chat ID {@render lock('TELEGRAM_CHAT_ID')}</label
          >
          <input
            id="tg-chat"
            type="text"
            disabled={isLocked('TELEGRAM_CHAT_ID')}
            bind:value={tgChat}
            class={FIELD}
            style={FIELD_STYLE}
          />
        </div>
        <p class="text-[11px]" style="color:var(--muted)">
          Message the bot once from that chat first — Telegram will not let a bot speak first.
        </p>
        <div><button type="submit" disabled={busy} class={BTN} style={BTN_STYLE}>Save</button></div>
      </form>
    </details>

    <div class="mt-4">
      <button type="button" disabled={busy} class={BTN} style={BTN_STYLE} onclick={sendTest}
        >Send test message</button
      >
    </div>
    {@render result(remindMsg)}
  </section>

  {#if first}
    <p class="text-xs" style="color:var(--muted)">
      Steps 2 to 4 are all optional and all live at
      <a href="/settings" class="underline">Settings</a> afterwards.
    </p>
  {:else}
    <p class="text-xs"><a href="/" class="underline">Back to the dashboard</a></p>
  {/if}
</main>

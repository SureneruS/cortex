<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import { Terminal } from "@xterm/xterm";
  import { FitAddon } from "@xterm/addon-fit";
  import { WebLinksAddon } from "@xterm/addon-web-links";
  import "@xterm/xterm/css/xterm.css";

  let terminalEl: HTMLDivElement;
  let term: Terminal;
  let fitAddon: FitAddon;
  let unlisten: (() => void) | null = null;

  onMount(async () => {
    term = new Terminal({
      fontFamily: "'JetBrains Mono', 'Menlo', monospace",
      fontSize: 14,
      lineHeight: 1.2,
      cursorBlink: true,
      cursorStyle: "block",
      scrollback: 10000,
      theme: {
        background: "#0c1117",
        foreground: "#c9d1d9",
        cursor: "#58a6ff",
        selectionBackground: "#c9d1d933",
        selectionForeground: "#c9d1d9",
        black: "#484f58",
        red: "#ec8e2b",
        green: "#58a6ff",
        yellow: "#d29921",
        blue: "#58a6ff",
        magenta: "#bc8cff",
        cyan: "#39c5cf",
        white: "#b1bac4",
        brightBlack: "#6e7681",
        brightRed: "#fdac53",
        brightGreen: "#79c0ff",
        brightYellow: "#e3b341",
        brightBlue: "#79c0ff",
        brightMagenta: "#d2a8ff",
        brightCyan: "#55d4dd",
        brightWhite: "#ffffff",
      },
    });

    fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.loadAddon(new WebLinksAddon());
    term.open(terminalEl);
    fitAddon.fit();

    await invoke("spawn_shell", {
      cols: term.cols,
      rows: term.rows,
    });

    unlisten = await listen<string>("pty-output", (event) => {
      term.write(event.payload);
    });

    term.onData((data: string) => {
      invoke("write_to_pty", { data });
    });

    term.onResize(({ cols, rows }: { cols: number; rows: number }) => {
      invoke("resize_pty", { cols, rows });
    });

    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit();
    });
    resizeObserver.observe(terminalEl);
  });

  onDestroy(() => {
    if (unlisten) unlisten();
    term?.dispose();
  });
</script>

<div class="terminal-container" bind:this={terminalEl}></div>

<style>
  .terminal-container {
    flex: 1;
    width: 100%;
    height: 100%;
  }

  .terminal-container :global(.xterm) {
    padding: 8px;
    height: 100%;
  }

  .terminal-container :global(.xterm-viewport) {
    overflow-y: auto !important;
  }

  .terminal-container :global(.xterm-viewport::-webkit-scrollbar) {
    width: 12px;
  }

  .terminal-container :global(.xterm-viewport::-webkit-scrollbar-track) {
    background: transparent;
  }

  .terminal-container :global(.xterm-viewport::-webkit-scrollbar-thumb) {
    background: rgba(255, 255, 255, 0.15);
    border-radius: 4px;
  }

  .terminal-container :global(.xterm-viewport::-webkit-scrollbar-thumb:hover) {
    background: rgba(255, 255, 255, 0.3);
  }
</style>

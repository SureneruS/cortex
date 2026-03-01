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
      fontSize: 13,
      lineHeight: 1.3,
      cursorBlink: true,
      cursorStyle: "block",
      theme: {
        background: "#1a1b26",
        foreground: "#a9b1d6",
        cursor: "#7aa2f7",
        selectionBackground: "#33467c",
        black: "#15161e",
        red: "#f7768e",
        green: "#9ece6a",
        yellow: "#e0af68",
        blue: "#7aa2f7",
        magenta: "#bb9af7",
        cyan: "#7dcfff",
        white: "#a9b1d6",
        brightBlack: "#414868",
        brightRed: "#f7768e",
        brightGreen: "#9ece6a",
        brightYellow: "#e0af68",
        brightBlue: "#7aa2f7",
        brightMagenta: "#bb9af7",
        brightCyan: "#7dcfff",
        brightWhite: "#c0caf5",
      },
    });

    fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.loadAddon(new WebLinksAddon());
    term.open(terminalEl);
    fitAddon.fit();

    // Spawn PTY via Tauri backend
    await invoke("spawn_shell", {
      cols: term.cols,
      rows: term.rows,
    });

    // Listen for PTY output from Tauri backend
    unlisten = await listen<string>("pty-output", (event) => {
      term.write(event.payload);
    });

    // Send user input to PTY
    term.onData((data: string) => {
      invoke("write_to_pty", { data });
    });

    // Handle resize
    term.onResize(({ cols, rows }: { cols: number; rows: number }) => {
      invoke("resize_pty", { cols, rows });
    });

    // Fit on window resize
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
</style>

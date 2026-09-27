---
name: serial-mcp
description: Drive real hardware over a serial line with this Serial MCP server -- type at a vintage console (CP/M, UCSD Pascal, a monitor ROM), send control bytes, pace writes to a UART with no flow control, watch through the mirror, and move files without typing them. Use this whenever a task talks to a device through the `serial.*` or `paced.*` tools (shown in some clients as `serial_open`, `paced_write`, `mcp__serial__...`), and especially for old machines that drop characters.
---

# Driving real hardware over serial

This server gives you a live serial line. On a modern device that is easy. On an old
machine it is not: many have a one-byte UART receive register and no flow control. They
were built for a human typing, not for a program. Most failures here are lost
characters, and they look like bugs somewhere else.

Tool names below are the server's own (`serial.open`, `paced.write`). Your client may
show them as `serial_open` or `mcp__serial__serial_open`.

For measured gaps and delays per machine, see `references/device-profiles.md`.

## 1. Send bytes, not escapes

- **`data` is literal.** `\r`, `\n` and `\x03` in a `data` string go out as a backslash
  and letters, never as control bytes. This is true for every tool and every option,
  including `newline` and `append_newline`.
- **Send control bytes as hex.** Use `as: "hex"`: `0d` is CR, `1b` is ESC, `03` is ^C,
  `1a` is ^Z.
- **Encode a command line with a command, not by hand.** Run
  `printf 'DIR\r' | xxd -p` and pass the output with `as: "hex"`. Hand-typed hex drops
  bytes.
- **Never put a large payload in `data`.** A long string is regenerated, not copied, and
  it drifts. To send a file, close the port with `serial.close`, stream the file from
  disk with a short pyserial script, then open the port again. Better still, move files
  over a network path if the machine has one.
- **When in doubt, read back with `as: "hex"`.** Text output can hide a stray byte.

## 2. Pace every connection

- **Pacing belongs to the connection.** Each `serial.open` gives a new connection with
  0 ms gaps. Call `paced.configure` right after every open.
- **Use `paced.write` for anything typed.** A 38-byte command sent with no gaps dropped a
  digit on a 9600-baud console.
- **`inter_char_gap_ms` paces every byte.** Its safe value depends on the machine and on
  the program that reads the input. A screen editor that redraws on each key needs far
  more than a command line.
- **`eol_gap_ms` is for block text inside a program.** Use it when you type lines into a
  program that does work after each line: BASIC program entry, an editor's insert mode,
  `PIP` from `CON:`. Its value differs per program. Do not use it to pace commands to a
  command processor. For those, see section 3.

## 3. One command at a time on an old console

- **Send one command. Wait until you see the prompt. Then send the next.** Do not send
  several command lines at once. While the machine prints a command's output, it does
  not read the UART. Bytes that arrive then overwrite each other in the one-byte
  register. No gap value fixes this. Seen as `SSSTAT` after a burst of `STAT` commands.
- **After a disk write, the prompt comes before the machine is ready.** Many BIOSes keep
  a disk write in a buffer and write it out on the next console read. So after `ERA`,
  `REN`, `SAVE` or a file transfer, the prompt appears, and then the BIOS writes the
  buffer. It does not read the UART while it writes. Wait for the write to finish before
  you type. Seen as `EE` or `DD` in place of the next command.
- **End a command with a bare CR.** Do not send CR+LF. On some CP/M consoles the LF
  arrives as a keystroke and stops a long listing after its first line.
- **Avoid interactive prompts in a sequence.** A `(Y/N)` question eats the next command.
  Use a temporary file name, then rename it.
- **Recover a confused screen.** Wait until the output stops. Then send ESC, then CR, as
  hex.

## 4. Read carefully

- **`serial.read_until` stops at the delimiter.** Anything after it stays in the buffer
  for the next read. Read again to drain it.
- **A delimiter must be unique.** A prompt that appears several times, such as `A>`
  during a batch job, stops the read too early.
- **`serial.read` returns everything since the last read**, from any source.
- **Do not trust a strange result.** A short or odd reply can come from the tool path,
  not the device. Check it with a direct pyserial script, or ask the user to look at the
  machine. Do this before you decide that the hardware or its disk is at fault.

## 5. The mirror

`serial.open` returns mirror details: a PTY path such as `/tmp/serial-mcp0`, or a TCP
port such as `127.0.0.1:2424`. A person can watch with `nc 127.0.0.1 2424` or a terminal
on the PTY.

- **Use `SERIAL_MCP_MIRROR=ro` when the agent drives.** In `rw` mode, anything the
  watcher's terminal sends goes straight to the device, mixed into your commands. This
  caused garbled `DIR` output before it was found.
- **In `rw` mode, bracket a multi-call sequence** with `paced.exclusive_begin` and
  `paced.exclusive_end`. The pause always expires, so a failed sequence cannot lock out
  the human.

## 6. Tune a gap by measurement

- **Calibrate only where every typed character echoes**, such as an editor's insert
  mode. At a menu, keys are commands, not echo, and `paced.calibrate` reports nonsense.
- **Start near a value that already works.** Do not sweep up from 0. On one console, gaps
  in the middle of the range were worse than low gaps: they set off a screen-redraw loop.
- **Find the break point.** When a gap fails, bisect between the failing value and a
  working one. Try each value near the edge at least twice. Record every value and its
  result. A sharp edge shows a fixed cost per key. A fuzzy edge shows a race.

## 7. Real hardware has only the console

- **You get only what a person at a terminal gets.** There is no memory access, snapshot
  or single-step. Any method must work with a plain terminal and the machine's own tools.
- **Prove a method on an emulator first**, if one exists, before you use it on the real
  machine.
- **Keep long test runs out of the main conversation.** Hand a long battery to a
  subagent that holds the port and reports a summary. Only one owner can hold a port.

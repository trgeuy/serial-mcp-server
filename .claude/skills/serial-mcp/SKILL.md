---
name: serial-mcp
description: Drive real hardware over a serial line with this Serial MCP server -- type at a vintage console (CP/M, BASIC, UCSD Pascal, a monitor ROM, any machine with a serial terminal port), send control bytes, pace writes to a UART with no flow control, watch through the mirror, and move files without typing them. Use this whenever a task talks to a device through the `serial.*` or `paced.*` tools (shown in some clients as `serial_open`, `paced_write`, `mcp__serial__...`), when you bring up a machine or a program that nobody has measured yet, and especially for old machines that drop characters.
---

# Driving real hardware over serial

This server gives you a live serial line. On a modern device that is easy. On an old
machine it is not: many have a one-byte UART receive register and no flow control. They
were built for a human typing, not for a program. Most failures here are lost
characters, and they look like bugs somewhere else.

The rules below apply to any machine with a serial console. Each rule shows where it was
seen. Measured values live in a pacing profile file (section 4): yours, kept in one place
for all your projects, and the tested examples in `references/pacing-examples.md`, from an
Altair 8800c with CP/M 2.2 and a CompuPro system with UCSD Pascal III. On other hardware,
use the examples as a starting point and as a model, not as values to copy.

Tool names below are the server's own (`serial.open`, `paced.write`). Your client may
show them as `serial_open` or `mcp__serial__serial_open`.

## 1. Send bytes, not escapes

- **`data` is literal.** `\r`, `\n` and `\x03` in a `data` string go out as a backslash
  and letters, never as control bytes. This is true for every tool and every option,
  including `newline` and `append_newline`.
- **Do not set `newline` on `serial.open`.** A `\r` there becomes a backslash and an `r`,
  and every tool that uses the connection's newline sends that text. Leave it out: the
  default is a real CR+LF. To end a line with a bare CR, put `0d` in hex data.
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

## 2. A new machine or a new program

Do these steps before you type real work into a machine or a program that is not in
your pacing profile file (section 4).

1. **Get the line settings from the user or the manual.** Baud rate, data bits, parity
   and stop bits. Do not guess. A wrong setting gives garbage or nothing.
2. **Open and listen first.** Do a `serial.read`. Then send one CR (`0d`) and read
   again. A prompt tells you the line works and what the prompt looks like.
3. **Find the line ending the program wants.** Most consoles end a line on CR. Some
   want CR+LF, and some treat the LF as a second key. Try a short harmless command with
   CR, and look at the echo and the reply.
4. **Find out if the program echoes.** Calibration needs an echo of each key (section
   6). A menu or a game that reads single keys does not echo.
5. **Start slow.** For a program with no measured values, start at 20 ms per character
   and 300 ms per line. For a screen editor or any program that redraws on each key,
   start at 100 ms per key. On the Altair, a screen editor dropped keys at 30 ms.
6. **Measure down from there** (section 7), and record the result (section 4).

## 3. Pace every connection

- **Each program needs its own pacing.** The gaps depend on the program that reads the
  input, not only on the machine. On the Altair at 9600 baud, the command processor
  uses 5 ms per character, MBASIC program entry 2 ms per character plus 30 ms per
  line, and a screen editor 50 to 100 ms per key. Set new gaps with
  `paced.configure` when you start a different program, and set them back when it ends.
- **Keep a pacing profile for your hardware.** Read it before you type into a program,
  and add a row each time you measure a new program. See section 4.
- **Pacing belongs to the connection.** Each `serial.open` gives a new connection with
  0 ms gaps. Call `paced.configure` right after every open.
- **Use `paced.write` for anything typed.** A 38-byte command sent with no gaps dropped a
  digit on a 9600-baud console.
- **`inter_char_gap_ms` paces every byte.** A program that does work on each key (a
  screen editor that redraws) needs far more than a command line.
- **`eol_gap_ms` is for block text inside a program.** Use it when you type lines into a
  program that does work after each line: BASIC program entry, an editor's insert mode,
  a program that copies the console to a file. A longer line needs a longer gap. Do not
  use it to pace commands to a command processor. For those, see section 5.
- **`eol_gap_ms` comes only after the connection's newline.** With the default CR+LF, a
  line that ends in a bare CR gets no line gap. Type such lines with CR+LF, if the
  program accepts the LF.

## 4. The pacing profile file

Keep every measured value in ONE file for all projects, so that a new project starts with
what you already know:

- macOS and Linux: `~/.config/serial-mcp/pacing-profiles.md`
- Windows: `%APPDATA%\serial-mcp\pacing-profiles.md`

Do not keep it in a project folder or in this skill's folder. A skill update replaces the
skill's folder.

- **Read it first.** Before you type into a program, look for the machine and the program.
  If a row exists, use its gaps.
- **No row: measure, then add one.** Follow section 2. Add the row as soon as you have a
  result, with the date.
- **No file: create it** with the format below. Tell the user where it is.
- **Do not change a measured value without a new measurement.** If a new run disagrees,
  add the new result and keep the old one in the notes. When the program changes (a new
  version), mark its row "measure again".

Format: one `##` section per machine, a short console line, then one table. Put long
results under the table.

```markdown
## <Machine name>

Console: <baud> <format>, <serial board or UART>, <flow control>. OS: <name, version>.
Disk: <controller, drives or emulator, anything that buffers writes>.

| Program / mode | Line end | Char gap ms | Line gap ms | Wait ms | Lowest pass / first fail | Method, runs | Date | Notes |
|---|---|---|---|---|---|---|---|---|
| <program, mode> | CR | <value> | <value or --> | <value or --> | <pass> / <fail> | <tool>, <runs> | YYYY-MM-DD | <short> |
```

- **Char gap ms, Line gap ms:** the values to use, with the 20% headroom (section 7).
- **Wait ms:** a wait the program needs, and when: after the prompt before the next
  command, or after starting the program before the first byte. Most waits come from
  disk access, so they belong to the disk system on the `Disk:` line. Do not reuse them
  on a machine with a different disk system.
- **Lowest pass / first fail:** the measured edge. Later you can check the headroom or
  measure again from it.
- Write `--` for a value that does not apply and `not recorded` for one nobody measured.
  Never fill a cell with a guess.

## 5. One command at a time on an old console

- **Send one command. Wait until you see the prompt. Then send the next.** Do not send
  several command lines at once. While the machine prints a command's output, it does
  not read the UART. Bytes that arrive then overwrite each other in the one-byte
  register. No gap value fixes this. Seen on CP/M as `SSSTAT` after a burst of `STAT`
  commands.
- **A prompt does not always mean the machine is ready.** Some systems print the prompt
  and then do more work. A CP/M BIOS that buffers disk writes writes the buffer out on
  the next console read. So after `ERA`, `REN`, `SAVE` or a file transfer, the prompt
  appears, and then the BIOS writes the buffer. It does not read the UART while it
  writes. Seen as `EE` or `DD` in place of the next command. After a command that
  writes to a disk, wait about 1 s after the prompt.
- **Some programs give no ready sign.** A program that reads text from the console, such
  as CP/M `PIP <file>=CON:`, prints nothing when it is ready. It first loads and creates
  its file, and loses bytes during that time. Wait before the first byte: on the Altair,
  1 s lost the start of line 1, and 1.5 s was clean. Record it as a wait (section 4).
- **Use the line ending the program wants.** The CP/M command processor wants a bare CR.
  On some CP/M consoles an LF arrives as a keystroke and stops a long listing after its
  first line.
- **Avoid interactive prompts in a sequence.** A `(Y/N)` question eats the next command.
  Use a temporary file name, then rename it.
- **Learn how to recover a confused screen.** Wait until the output stops. On the
  machines measured here, ESC and then CR, sent as hex, brought back a prompt. Ask the
  user what works on their machine.

## 6. Read the failure

The kind of damage tells you which gap to change.

| What you see | Probable cause | What to do |
|---|---|---|
| Garbage, or nothing at all | Wrong line settings, port or cable | Check section 2, step 1. Do not change gaps. |
| A letter missing inside a line | `inter_char_gap_ms` too short | Increase it. |
| The start of a line missing, often after a long line | `eol_gap_ms` too short | Increase it. A BASIC line that loses its number runs at once or gives `Syntax error`. |
| Parts of commands joined or doubled (`SSSTAT`) | Sent while the machine was busy | Send one command at a time (section 5). |
| The start of the first line lost, the rest correct | Sent before the program was ready | Wait longer after starting the program (section 5). |
| A stray letter at the start of the next command | Typed during a disk write after the prompt | Wait after the prompt (section 5). |
| Repeated redraws or bells, the machine looks hung | Keys arrive during a slow screen update | Wait until it is quiet, recover the screen, use a longer gap. |
| A result that makes no sense | The tool path, not the device | See section 8. |

## 7. Tune a gap by measurement

- **Calibrate only where every typed character echoes**, such as an editor's insert
  mode or BASIC program entry. At a menu, keys are commands, not echo, and
  `paced.calibrate` reports nonsense.
- **Use real lines as `test_lines`.** Lines from the actual job show the real cost per
  line. Short generated lines can pass where the real lines fail.
- **Check `sent_text` in the result.** `paced.calibrate` ends each test line with the
  connection's newline. If that newline is text such as `\r`, the program echoes the
  text, the line is never entered, and the result says "clean". The `sent_text` must
  end in a real CR or CR+LF.
- **Start near a value that already works.** Do not sweep up from 0. On one console, gaps
  in the middle of the range were worse than low gaps: they set off a screen-redraw loop.
- **Find the break point.** When a gap fails, bisect between the failing value and a
  working one. Try each value near the edge at least twice. Record every value and its
  result. A sharp edge shows a fixed cost per key. A fuzzy edge shows a race.
- **Leave 20% headroom.** Do not set a gap at the limit you observed. Set it at least
  20% above the lowest value that passed: if 15 ms failed and 20 ms passed, use 24 ms
  or more. The edge moves with line length and with what the program does, so
  test the value with the real job.

## 8. Read carefully

- **`serial.read_until` stops at the delimiter.** Anything after it stays in the buffer
  for the next read. Read again to drain it.
- **A delimiter must be unique.** A prompt that appears several times, such as `A>`
  during a batch job, stops the read too early.
- **`serial.read` returns everything since the last read**, from any source.
- **Do not trust a strange result.** A short or odd reply can come from the tool path,
  not the device. Check it with a direct pyserial script, or ask the user to look at the
  machine. Do this before you decide that the hardware or its disk is at fault.

## 9. The mirror

`serial.open` returns mirror details: a PTY path such as `/tmp/serial-mcp0`, or a TCP
port such as `127.0.0.1:2424`. A person watches the TCP mirror with `serial-watch` (installed
with the server; `serial-watch PORT` for another port), or a PTY mirror with a terminal program
such as `screen /tmp/serial-mcp0`.

- **Use `SERIAL_MCP_MIRROR=ro` when the agent drives.** In `rw` mode, anything the
  watcher's terminal sends goes straight to the device, mixed into your commands. This
  caused garbled `DIR` output before it was found.
- **In `rw` mode, bracket a multi-call sequence** with `paced.exclusive_begin` and
  `paced.exclusive_end`. The pause always expires, so a failed sequence cannot lock out
  the human.

## 10. Real hardware has only the console

- **You get only what a person at a terminal gets.** There is no memory access, snapshot
  or single-step. Any method must work with a plain terminal and the machine's own tools.
- **Prove a method on an emulator first**, if one exists, before you use it on the real
  machine.
- **Keep long test runs out of the main conversation.** Hand a long battery to a
  subagent that holds the port and reports a summary. Only one owner can hold a port.

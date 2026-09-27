# Device profiles

Measured values for machines this fork was used with. A value here is true for that
machine and that program only. For a new machine, measure (see SKILL.md, section 6), then
add a profile.

Each value shows what was measured and how.

## Altair 8800c, CP/M 2.2b, 9600 baud 8N1 console

The console is a UART with no flow control. The disks are 8 MB drives on a disk server;
the BIOS source calls it the serial disk server.

| Program | inter_char_gap_ms | eol_gap_ms | Notes |
|---|---|---|---|
| CCP (command line) | 2 to 5 | not needed | 2 ms calibrated with `paced.sweep`. 5 ms also clean over many commands. Wait for the prompt before each command. |
| VIEDIT, single commands | 50 | -- | 5 ms and 30 ms dropped keys. `o` does extra screen work and dropped a key at 30 ms. |
| VIEDIT, repeated scroll keys (`j`, `k`) | 100 | -- | 40 `j` at 50 ms lost 7 to 8 keys, 2 of 2 runs. 100 ms clean, 2 of 2. |

**Break points for a burst of `j` or `k` grow with line width:** about 98 ms (`j`) and
59 ms (`k`) at 9 characters, 260 ms and 100 ms at 40, and 550 ms and 150 ms at 79. The
98 ms edge was sharp: 96 ms failed 2 of 2, and 98 ms passed 2 of 2.

**Delay after a disk write:** the BIOS keeps writes in a track buffer. Its console-input
routine (`conIn`) writes the buffer out before it reads a key. After `ERA`, `REN`, `SAVE`
or a file transfer, wait about 1 s after the prompt before you type. With the wait, 3 of 3
commands were clean. Without it, the next command came back as `EE` or `DD`.

**Command bursts:** five `STAT` commands sent at once always left a stray `SS` fragment.
Every `eol_gap_ms` from 0 to 1000 ms gave the same result. Send one command at a time.

**Line ending:** bare CR. The CCP needs no LF.

## UCSD Pascal III, CompuPro Interfacer (AMI S1602P UART), 9600 baud

| Program | inter_char_gap_ms | eol_gap_ms | Notes |
|---|---|---|---|
| Editor, insert mode | 15 | 50 | Byte-exact echo with `paced.calibrate`. |

- 0 ms lost about 80% of the bytes. 1 to 4 ms lost some.
- 6 to 12 ms set off a screen-redraw and bell loop. `paced.calibrate` reported large
  "substituted" counts, and the machine looked hung. It was not. Wait for it to go quiet,
  then send ESC, then CR, as hex.
- Calibrate in insert mode only. At the editor's command menu, keys are commands and do
  not echo.

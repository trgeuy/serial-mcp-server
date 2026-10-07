# Pacing examples

Tested values from the machines this fork was used with, in the pacing-profile format
(SKILL.md, section 4). A value here is true for that machine and that program only. On
other hardware, use these as a starting point and as a model for your own profile file.
Do not copy them into your file as if you had measured them.

## Altair 8800c

Console: 9600 baud 8N1, 88-2SIO port A, no flow control. OS: CP/M 2.2b. Line end for
commands: bare CR.
Disk: FDC+ controller, 8 MB drives on an ESP32 disk server over a fast serial link; the BIOS
buffers a track and writes it on the next console read.

| Program / mode | Line end | Char gap ms | Line gap ms | Wait ms | Lowest pass / first fail | Method, runs | Date | Notes |
|---|---|---|---|---|---|---|---|---|
| CCP, command line | CR | 5 | -- | 1000 after a disk write | char 2 / not recorded | `paced.sweep`; 5 ms clean over many commands | not recorded | One command at a time. An LF can stop a long listing. |
| MBASIC 5.21, program entry | CR+LF | 2 | 30 | -- | char 1 / 0; line 20 / 15 (after a 72-char line) | `paced.sweep`, 2 to 4 runs each | 2026-10-06 | Longer lines need a longer line gap. |
| CP/M `PIP <file>=CON:`, typed text | CR+LF | 2 | 0 | 2000 before the first byte | per byte ~2.3 / 1.04 (real interval); start 1500 / 1000 | pyserial script, 2 to 3 runs; LOAD result checked byte for byte | 2026-10-06 | PIP gives no ready sign. No chunks needed for a 6 KB file. End with ^Z. |
| VIEDIT, single commands | -- | 50 | -- | -- | 50 / 30 | real-hardware battery | 2026-09-15 | VIEDIT has changed since. Measure again. |
| VIEDIT, repeated `j`/`k` | -- | 100 | -- | -- | `j` 98 / 96 (9-char lines) | real-hardware battery, 2 runs each | 2026-09-15 | Edge grows with line width. VIEDIT has changed since. |

**CCP, disk-write wait:** the BIOS keeps writes in a track buffer. Its console-input
routine writes the buffer out before it reads a key. After `ERA`, `REN`, `SAVE` or a file
transfer, the prompt appears before the write ends. With a 1 s wait, 3 of 3 commands were
clean. Without it, the next command came back as `EE` or `DD`.

**CCP, command bursts:** five `STAT` commands sent at once always left a stray `SS`
fragment. Every line gap from 0 to 1000 ms gave the same result. No gap fixes this.

**MBASIC:** at 0 ms per character, 1 byte of 89 was lost, 4 of 4 runs. With a 2 ms
character gap, a line gap of 14 ms or less lost the start of the next line, 8 of 8 runs.
The line lost its number, so MBASIC ran it at once or gave `Syntax error`. 15 ms was clean
after a 28-character line, but failed 2 of 2 after a 72-character line. MBASIC ends a line
on the CR and ignores the LF.

**VIEDIT `j`/`k` break points by line width:** `j` about 98, 260 and 550 ms at 9, 40 and
79 characters; `k` about 59, 100 and 150 ms. The 98 ms edge was sharp: 96 ms failed 2 of
2, and 98 ms passed 2 of 2.

## CompuPro system with UCSD Pascal III

Console: 9600 baud, CompuPro Interfacer 1 (AMI S1602P UART), no flow control. OS: UCSD
Pascal III.
Disk: CompuPro Disk 1 controller with a floppy emulator (Gotek-like), real floppy timing.

| Program / mode | Line end | Char gap ms | Line gap ms | Wait ms | Lowest pass / first fail | Method, runs | Date | Notes |
|---|---|---|---|---|---|---|---|---|
| Editor, insert mode | not recorded | 15 | 50 | -- | 15 / 12 | `paced.calibrate`, `paced.sweep` | 2026-08-11 | 6 to 12 ms start a redraw loop. |

**Editor:** 0 ms lost about 80% of the bytes; 1 to 4 ms lost some. 6 to 12 ms set off a
screen-redraw and bell loop. `paced.calibrate` reported large "substituted" counts, and
the machine looked hung. It was not. Wait for it to go quiet, then send ESC, then CR, as
hex. Calibrate in insert mode only. At the editor's command menu, keys do not echo.

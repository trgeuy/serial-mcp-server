---
kind: serial-protocol
name: DemoDevice Protocol
device_name_contains: DemoDevice
connection:
  baudrate: 115200
  bytesize: 8
  parity: "N"
  stopbits: 1
  newline: "\r\n"
---

# DemoDevice Protocol

This is a simulated serial device for testing the Serial MCP server.

## Connection

- **Baud rate:** 115200
- **Data bits:** 8
- **Parity:** None
- **Stop bits:** 1
- **Line terminator:** `\r\n`

## Line protocol

- Commands are single-line, terminated with `\r\n`.
- Responses are one or more lines, each terminated with `\r\n`.
- After every response, the device prints the prompt `> ` (greater-than followed by a space).
- The prompt indicates the device is ready for the next command.
- Prefixed lines (`[LOG]`, `[SAMPLE]`, `[BOOT]`) are asynchronous output. They can appear between the prompt and the next command.

## Boot sequence

On power-up (or after `reboot` / `factory-reset`), the device prints:

```
[BOOT] DemoDevice v1.0.0
[BOOT] Ready.
>
```

---

## Commands

### help

List all available commands.

```
> help
Available commands:
  help                 Show this help message
  version              Show firmware version
  ...
>
```

### version

Print firmware version string.

```
> version
DemoDevice v1.0.0
>
```

### uptime

Print device uptime in seconds.

```
> uptime
1234s
>
```

### ping

Simple connectivity test.

```
> ping
pong
>
```

### echo \<text\>

Echo text back exactly. Use this to test write and readline.

```
> echo Hello world
Hello world
>
```

### status

Print device status as a single JSON line.

```
> status
{"state":"idle","temp":42.3,"uptime":1234,"logs_enabled":false,"authenticated":false}
>
```

Fields:
- `state`: `"idle"`, `"logging"`, or `"sampling"`
- `temp`: current temperature reading (float)
- `uptime`: seconds since boot (int)
- `logs_enabled`: whether periodic logging is active (bool)
- `authenticated`: whether the session is authenticated (bool)

### config get [key]

Get all configuration values (no key) or a single key.

```
> config get
{"log_interval_ms":1000,"sample_rate_hz":10,"device_name":"DemoDevice"}
> config get log_interval_ms
{"log_interval_ms":1000}
>
```

### config set \<key\> \<value\>

Set a configuration value.

```
> config set log_interval_ms 500
OK log_interval_ms=500
>
```

Valid keys and ranges:
- `log_interval_ms`: 100–10000 (int)
- `sample_rate_hz`: 1–100 (int)
- `device_name`: any string

### log start [interval_ms]

Start periodic log output. You can set the interval. This overrides the `log_interval_ms` config value.

```
> log start
OK logs started (interval=1000ms)
> [LOG] 14:32:01 temp=42.1 humidity=65.3 pressure=1013.2
[LOG] 14:32:02 temp=41.8 humidity=65.5 pressure=1013.0
```

Log lines have the format:
```
[LOG] HH:MM:SS temp=<float> humidity=<float> pressure=<float>
```

The device emits log lines asynchronously. They can appear even while the device waits for a command. The prompt is still valid. Send a command, and the device responds.

### log stop

Stop periodic logging.

```
> log stop
OK logs stopped
>
```

### sample \<count\>

Collect a fixed number of sensor samples and then stop. The device emits one line per sample, then a `DONE` marker.

```
> sample 3
OK sampling 3 at 10Hz
[SAMPLE] 1/3 temp=42.1 humidity=65.2
[SAMPLE] 2/3 temp=41.9 humidity=65.4
[SAMPLE] 3/3 temp=42.3 humidity=65.0
[SAMPLE] DONE
>
```

Use `read_until` with delimiter `DONE` to collect all samples in one call. `config set sample_rate_hz` controls the sample rate. Count must be 1–1000.

### auth \<password\>

Authenticate the session. You need this for `secret` and `factory-reset`.

```
> auth demo1234
OK authenticated
> auth wrong
ERROR: wrong password
>
```

The password is `demo1234`.

### secret

Read a secret value. This needs authentication.

```
> secret
ERROR: not authenticated
> auth demo1234
OK authenticated
> secret
The answer is 42.
>
```

### factory-reset

Reset the device to its defaults. This needs authentication. It resets the config, clears authentication, stops logging and sampling, and reboots the device.

```
> factory-reset
OK factory reset
[BOOT] DemoDevice v1.0.0
[BOOT] Ready.
>
```

### reboot

Reboot the device. This stops all activity, pauses for about 1 second, then prints the boot banner.

```
> reboot
Rebooting...
[BOOT] DemoDevice v1.0.0
[BOOT] Ready.
>
```

## Error handling

Unknown commands:
```
> foo
ERROR: unknown command 'foo'. Type 'help' for available commands.
>
```

Wrong arguments:
```
> config set
ERROR: usage: config set <key> <value>
>
```

## Multi-step flows

### Authenticate and read secret

1. `auth demo1234` → `OK authenticated`
2. `secret` → `The answer is 42.`

### Configure and collect samples

1. `config set sample_rate_hz 5` → `OK sample_rate_hz=5`
2. `sample 10` → 10 sample lines + `[SAMPLE] DONE`

### Start logging, send commands, stop logging

1. `log start 2000` → `OK logs started (interval=2000ms)`
2. `ping` → `pong` (log lines may appear between prompt and response)
3. `log stop` → `OK logs stopped`

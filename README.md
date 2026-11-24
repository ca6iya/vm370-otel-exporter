# vm370-otel-exporter

Prometheus and OTLP exporter for **VM/370 Community Edition** CP text, the
Release 6 `INDICATE` and `QUERY` lines produced under Hercules by the
[zvm_play](https://github.com/ca6iya/zvm_play) console monitor.

This repository is the VM/370 exporter. `zvm.linux.*` guest-file series stay
in `zvm-agent` (in [zvm-otel-exporter](https://github.com/ca6iya/zvm-otel-exporter)).
A `/proc` snapshot collected from the separate s390x Linux guest is that
agent's OTLP scope. This process uses the scope name `vm370-otel-exporter`
and does not emit `zvm.linux.*`.

The program reads CP text from a file or stdin. It does not read `/proc`,
hypfs, monreader, vmcp, or Feilong, and it does not send Hercules or shell
commands. `/metrics` listens on `127.0.0.1:9370`.

These conversions were **not run on a live VM/370**. The numbers below are a
contract to confirm against a real `INDICATE` / IPL log before anyone treats
them as production measurements.

## Contract

Every instrument name starts with `zvm.vm370.`. The dotted name is the
catalog name and the OTLP instrument name. Prometheus text replaces each dot
with an underscore, appends a unit suffix, and appends `_total` on counters.

| CP text | Instrument | Kind | Value |
| --- | --- | --- | --- |
| `CPU-002%` | `zvm.vm370.cpu.utilization` | gauge | `0.02` (percent / 100) |
| `APU-000%` | `zvm.vm370.apu.utilization` | gauge | percent / 100 |
| `Q1-00`, `Q2-00` | `zvm.vm370.queue.depth` | gauge | printed depth, attribute `zvm.vm370.queue=q1` or `q2` |
| `STORAGE-012%` | `zvm.vm370.storage.utilization` | gauge | `0.12`. Real storage in use. |
| `RATIO-01.0` | `zvm.vm370.paging.ratio` | gauge | printed factor `1.0` |
| `READS=000034` | `zvm.vm370.paging.reads` | counter | `34` pages, cumulative, per userid |
| `WRITES=` | `zvm.vm370.paging.writes` | counter | pages, cumulative, per userid |
| `RES-`, `WS-` | `zvm.vm370.guest.pages.resident`, `.working_set` | gauge | pages |
| `VTIME=mmm:ss`, `TTIME=mmm:ss` | `zvm.vm370.guest.vtime`, `.ttime` | counter | seconds (`minutes * 60 + seconds`), only when the field is `mmm:ss` |
| `SIO=`, `RDR-`, `PRT-`, `PCH-` | `zvm.vm370.guest.sio`, `.rdr`, `.prt`, `.pch` | counter | printed count |
| `DISK-`, `DRUM-` | `zvm.vm370.paging.disk`, `.drum` | gauge | pages allocated when INDICATE runs |
| `QUERY NAMES` `WAKEUP - DSC` | `zvm.vm370.guest.info` | gauge | `1`, attributes userid and terminal |
| IPL `Storage size = N K` and the nucleus, dynamic paging, trace table, free storage, and virtual=real fields | `zvm.vm370.storage.size`, `.nucleus`, `.dynamic_paging`, `.trace_table`, `.free`, `.virtual_real` | gauge | `N * 1024` bytes |

`STORAGE-nnn%` is real storage. The playground JSON field `steal_pct` is the
same percent under another name. This exporter does not use that name.

`READS=` and `WRITES=` stay cumulative page counters. They are not divided
into a per-second rate. `RATIO` stays the printed factor. `DISK-` and
`DRUM-` are the pages allocated at that moment, so a later sample can be
lower.

`VTIME=1:02:03` and `TTIME=00:00:00` do not match `mmm:ss`, so those fields
are skipped.

Per-userid series take `zvm.vm370.userid` from a preceding `ind user <userid>`
echo. The example log line is `/(0009) ind user WAKEUP`.

## Identity

Resource attributes come only from the VMMON line

```text
[DIAG00]HYPERVISOR=VM/370   VM_USERID=CMSUSER
```

| Attribute | Source |
| --- | --- |
| `zvm.hypervisor` | `HYPERVISOR=` |
| `zvm.system.name` | `HYPERVISOR=` |
| `zvm.exporter.guest` | `VM_USERID=` |

`host.arch` is set only when the supplied text has its own `host.arch=`
line. VM/370 CP text does not. Do not point this exporter at
`zvm-agent/fixtures/sysinfo.txt`. That file describes z/VM 7.3.0 on CPC type
3906, which is a different system.

OTLP `service.name` is `vm370-otel-exporter`. The meter scope name is the
same string. Keep a zvm-agent `/proc` export on its own scope if both are
sent to one collector.

## Run

```bash
python -m vm370_otel_exporter --text cp.txt
python -m vm370_otel_exporter --text cp.txt --once
python -m vm370_otel_exporter --text - < cp.txt
python -m vm370_otel_exporter --catalog
```

When `--text` is a file, `/metrics` and OTLP callbacks re-read that file on
each scrape. Stdin is parsed once. The process still does not send Hercules
or shell commands; [zvm_play](https://github.com/ca6iya/zvm_play)
`./capture-cp-text.sh` writes the file.

The server binds `127.0.0.1:9370` and answers `GET /metrics`. Any other
listen address is rejected. Put the container on the host network so that
loopback bind is the host loopback. Pass `--otlp http://127.0.0.1:4318` to push
OTLP/HTTP to a local collector. A schemeless address uses TLS. `--otlp-protocol grpc`
selects OTLP/gRPC. `--otlp-insecure` selects plaintext and is refused when
`OTEL_EXPORTER_OTLP_HEADERS` or `OTEL_EXPORTER_OTLP_METRICS_HEADERS` is set.
Plaintext HTTP does not read `~/.netrc`. An https export does not follow a
redirect onto http, and a redirect to another origin drops credential headers. Omit `--otlp` and the
process does not open an OTLP connection.

Prometheus scrape:

```yaml
scrape_configs:
  - job_name: vm370
    static_configs:
      - targets: ["127.0.0.1:9370"]
```

On this homelab the OTLP path already lands series on NAS Prometheus
(`192.168.1.181:9090`) as `zvm_vm370_*` with `job="vm370-otel-exporter"`.
OpenTelemetry adds a `_ratio` suffix on unit-1 gauges (`cpu_utilization_ratio`).
Do not import the z/VM dashboards from `zvm-otel-exporter` — those use Feilong
names and steal.

Grafana (`http://192.168.1.181:3001`): import
`examples/grafana/vm370-playground.json` (uid `vm370-playground`).
Every query uses `job="vm370-otel-exporter"` so the collector re-export
(`job="otel-collector-metrics"`) does not draw a second CPU line. STORAGE is
percent 0–1, not steal. READS is the cumulative counter.

This board is one **hypervisor** (many `zvm_vm370_userid` guests). Linux s390x
hosts use the separate zLinux dashboard in
[zvm_play](https://github.com/ca6iya/zvm_play/blob/main/dashboards/grafana/zlinux-agent.json)
(Node Exporter Full / Grafana 1860 layout).

## Docker / Dockhand Git stack

`docker-compose.yml` is Git-stack ready: image only, no `build:`, no
top-level `name:`, no `container_name:`, no `env_file`. The image is
`ghcr.io/ca6iya/vm370-otel-exporter:latest` (`linux/amd64`). Compose uses
`network_mode: host` so `/metrics` stays on `127.0.0.1:9370`. An empty
`vm370_cp_text` volume is seeded from `examples/cp-sample.txt`.

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --wait
curl -sS http://127.0.0.1:9370/metrics
```

Optional env (interpolated by Dockhand Git deploy):

- `VM370_TEXT` default `/data/cp.txt`
- `VM370_OTLP` empty means Prometheus only. `http://127.0.0.1:4318` plus
  `VM370_OTLP_INSECURE=1` pushes plaintext OTLP to a host collector.
- `VM370_TAG` image tag, default `latest`

Copy a live playground snapshot into the volume after
`./capture-cp-text.sh` on zvm_play. The next scrape re-parses the file:

```bash
docker run --rm \
  -v vm370_cp_text:/data \
  -v "$PWD/monitor/cp-snapshot.txt:/src/cp.txt:ro" \
  alpine cp /src/cp.txt /data/cp.txt
```

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
```

Fixtures under `tests/fixtures/` are the CP examples plus `no_match.txt`.
Tests do not need Hercules. A test fails when a catalog or sample name does
not start with `zvm.vm370.`, when the storage percent is named steal, or when
`READS` is declared as a rate.

Apache-2.0.

# 7.x to 8.1 Breaking Changes

These changes cause **server startup failures** if old syntax is used. Always verify your aerospikeConfig against this list.

| Item | 7.x (Old) | 8.1 (New) | Since |
|------|-----------|-----------|-------|
| Info port | `info { port 3003 }` | **Removed**. Use `admin { port 3008 }` | 8.1.0 |
| Memory data | `memory-size 4G` | `storage-engine memory { data-size 4G }` | 7.0 deprecated, 7.1 removed |
| Write block | `write-block-size 128K` | `flush-size 128K` (internal write-block fixed at 8M) | 7.1 |
| Max record size | Default = write-block-size | **Default 1M**, max 8M | 7.1 |
| Index memory | `memory-size` (device mode) | `indexes-memory-budget` | 7.0 deprecated |
| Stop writes | `stop-writes-pct` | `stop-writes-sys-memory-pct` | 7.0 removed |
| Eviction | `high-water-memory-pct` | `evict-used-pct`, `evict-tenths-pct` | 7.0 removed |
| Data in memory | Namespace level | Inside `storage-engine device` block | 7.0 moved |
| MRT write-block | N/A | Affects data-size calculation | 8.0 |

## Migration Examples

```diff
# Memory storage engine
- namespace cache { memory-size 4G; storage-engine memory }
+ namespace cache { storage-engine memory { data-size 4G } }

# Device storage engine
- namespace data { storage-engine device { write-block-size 128K } }
+ namespace data { storage-engine device { flush-size 128K } }

# Network info port (REMOVED)
- network { info { port 3003 } }
+ network { admin { port 3008 } }
```

**Critical**: If `info {}` block remains in config, the server fails with a **parse error** and the pod enters CrashLoopBackOff.

**Minimum data-size**: 512 MiB (8 stripes * 8 write-blocks * 8 MiB = `536870912` bytes).

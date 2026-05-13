# ackoctl command reference

Every `ackoctl` command with one-line description and a copy-pasteable example. Use this when constructing precise invocations — the parent `SKILL.md` covers the high-level grammar.

Conventions:

- `<CONN_ID>` — connection profile UUID, obtained from `ackoctl connection list`.
- `<NS>/<NAME>` — Kubernetes namespace + AerospikeCluster CR name, e.g. `aerospike/sample`.
- `-o table|json|yaml` is available on every list/get; default is `table`.
- Destructive verbs (`delete`, `remove`, `revoke`, mutation `info`) require `--yes` to skip the interactive confirmation.

## Top-level

| Command | Description | Example |
|---------|-------------|---------|
| `ackoctl version` | Print version, commit, build date | `ackoctl version` |
| `ackoctl --help` | Top-level help / discovery | `ackoctl --help` |

## config — context management

| Command | Description | Example |
|---------|-------------|---------|
| `config set-context NAME` | Create or update a context | `ackoctl config set-context prod --server=https://acm.example.com/api --token=eyJ... --workspace-id=prod-us` |
| `config use-context NAME` | Switch the active context | `ackoctl config use-context prod` |
| `config current-context` | Print the active context name | `ackoctl config current-context` |
| `config view` | Show full config (redacts tokens) | `ackoctl config view -o yaml` |
| `config delete-context NAME` | Remove a context | `ackoctl config delete-context prod` |

## connection — Aerospike connection profiles

| Command | Description | Example |
|---------|-------------|---------|
| `connection list` | List connection profiles in the workspace | `ackoctl connection list` |
| `connection get ID` | Show one profile | `ackoctl connection get 1f3c... -o yaml` |
| `connection create` | Create a profile (multi `--host` allowed) | `ackoctl connection create --name local-aero --host node-1 --host node-2 --port 3000 --label env=dev` |
| `connection update ID` | Patch a profile (name, hosts, labels) | `ackoctl connection update 1f3c... --name renamed` |
| `connection delete ID` | Remove a profile (cascades notes) | `ackoctl connection delete 1f3c... --yes` |
| `connection health ID` | Live reachability probe | `ackoctl connection health 1f3c...` |

## cluster — cluster inspection and namespace tuning

| Command | Description | Example |
|---------|-------------|---------|
| `cluster info CONN_ID` | Full snapshot — nodes, namespaces, sets, sindex counts | `ackoctl cluster info 1f3c... -o yaml` |
| `cluster configure-namespace CONN_ID` | Tune runtime-mutable namespace knobs (`asinfo set-config`) | `ackoctl cluster configure-namespace 1f3c... --name=test --param=high-water-disk-pct=70 --param=stop-writes-pct=90` |

## set — set inventory

| Command | Description | Example |
|---------|-------------|---------|
| `set list CONN_ID` | List sets, optionally scoped to a namespace | `ackoctl set list 1f3c... --namespace=test` |

## record — data plane

| Command | Description | Example |
|---------|-------------|---------|
| `record list CONN_ID` | Paged record listing | `ackoctl record list 1f3c... --namespace=test --set=users --page-size=100` |
| `record get CONN_ID` | Read one record by PK | `ackoctl record get 1f3c... --namespace=test --set=users --pk=alice` |
| `record put CONN_ID` | Write one record (`--bins` is JSON) | `ackoctl record put 1f3c... --namespace=test --set=users --pk=alice --bins='{"name":"Alice","age":30}' --ttl=3600` |
| `record delete CONN_ID` | Delete one record | `ackoctl record delete 1f3c... --namespace=test --set=users --pk=alice --yes` |
| `record query CONN_ID` | PK-pattern + predicate scan | `ackoctl record query 1f3c... --namespace=test --set=users --pk-pattern='ali' --pk-match-mode=prefix --select=name,age` |

`--filter` and `--predicate` accept raw JSON to pass the full `FilterGroup` / `QueryPredicate` DSL. `--pk-type` pins the particle type (`auto|string|int|bytes`); `auto` retries the alternate type on `NOT_FOUND`.

## query — predicate, pk-lookup, full scan

| Command | Description | Example |
|---------|-------------|---------|
| `query exec CONN_ID` (predicate) | Bin predicate query | `ackoctl query exec 1f3c... --namespace=test --set=users --bin=age --op=between --value=18 --value2=30 --select=name,age` |
| `query exec CONN_ID` (pk lookup) | Primary-key lookup | `ackoctl query exec 1f3c... --namespace=test --set=users --primary-key=alice --pk-type=string` |
| `query exec CONN_ID` (scan) | Full scan with cap | `ackoctl query exec 1f3c... --namespace=test --set=users --max-records=1000` |

Operators: `equals | between | contains | geo_within_region | geo_contains_point`. `--value` / `--value2` parse as JSON (so `30` stays int and `"alice"` stays string).

## index — secondary indexes

| Command | Description | Example |
|---------|-------------|---------|
| `index list CONN_ID` | List secondary indexes | `ackoctl index list 1f3c...` |
| `index create CONN_ID` | Create a secondary index | `ackoctl index create 1f3c... --namespace=test --set=users --bin=age --name=idx_age --type=numeric` |
| `index delete CONN_ID` | Drop a secondary index | `ackoctl index delete 1f3c... --namespace=test --name=idx_age --yes` |

`--type`: `numeric | string | geo2dsphere`.

## note — operator notes (cluster-manager metaDB)

| Command | Description | Example |
|---------|-------------|---------|
| `note set update CONN_ID` | Create/update a set-level note | `ackoctl note set update 1f3c... --namespace=test --set=users --note='migration in progress'` |
| `note set delete CONN_ID` | Remove a set-level note | `ackoctl note set delete 1f3c... --namespace=test --set=users --yes` |
| `note set list CONN_ID` | List set-level notes for a connection | `ackoctl note set list 1f3c...` |
| `note record update CONN_ID` | Create/update a record-level note | `ackoctl note record update 1f3c... --namespace=test --set=users --pk=alice --note='under investigation'` |
| `note record delete CONN_ID` | Remove a record-level note | `ackoctl note record delete 1f3c... --namespace=test --set=users --pk=alice --yes` |
| `note record list CONN_ID` | List record-level notes for a (conn, ns, set) | `ackoctl note record list 1f3c... --namespace=test --set=users` |

Notes are scoped per connection profile and cascade-delete with the connection. Max body length is 8 KB; table output truncates to 60 chars (JSON/YAML keeps the full body).

## k8s — ACKO-managed AerospikeCluster CRs

Requires cluster-manager to have `K8S_MANAGEMENT_ENABLED=true`; otherwise the server returns 404.

| Command | Description | Example |
|---------|-------------|---------|
| `k8s cluster list` | List all AerospikeCluster CRs | `ackoctl k8s cluster list` |
| `k8s cluster get NS/NAME` | Inspect one CR (phase, size, conditions) | `ackoctl k8s cluster get aerospike/sample-cluster -o yaml` |
| `k8s cluster reconcile NS/NAME` | Stamp `acko.io/force-reconcile` | `ackoctl k8s cluster reconcile aerospike/sample-cluster` |
| `k8s cluster scale NS/NAME` | Patch `spec.size` | `ackoctl k8s cluster scale aerospike/sample-cluster --size=5 --yes` |
| `k8s pod logs NS/NAME` | Stream / tail pod logs | `ackoctl k8s pod logs aerospike/sample-cluster --pod=sample-cluster-0-0 --container=aerospike-server --since=5m --tail=200` |
| `k8s events list NS/NAME` | Classified event timeline | `ackoctl k8s events list aerospike/sample-cluster --since=30m` |

`NS/NAME` is `"<namespace>/<name>"` — always quote it in shell.

## info — raw asinfo

| Command | Description | Example |
|---------|-------------|---------|
| `info exec CONN_ID --command=...` | Whitelisted read verbs (status, statistics, namespace/<ns>, ...) | `ackoctl info exec 1f3c... --command='statistics'` |
| `info exec CONN_ID --command=... --node=...` | Target one node | `ackoctl info exec 1f3c... --command='status' --node=BB9020014270008` |
| `info exec CONN_ID --command=... --allow-write --yes` | Mutation verbs (`set-config:`, `recluster:`, ...) | `ackoctl info exec 1f3c... --command='set-config:context=service;proto-fd-max=20000' --allow-write --yes` |

Mutation verbs require both `--allow-write` and a confirmation (`--yes` or interactive `y`).

## admin — users and roles (security-enabled clusters)

Only applies when the target cluster has security enabled in `aerospike.conf`. CE clusters managed by ACKO do not — these commands target Aerospike Enterprise clusters reached via cluster-manager.

| Command | Description | Example |
|---------|-------------|---------|
| `admin user list CONN_ID` | List users and their roles | `ackoctl admin user list 1f3c...` |
| `admin user create CONN_ID` | Create a user | `ackoctl admin user create 1f3c... --name=alice --password=*** --role=read-write` |
| `admin user grant CONN_ID` | Add roles to a user | `ackoctl admin user grant 1f3c... --name=alice --role=sys-admin` |
| `admin user revoke CONN_ID` | Remove roles from a user | `ackoctl admin user revoke 1f3c... --name=alice --role=read-write` |
| `admin user passwd CONN_ID` | Change a user's password | `ackoctl admin user passwd 1f3c... --name=alice --password=***` |
| `admin user delete CONN_ID` | Remove a user | `ackoctl admin user delete 1f3c... --name=alice --yes` |
| `admin role list CONN_ID` | List roles and privileges | `ackoctl admin role list 1f3c...` |
| `admin role create CONN_ID` | Create a role with privileges | `ackoctl admin role create 1f3c... --name=ops-readonly --privilege=read` |
| `admin role delete CONN_ID` | Drop a role | `ackoctl admin role delete 1f3c... --name=ops-readonly --yes` |

## udf — Lua UDF module management

| Command | Description | Example |
|---------|-------------|---------|
| `udf list CONN_ID` | List registered UDF modules | `ackoctl udf list 1f3c...` |
| `udf register CONN_ID` | Register a UDF from a local file | `ackoctl udf register 1f3c... --file=./examples/sum.lua --name=sum.lua` |
| `udf get CONN_ID` | Fetch one UDF (source + metadata) | `ackoctl udf get 1f3c... --name=sum.lua -o yaml` |
| `udf remove CONN_ID` | Unregister a UDF | `ackoctl udf remove 1f3c... --name=sum.lua --yes` |

UDF registration is cluster-wide. Use `ackoctl note` to record provenance/ticket links for a registered module.

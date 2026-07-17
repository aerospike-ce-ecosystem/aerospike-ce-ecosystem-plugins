---
name: bug-reporter
description: "MUST USE when an ACKO/Aerospike CE Ecosystem user hits an error, bug, crash, unexpected behavior, or wants to file an issue and is unsure which `aerospike-ce-ecosystem` org repo to report it to. Routes the report to the correct repo (aerospike-py / aerospike-ce-kubernetes-operator / aerospike-cluster-manager / ackoctl / aerospike-ce-ecosystem-plugins / project-hub) based on symptom, and generates a ready-to-paste GitHub issue body with the required reproduction context (versions, logs, CR YAML, kubectl describe output, ackoctl command, etc.). Triggers on: '버그 제보', 'bug report', 'where do I file this issue', 'report this to GitHub', 'which repo do I open an issue in', '이슈 어디다 올려야 해', 'AerospikeCluster CR phase=Error 제보', 'aerospike-py panicked', 'cluster-manager UI 500', 'ackoctl crashed', '플러그인 skill 오작동'."
---

> **추천**: 이 plugin을 사용하는 프로젝트의 `CLAUDE.md`에 다음 문구를 추가해두면, 사용자가 버그를 마주쳤을 때 Claude가 자동으로 이 skill을 호출해 올바른 repo로 안내합니다.
>
> ```markdown
> ## Bug Reporting
>
> 이 워크스페이스에서 Aerospike CE Ecosystem 관련 에러/버그를 만났다면
> `bug-reporter` skill을 사용해 `aerospike-ce-ecosystem` org의 올바른 repo에 이슈를 제보하세요.
> ```

# bug-reporter — aerospike-ce-ecosystem 이슈 라우팅 가이드

에러/버그를 발견했을 때 **어느 GitHub repo에 이슈를 올려야 하는지** 판별하고, 재현 컨텍스트를 모아 바로 붙여넣을 수 있는 이슈 본문을 만들어 주는 skill. org URL: <https://github.com/aerospike-ce-ecosystem>

## 1. 어느 repo에 제보해야 하나? (Decision Table)

| 증상 / 컴포넌트 | 제보할 Repo | New Issue URL |
|---|---|---|
| Aerospike 서버 자체 (CE 8.x) 버그, asd 코어덤프, namespace 동작 이상 | **Aerospike 본가** (외부) | <https://github.com/aerospike/aerospike-server/issues> |
| Python에서 `import aerospike_py` 후 발생한 에러 (panic, segfault, 잘못된 NamedTuple, exception 클래스 위치 등) | `aerospike-py` | <https://github.com/aerospike-ce-ecosystem/aerospike-py/issues/new> |
| AerospikeCluster CRD 리컨실 실패, webhook reject, ACKO operator pod CrashLoop, `phase=Error/ConfigDegraded`, dynamic config rollback | `aerospike-ce-kubernetes-operator` (ACKO) | <https://github.com/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator/issues/new> |
| cluster-manager 웹 UI 500/404, Record browser / Query builder 오작동, FastAPI 백엔드 에러, Next.js 페이지 깨짐, OIDC/Keycloak 로그인 실패 | `aerospike-cluster-manager` | <https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager/issues/new> |
| `ackoctl` CLI 크래시, 잘못된 명령 grammar, context 설정 문제, install.sh 실패, sha256 검증 실패 | `ackoctl` | <https://github.com/aerospike-ce-ecosystem/ackoctl/issues/new> |
| Claude Code Skill / Agent (이 plugin) 동작 이상, 잘못된 정보, 트리거 누락, plugin.json 오류 | `aerospike-ce-ecosystem-plugins` | <https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/issues/new> |
| 여러 repo에 걸친 이슈, ADR 제안, roadmap/release matrix 누락, 문서 오류 | `project-hub` | <https://github.com/aerospike-ce-ecosystem/project-hub/issues/new> |

> **판단이 어려울 때**: 어디서 에러가 던져졌는지를 따라가세요.
> - Python traceback 최상단이 `aerospike_py.*` → `aerospike-py`
> - `kubectl describe asc` 의 Events 또는 operator log → `aerospike-ce-kubernetes-operator`
> - 브라우저 콘솔 또는 cluster-manager 백엔드 traceback → `aerospike-cluster-manager`
> - 터미널에서 친 명령이 `ackoctl ...` 였다면 → `ackoctl`
> - Claude Code 안에서 skill/agent 가 잘못된 응답을 했다면 → `aerospike-ce-ecosystem-plugins`
> - **그래도 모르겠다면 `project-hub` 에 올리세요.** Hub planner가 적절한 sub-repo로 dispatch 해 줍니다 (`cross-repo` 라벨).

## 2. 제보 전에 먼저 할 일

1. **중복 검색** — `gh issue list --repo aerospike-ce-ecosystem/<repo> --search "<error message snippet>"` 로 같은 증상이 이미 올라와 있는지 확인.
2. **최신 버전 확인** — 이미 고쳐졌을 수 있습니다. aerospike-py: `pip show aerospike-py` vs PyPI 최신 / ACKO: `kubectl -n aerospike-operator get deploy aerospike-operator-controller-manager -o jsonpath='{.spec.template.spec.containers[0].image}'` / cluster-manager: UI 우하단 build info 또는 API `/api/v1/version` / ackoctl: `ackoctl version`.
3. **재현 최소화** — minimal reproducer로 줄이세요. CR YAML이면 size=1, 단일 namespace로; Python 코드면 5~10줄 안으로.

## 3. 이슈 본문 템플릿 (repo별)

공통 헤더(환경/재현 단계/기대·실제 동작/로그)와 repo별 필수 첨부물 체크리스트: **[`./reference/issue-templates.md`](./reference/issue-templates.md)**

핵심만 요약: aerospike-py는 `python --version` + traceback(+`RUST_BACKTRACE=1`), ACKO는 CR YAML(민감정보 제거) + `describe asc` Events + operator log, cluster-manager는 실패한 API 요청/콘솔 에러 + `/api/v1/version`, ackoctl은 `ackoctl version` + `-v` 재실행 출력(token redact), plugins는 skill 이름 + prompt + 잘못된 답변, project-hub는 영향 repo 목록.

## 4. 라벨 가이드

org 공통 [Agentic Workflow 라벨](https://github.com/aerospike-ce-ecosystem/project-hub/blob/main/docs/docs/coordination/labels.md):

- 분명한 버그 → `bug` · AI agent에게 맡기고 싶음 → `agent` · 정보 부족 → `needs-clarification` · 여러 repo에 걸침 → project-hub 에 올리고 `cross-repo`

CE 한정 제약(8노드/2 namespace/XDR·TLS 없음 …) 위반은 **버그가 아니라 Webhook의 의도된 동작**입니다. 그 경우는 이슈 대신 GitHub Discussion에 올려주세요.

## 5. `gh` 로 한 번에 이슈 만들기

```bash
gh issue create \
  --repo aerospike-ce-ecosystem/<repo> \
  --title "<짧고 행동 중심: 'asc reconcile loops on size patch when storage-engine=device'>" \
  --label bug \
  --body-file ./issue-body.md
```

이 skill을 사용할 때 Claude가 할 일: ① 증상 설명 → repo 결정 ② `reference/issue-templates.md` 템플릿으로 `issue-body.md` 채우기 (민감 정보 제거) ③ `gh issue list --search` 로 중복 확인 ④ (사용자 승인 후) `gh issue create` 실행.

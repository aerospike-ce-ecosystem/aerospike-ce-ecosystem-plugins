# 이슈 본문 템플릿 (repo별)

## 공통 헤더

```markdown
## 환경
- OS:                          # macOS 14.5 / Ubuntu 22.04 / ...
- Aerospike server image:      # aerospike/aerospike-server:ce-8.1.x.x
- Kubernetes:                  # kind v0.23 / EKS 1.30 / minikube ...
- 컴포넌트 버전: <아래 repo별로 채움>

## 무엇을 했는지 (재현 단계)
1. ...
2. ...

## 기대한 동작
...

## 실제 동작
...

## 로그 / 에러 메시지
<details><summary>logs</summary>

```
<paste here>
```

</details>
```

## `aerospike-py`

추가로 첨부할 것:
- `python --version`, `pip show aerospike-py`
- 5~20줄 재현 스니펫 (가능하면 docstring/주석 포함)
- 전체 traceback (`aerospike_py.*` 호출 stack 포함)
- panic 인 경우 `RUST_BACKTRACE=1` 출력

## `aerospike-ce-kubernetes-operator` (ACKO)

추가로 첨부할 것:
- 문제의 AerospikeCluster CR (`kubectl get asc <name> -n <ns> -o yaml`) — secret/feature-key 같은 민감 정보 제거
- `kubectl describe asc <name> -n <ns>` 의 Events 섹션
- Operator log 의 reconcile 실패 구간 (앞뒤 30줄)
  ```bash
  # Deployment 이름은 설치 방식에 따라 다릅니다(Helm: `<release>-aerospike-ce-kubernetes-operator`,
  # kustomize: `aerospike-ce-kubernetes-operator-controller-manager`). 양쪽 모두 pod에
  # `control-plane=controller-manager` 라벨이 붙으므로 라벨로 선택하세요.
  kubectl -n aerospike-operator logs -l control-plane=controller-manager --since=10m --tail=200
  ```
- `phase`, `conditions`, `lastReconcileTime`
- CE 환경임을 명시 (Enterprise 기능 시도가 아닌지 한번 자문)

## `aerospike-cluster-manager`

UI 버그:
- 브라우저 + 버전 (Chrome 138 / Safari 17 …)
- 재현 페이지 URL 패스 (예: `/clusters/<clusterId>/sets/<namespace>/<set>/records/<key>`)
- 브라우저 콘솔 에러 + Network 탭에서 실패한 API 요청 (Request/Response)
- 스크린샷 또는 짧은 화면 녹화

백엔드 버그:
- 호출한 endpoint와 method, payload
- FastAPI traceback (`uvicorn` 로그)
- 배포된 api 컨테이너 image tag (버전 endpoint는 없습니다):
  ```bash
  kubectl -n aerospike-operator get pod -l app.kubernetes.io/component=ui-api \
    -o jsonpath='{.items[0].spec.containers[0].image}'
  ```

## `ackoctl`

- `ackoctl version`
- 실행한 명령 (flags 포함, token은 마스킹)
- `-v` 로 다시 실행한 출력 (stderr 포함)
- `~/.ackoctl/config.yaml` 의 관련 context (token/server URL은 redact)

## `aerospike-ce-ecosystem-plugins`

- 어떤 skill / agent 인지 (`name:` 또는 path)
- Claude Code 안에서 사용자가 입력한 prompt (또는 `/<command>`)
- skill이 잘못 답한 내용 (스크린샷이면 더 좋음)
- 기대했던 답 / 동작
- plugin 버전 (`.claude-plugin/plugin.json` 의 `version`)

## `project-hub` (cross-repo / docs / ADR)

- 영향받는 repo 목록 (`cross-repo` 라벨 후보)
- 문서 오류라면 정확한 URL과 라인
- ADR 제안이라면 [기존 ADR 디렉토리](https://github.com/aerospike-ce-ecosystem/project-hub/tree/main/docs/docs/architecture/adr)의 형식을 참고

# Web (agv-jetson)

이 문서는 Web/플래너 관련 컴포넌트(웹 UI, AI 노드, 플래너 인터페이스 등)를 정리한 README 입니다. `Drive_Control/Readme.md`의 형식을 참고하여 구조화했습니다.

## 폴더 구조(요약)
```
Web/
├─ interfaces/
│  ├─ mqtt_topics.yaml
│  └─ schemas/
│     ├─ items.schema.json
│     └─ path.schema.json
├─ config/
│  └─ dev/
│     ├─ mqtt.json
│     ├─ planner.json
│     └─ control.json
├─ data/
│  ├─ poi/
│  │  └─ store_A_poi.json
│  └─ samples/
│     └─ items_example.json
├─ cpp/
│  ├─ CMakeLists.txt
│  ├─ include/
│  ├─ src/
│  └─ apps/
│     ├─ sim_main.cpp
│     └─ planner_main.cpp
└─ python/
   ├─ ai_node/
   └─ webapp/
      ├─ app.py
      ├─ mqtt_pub.py
      └─ telemetry.py
```

## 구성 요소

- `MQTT Broker` : Eclipse Mosquitto (Docker로 실행 권장)
- `Planner Node (Python)` : `agv/ai/items`를 구독해 A* 기반 경로를 계산하고 `agv/planner/global_path`로 발행
- `AI Node (Python)` : 텍스트/오디오 → 아이템 파싱 → `agv/ai/items` 발행
- `Web UI / API (FastAPI)` : 사용자 입력, 상태/지도 조회, 명령 발행 (MQTT 연동)
- `C++ Planner` : 로컬 빌드 가능한 대체 플래너(C++ 예제)

## 토픽 및 데이터 흐름

- `agv/ai/items` — AI → Planner (스키마: `interfaces/schemas/items.schema.json`)
- `agv/planner/global_path` — Planner → Control (스키마: `interfaces/schemas/path.schema.json`)
- `agv/state/pose` — Localization → Web
- `agv/web/command` — Web → AGV (명령)

동작 흐름:
1. 사용자 또는 AI 노드가 `agv/ai/items`에 아이템 리스트 발행
2. Planner가 경로 계산 후 `agv/planner/global_path` 발행
3. 로컬화/제어 노드가 경로를 받아 제어 실행
4. Web(telemetry)은 `agv/state/pose` 및 `agv/planner/global_path`를 구독해 UI에 표시

## 주요 파일

- `interfaces/mqtt_topics.yaml` : 토픽 정의
- `interfaces/schemas/items.schema.json` : items 페이로드 스키마
- `interfaces/schemas/path.schema.json` : path 페이로드 스키마
- `config/dev/*.json` : 환경별 설정
- `python/ai_node/` : AI 노드 구현 (아이템 파싱)
- `python/webapp/app.py` : FastAPI 앱
- `python/webapp/mqtt_pub.py` : 웹에서 MQTT 발행 헬퍼
- `python/webapp/telemetry.py` : UI용 MQTT 구독/발행
- `cpp/` : C++ 플래너 예제

## 실행 가이드 (요약)

1. MQTT 브로커 (Docker Compose 권장):

```bash
docker-compose up -d
```

2. Planner(파이썬) 실행 또는 Docker Compose 서비스 사용

3. Web UI (개발):

```bash
cd python/webapp
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

4. AI 노드 테스트:

```bash
python python/ai_node/main.py
```


## 의존성

- Python 3.11 권장
- 주요 패키지: `paho-mqtt`, `fastapi`, `uvicorn`, `pydantic`, `python-dotenv`

각 서비스의 `requirements.txt` 또는 Dockerfile을 확인하세요.

## 누락/주의사항

- `localization_node` 및 `control_node`는 레포지토리에 포함되어 있지 않습니다(외부 서비스 가정). 토픽/페이로드 계약을 확인하세요.
- OpenAI 연동 기능은 `OPENAI_API_KEY`가 필요할 수 있습니다.

## 기여

버그 리포트나 개선 제안은 이 저장소의 이슈에 남겨주세요.
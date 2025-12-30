# AGV Jetson Nano Project
<img width="46%" alt="main" src="https://github.com/user-attachments/assets/2073dd20-728c-4965-83b7-ac298bbf77c7" />
<img width="52%" alt="systemachitecture" src="https://github.com/user-attachments/assets/3b2590bd-222a-4224-bcbc-8fde4a967a7d" />

Jetson Nano 기반 AGV(스마트 카트) 프로젝트의 통합 문서입니다. 이 파일은 `Drive_Control`과 `Web` 모듈의 README를 통합하여 전체 구조, 실행 방법, 메시지 규격 및 기여 정보를 제공합니다.

## 기여자

- 제영호
- 성주희

## 목표 요약

- 음성 인식/AI 결과로 생성된 `items` JSON을 입력으로 받아
- POI(진열대 좌표)를 매핑하고 방문 순서를 결정
- A* 기반 최단 경로(또는 최적화된 경로)를 계산하여 `global_path` JSON을 출력
- MQTT를 통해 모듈 간 통신하여 실제 AGV 제어 파이프라인에 연결

## 아키텍처 개요

- AI Node (Python): 음성인식/텍스트 → items JSON 생성 → `agv/ai/items` 발행
- Planner Node (Python/C++): items → POI 매핑 → A* → `agv/planner/global_path` 발행
- Web UI / API (FastAPI): 사용자 입력(아이템 발행, 명령), 상태/지도 조회, telemetry 구독
- Drive_Control (Jetson): 모터 제어, 네비게이션, 비전(정렬/검출), 그리퍼 제어
- 통신: MQTT(JSON) 기반 토픽을 통해 데이터 교환

각 모듈은 독립 프로세스이며 필요에 따라 Docker로 배포 가능합니다.

## 폴더 구조 (요약)

```
AGV/
├─ README.md
├─ Web/
│  ├─ README.md
│  ├─ interfaces/ # 프로세스 간 인터페이스(고정 규약)
│  │  ├─ mqtt_topics.yaml
│  │  └─ schemas/
│  │     ├─ items.schema.json
│  │     └─ path.schema.json
│  ├─ config/ # 환경별 설정(dev/prod)
│  │  └─ dev/
│  │     ├─ mqtt.json
│  │     ├─ planner.json
│  │     └─ control.json
│  ├─ data/ # 코드와 분리된 데이터
│  │  ├─ poi/
│  │  │  └─ store_A_poi.json
│  │  └─ samples/
│  │     └─ items_example.json
│  ├─ cpp/ # C++ 노드(Planner / Control / Simulation)
│  │  ├─ CMakeLists.txt
│  │  ├─ include/
│  │  ├─ src/
│  │  └─ apps/
│  │     ├─ sim_main.cpp # 실물 없이 A* 검증
│  │     └─ planner_main.cpp # items → path
│  └─ python/
│     └─ ai_node/ # AI/음성 인식 노드
└─ Drive_Control/
  ├── main.py                 # 프로그램 진입점 (MQTT 이벤트 루프 실행)
  ├── config/                 # 설정 파일 (MQTT 주소, 모터 파라미터 등)
  │   └── settings.yaml
  ├── src/
  │   ├── __init__.py
  │   ├── communication/      # 통신 관련 모듈
  │   │   ├── __init__.py
  │   │   └── mqtt_client.py
  │   ├── motion/             # 이동 및 모터 제어
  │   │   ├── __init__.py
  │   │   ├── motor_control.py # 저수준 모터 드라이버 제어
  │   │   └── navigator.py     # 좌표 기반 이동 로직 (기존 move_align 일부)
  │   ├── vision/             # 카메라 및 이미지 처리
  │   │   ├── __init__.py
  │   │   ├── detector.py      # 객체 인식 (기존 detection_grasp 일부)
  │   │   └── aligner.py       # 빨간 점 기반 정렬 로직 (기존 move_align 일부)
  │   ├── manipulation/       # 그리퍼 및 잡기 동작
  │   │   ├── __init__.py
  │   │   └── grasper.py       # Grasping 로직 (기존 detection_grasp 일부)
  │   └── utils/              # 공통 유틸리티 (로깅, 시간 계산 등)
  │       └── logger.py
  └── requirements.txt

```

---

## 설계 원칙
1. **인터페이스 고정**  
   `interfaces/`의 토픽 및 JSON 구조는 프로젝트 전반의 계약서 역할
2. **알고리즘 분리**  
   A*, 경로 최적화 로직은 하드웨어/통신에 의존하지 않음
3. **환경 독립성**  
   실물/시뮬레이션 차이는 `config/`만으로 전환
4. **유지보수 용이성**  
   입력/출력 JSON 기반으로 재현 및 디버깅 가능

---

## 메시지 형식 예시

### items
```json
{
  "items": [
    {"name": "coke", "qty": 1},
    {"name": "ramen", "qty": 2}
  ],
  "timestamp_ms": 0
}
```

### global_path

```json
{
  "frame": "map",
  "waypoints": [
    {"x": 1.0, "y": 1.0},
    {"x": 1.2, "y": 1.0}
  ],
  "total_cost": 12.3,
  "created_ms": 0
}
```

## 실행 가이드 (요약)

1) MQTT 브로커 시작 (Docker Compose 권장):

```bash
docker-compose up -d
```

2) Web UI (개발):

```bash
cd Web/python/webapp
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

3) Drive_Control (Jetson) 개발용 실행:

```bash
cd Drive_Control
pip install -r requirements.txt
python main.py
```

4) AI 노드 테스트:

```bash
python Web/python/ai_node/main.py
```

5) C++ 플래너 빌드/테스트(선택): `Web/cpp`의 `CMakeLists.txt` 참고

## 의존성

- Python 3.11 권장
- 주요 패키지: `paho-mqtt`, `fastapi`, `uvicorn`, `pydantic`, `python-dotenv`, `opencv-python`, `tflite-runtime`(또는 TensorFlow Lite 런타임)

각 서브디렉토리(`Web/python`, `Drive_Control`)의 `requirements.txt`를 확인하세요.

## 하드웨어 & 인터페이스 (Drive_Control)

- 모터 제어: `motor_control` 인터페이스
- 카메라: USB 또는 CSI
- 거리 센서: UART/시리얼
- 서보/그리퍼: `SCSCtrl.TTLServo` 등 벤더 라이브러리

실물 연결 시에는 `localization_node` 및 `control_node`(또는 Drive_Control의 모듈)를 적절히 구성해야 합니다.

## 개발 및 테스트 권장 흐름

1. 시뮬레이션/유닛 테스트로 A* 및 planner 로직 검증 (`Web/cpp/sim_main.cpp`)
2. Planner End-to-End 테스트 (`Web/cpp/planner_main.cpp` 또는 Python planner)
3. MQTT 연결 및 메시지 포맷 검증
4. Drive_Control 통합 후 실제 제어 테스트

## 주의사항 / 누락된 컴포넌트

- `localization_node` 및 `control_node`는 레포지토리에 포함되어 있지 않으며, 실물 제어환경에서는 별도 모듈 또는 외부 서비스가 필요합니다.
- OpenAI 연동 기능은 `OPENAI_API_KEY` 설정이 필요할 수 있습니다.

## 기여 및 관리

- 버그 리포트나 기능 제안은 GitHub 이슈로 남겨주세요.
- 코드 스타일 및 PR 가이드는 별도 문서(없을 경우 이슈로 요청)를 통해 합의합니다.

---

필요하시면 이 파일을 영어 번역본으로 제공하거나, `docker-compose` 서비스 정의와 예제 환경 파일(`config/dev/*.json`)을 연결해 드릴게요.


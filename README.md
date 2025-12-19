# AGV Jetson Nano Project

Jetson Nano 기반 AGV(스마트 카트) 프로젝트입니다.  
---

## 프로젝트 목표
- 음성인식/AI 결과로 생성된 `items JSON` 입력
- POI(진열대 좌표) 매핑 및 방문 순서 결정
- A* 기반 최단 경로 계획
- `global_path JSON` 출력(MQTT 또는 파일)
- 실물 연결 시 Control/Localization 모듈만 교체하여 주행

---

## 아키텍처 개요 (멀티 프로세스)
- **AI Node (Python)**  
  음성 인식 및 AI 파싱 → `items JSON` 생성
- **Planner Node (C++)**  
  items → POI → A* → `global_path JSON`
- **Control Node (C++)** *(실물 AGV 연결 시)*  
  경로 추종(Pure Pursuit 등) 및 모터 제어
- **통신**  
  MQTT(JSON) 기반 프로세스 간 통신

각 프로세스는 독립적으로 실행/재시작 가능하도록 설계합니다.

---

## 폴더 구조
```
agv-jetson/
├─ README.md
├─ interfaces/ # 프로세스 간 인터페이스(고정 규약)
│ ├─ mqtt_topics.yaml
│ └─ schemas/
│ ├─ items.schema.json
│ └─ path.schema.json
├─ config/ # 환경별 설정(dev/prod)
│ └─ dev/
│ ├─ mqtt.json
│ ├─ planner.json
│ └─ control.json
├─ data/ # 코드와 분리된 데이터
│ ├─ poi/
│ │ └─ store_A_poi.json
│ └─ samples/
│ └─ items_example.json
├─ cpp/ # C++ 노드(Planner / Control / Simulation)
│ ├─ CMakeLists.txt
│ ├─ include/
│ ├─ src/
│ └─ apps/
│ ├─ sim_main.cpp # 실물 없이 A* 검증
│ └─ planner_main.cpp # items → path
└─ python/
└─ ai_node/ # AI/음성 인식 노드
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

## global_path

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

## 개발 및 테스트 흐름 (실물 없이)

1. sim_main으로 가짜 맵에서 A* 경로 검증
2. planner_main으로 items → path End-to-End 확인
3. MQTT 통신 연결
4. 실물 AGV 연결 후 Control/Localization 추가

## 음성 입력(휴대폰 웹) 옵션
휴대폰에서 웹으로 음성 인식(브라우저 SpeechRecognition) → 텍스트를 OpenAI로 `items` JSON 파싱 → MQTT로 발행하는 웹 UI를 제공합니다.

- 실행: `python/webapp/README.md`

## 실물 AGV 연결 시 변경 범위
- Control Node(경로 추종, 모터 제어) 추가/교체
- Localization 입력(오도메트리, IMU, 마커 등) 연결
- config/prod/ 환경 설정 적용
  → Planner 및 A* 알고리즘은 그대로 유지

## GitHub 관리 기준
- 포함: interfaces/, cpp/, python/, config/dev(샘플), data/samples
- 제외: 빌드 산출물, 로그, 비밀키(.env 등)

## Roadmap
- POI 후보 다중 지원 및 자동 선택
- 방문 순서 최적화(TSP 휴리스틱)
- 경로 스무딩 및 안정적 추종
- 장애물 회피 및 재탐색 로직 고도화

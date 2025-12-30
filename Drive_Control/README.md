# Drive_Control
<img width="33%" alt="d50f507339da4bfba9c3f5a078839e8bb7XP6h4sleVHU4g0-10" src="https://github.com/user-attachments/assets/9a342861-745e-47cb-b88d-131869cbfcfe" />
<img width="33%" alt="d50f507339da4bfba9c3f5a078839e8bb7XP6h4sleVHU4g0-9" src="https://github.com/user-attachments/assets/e98e02c8-df75-4dac-8019-246bca115c69" />
<img width="33%" alt="d50f507339da4bfba9c3f5a078839e8bb7XP6h4sleVHU4g0-11" src="https://github.com/user-attachments/assets/ce2177af-0d74-4618-925f-5426d1ff5231" />


Drive_Control 모듈의 README입니다. 이 폴더는 Jetson Nano 기반 AGV의 모션 제어, 비전, 그리퍼 조작 및 통신 관련 코드들을 포함합니다.

## 디렉터리 구조
```
AGVProject/
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
│   │   ├── detector.py      # 객체 검출 (model.tflite 사용 가능)
│   │   └── aligner.py       # 정렬 로직 (move_align 일부)
│   ├── manipulation/       # 그리퍼 및 잡기 동작
│   │   ├── __init__.py
│   │   └── grasper.py       # Grasping 로직
│   └── utils/              # 공통 유틸리티 (로깅, 시간 계산 등)
│       └── logger.py
└── requirements.txt
```

## 구성 요소

- **앱 엔트리포인트**: `main.py` — 전체 서브시스템 초기화 및 실행 흐름 제어
- **모션(Mobility)**: `motion`
    - `navigator.py` (`Navigator`): 경로 추종, 회전/직진 제어, 위치 보정, 경로상 그랩 트리거
    - `motor_control.py`: 모터 제어 API (전진/후진/회전/속도)
- **조작(Manipulation)**: `grasper.py` (`Grasper`)
    - 거리 센서(시리얼) 스레드로 거리 업데이트, 서보 포즈 제어, 역기구학 계산 및 그리퍼 작동
- **비전(Vision)**: `vision`
    - `aligner.py` (`Aligner`): 빨간 마커 기반 정렬 및 서보 연동 정렬
    - `detector.py`: 객체 검출 (TensorFlow Lite 모델 사용 가능)
- **통신(Integration)**: `mqtt_client.py` — 원격 명령/상태 전송(옵션)
- **유틸리티**: `logger.py` — 로깅; `config/settings.yaml` — 런타임 설정
- **모델/리소스**: `model.tflite` — TFLite 기반 객체 검출 모델

## 주요 데이터 흐름 & 상호작용

1. 외부 명령/스케줄 → (`mqtt_client` 또는 `main.py`) → `Navigator.execute_path(path_data)` 호출
2. `Navigator`의 웨이포인트 처리:
     - 목표 각도 계산 → `motor_control.turn_to_angle()` 호출
     - 직진 이동 → `motor_control.forward()` (또는 `move_straight`)
     - `camera_instance`가 존재하면 `aligner.align_to_red_marker()`로 미세 정렬
     - 도달 위치가 `grasp_table`이고 `runtime_order`에 포함되면 `grasper.execute_grasp()` 실행
3. `Grasper.execute_grasp()` (옵션): `aligner.align_to_object_with_servo()` → 거리 센서(`serial`)로 거리 읽기 → IK 계산 → `SCSCtrl.TTLServo`로 서보 제어
4. 비전 파이프라인: 카메라 프레임 → `detector.detect(image)` → `aligner`/`grasper` 사용

## 사용 기술 / 라이브러리

- Python
- OpenCV (`opencv-python`), NumPy
- TensorFlow Lite 런타임 또는 `tflite-runtime` (모델: `model.tflite`)
- Serial 통신: `pyserial`
- 서보 제어: `SCSCtrl.TTLServo` (벤더 라이브러리)
- MQTT: `paho-mqtt` (선택)

## 하드웨어 및 인터페이스

- 모터 드라이버: `motor_control` 인터페이스로 제어 신호 전송
- 카메라: USB 또는 CSI (V4L2)
- 거리 센서: UART/시리얼 (예: UART-to-USB)
- 서보/그리퍼: `SCSCtrl` TTL 서보 제어
- 네트워크: MQTT 브로커(원격 제어/모니터링, 선택)

## 바로가기(개발/테스트)

- 의존성 설치: `pip install -r requirements.txt`

```
pip install --extra-index-url https://google-coral.github.io/py-repo/ tflite-runtime
```

- 실행: `python main.py` (환경 설정에 따라 MQTT 브로커 주소 등 변경 필요)

## 참고

- 주요 동작은 `src/` 내부의 모듈들(`navigator`, `motor_control`, `aligner`, `grasper`)에서 구현됩니다.


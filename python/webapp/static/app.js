import {
  computed,
  createApp,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
} from "https://unpkg.com/vue@3/dist/vue.esm-browser.js";

const POLL_MS = 2000;
const COMMAND_KEYWORDS = {
  go: ["출발", "가자", "이동", "앞으로", "go", "start", "run"],
  stop: ["멈춰", "멈춤", "정지", "스탑", "stop", "그만", "halt"],
};
const ROTATE_MAP = true; // rotate map 90deg to display horizontally

const template = `
  <div class="container">
    <header class="header">
      <div>
        <p class="eyebrow">AGV Control + Voice</p>
        <h1>AGV Command Center</h1>
        <p class="muted">지도에서 위치 확인, Go/Stop, 음성으로 경로 생성까지 한 번에</p>
      </div>
      <div class="status-row">
        <span class="pill" :class="telemetry.connected ? 'pill-ok' : 'pill-warn'">
          <span class="dot"></span>{{ telemetry.connected ? 'MQTT 연결됨' : 'MQTT 대기' }}
        </span>
        <span class="pill pill-ghost" v-if="telemetry.last_error">⚠️ {{ telemetry.last_error }}</span>
        <span class="pill" :class="speechSupported ? 'pill-ok' : 'pill-warn'">
          🎤 {{ speechSupported ? '음성 인식 가능' : '음성 인식 불가' }}
        </span>
      </div>
    </header>

    <section class="card map-card wide-card">
      <div class="card-head">
        <div>
          <p class="label">MAP</p>
          <h2>AGV 위치</h2>
        </div>

      </div>
      <div class="canvas-wrap">
        <canvas ref="mapCanvas"></canvas>
        <div v-if="mapLoading" class="overlay">지도 불러오는 중…</div>
        <div v-else-if="!map" class="overlay">지도 파일을 찾을 수 없습니다.</div>
      </div>
      <div class="legend">
        <div class="legend-item"><span class="legend-box obstacle"></span> 장애물</div>
        <div class="legend-item"><span class="legend-box poi"></span> POI</div>
        <div class="legend-item"><span class="legend-box agv"></span> AGV</div>
        <div class="legend-item"><span class="legend-box path"></span> 예상 경로</div>
        <button class="btn ghost small" @click="clearPath" :disabled="clearingPath">경로 초기화</button>
      </div>
    </section>

    <section class="card action-card wide-card">
      <div class="action-grid">
        <div class="panel">
          <div class="card-head">
            <div>
              <p class="label">CONTROL</p>
              <h2>Go / Stop</h2>
              <p class="muted small">버튼/음성으로 MQTT에 명령을 발행합니다.</p>
            </div>
          </div>
          <div class="button-row">
            <button class="btn go" @click="sendGo" :disabled="commandBusy">Go</button>
            <button class="btn stop" @click="sendStop" :disabled="commandBusy">Stop</button>
            <button class="btn ghost" @click="refreshState">상태 새로고침</button>
          </div>

          <div class="voice-block">
            <div class="voice-row">
              <div class="button-row">
                <button class="btn" @click="startListening" :disabled="!speechSupported || listening">🎤 음성 시작</button>
                <button class="btn ghost" @click="stopListening" :disabled="!listening">중지</button>
              </div>
              <label class="select-field">
                <span>언어</span>
                <select v-model="lang">
                  <option value="ko-KR">ko-KR</option>
                  <option value="en-US">en-US</option>
                </select>
              </label>
            </div>
            <div class="transcript">
              <p class="label">인식 결과</p>
              <p class="transcript-text">{{ transcript || '대기 중' }}</p>
              <p v-if="interim" class="muted small">임시: {{ interim }}</p>
            </div>
            <p class="muted small">"출발/가자/go" → Go, "멈춰/정지/stop" → Stop. 그 외 문장은 items로 간주해 경로를 요청합니다.</p>
          </div>

          <div class="alerts">
            <p v-if="info" class="info">{{ info }}</p>
            <p v-if="error" class="error">{{ error }}</p>
          </div>

          <div class="last-command" v-if="lastCommand">
            <p class="label">최근 명령</p>
            <p>{{ lastCommand.action.toUpperCase() }} · {{ timeAgo(lastCommand.at) }} 전 · {{ lastCommand.source }}</p>
            <p v-if="lastCommand.utterance" class="muted small">"{{ lastCommand.utterance }}"</p>
          </div>
        </div>

        <div class="panel">
          <div class="card-head">
            <div>
              <p class="label">VOICE TO PATH</p>
              <h2>음성/텍스트로 경로 생성</h2>
              <p class="muted small">"콜라 두 개 찾아줘" 같은 문장을 인식해 items → planner → 예상 경로를 그립니다.</p>
            </div>
          </div>

          <div class="plan-grid">
            <div class="plan-left">
              <label class="select-field full">
                <span>주문/물품 문장</span>
                <textarea v-model="itemsText" rows="3" placeholder="예: 립스틱 2개, 앰플 1개 가져와"></textarea>
              </label>
              <div class="button-row">
                <button class="btn go" @click="requestPathFromText" :disabled="planning">AI로 경로 요청</button>
                <button class="btn ghost" @click="previewItems" :disabled="planning">AI로 items 미리보기</button>
                <button class="btn ghost" @click="clearItems" :disabled="planning">초기화</button>
              </div>
              <p class="muted small">AI 파싱에는 서버에 OPENAI_API_KEY가 필요합니다.</p>
            </div>
            <div class="plan-right">
              <p class="label">items JSON</p>
              <pre class="code small-pre">{{ itemsJson }}</pre>
            </div>
          </div>

          <div class="last-command" v-if="pathMeta">
            <p class="label">최근 경로</p>
            <p>{{ pathSummary }} <span v-if="pathAgeText">· {{ pathAgeText }} 전</span></p>
            <p class="muted small">waypoints: {{ (pathMeta.waypoints || []).length }}</p>
          </div>
        </div>
      </div>
    </section>
  </div>
`;

createApp({
  template,
  setup() {
    const mapCanvas = ref(null);
    const map = ref(null);
    const pose = ref(null);
    const status = ref("");
    const pathMeta = ref(null);
    const itemsText = ref("");
    const itemsPreview = ref(null);
    const telemetry = reactive({
      connected: false,
      last_error: "",
      pose_topic: "agv/state/pose",
      command_topic: "agv/web/command",
      path_topic: "agv/planner/global_path",
      last_seen_ms: null,
    });

    const mapLoading = ref(false);
    const commandBusy = ref(false);
    const planning = ref(false);
    const clearingPath = ref(false);
    const info = ref("");
    const error = ref("");
    const speechSupported = ref(false);
    const listening = ref(false);
    const lang = ref("ko-KR");
    const transcript = ref("");
    const interim = ref("");
    const lastCommand = ref(null);
    const mqttHost = ref("localhost");
    const mqttPort = ref(1883);
    const pathProgress = ref(1);
    let pathAnimId = null;
    let pathAnimLoopId = null;
    let lastPathStamp = 0;
    let targetPoiIds = [];

    let recognition = null;
    let pollTimer = null;

    const statusText = computed(() => status.value || "대기");
    const poseText = computed(() => {
      if (!pose.value || pose.value.x === undefined || pose.value.y === undefined) return "N/A";
      const x = Number(pose.value.x).toFixed(2);
      const y = Number(pose.value.y).toFixed(2);
      const theta =
        pose.value.theta !== undefined && pose.value.theta !== null
          ? ` | θ ${Number(pose.value.theta).toFixed(2)}`
          : "";
      return `x ${x}, y ${y}${theta}`;
    });
    const lastSeenText = computed(() => {
      if (!telemetry.last_seen_ms) return "N/A";
      return timeAgo(telemetry.last_seen_ms) + " 전";
    });
    const commandTopic = computed(() => telemetry.command_topic || "agv/web/command");
    const poseTopic = computed(() => telemetry.pose_topic || "agv/state/pose");
    const pathTopic = computed(() => telemetry.path_topic || "agv/planner/global_path");
    const itemsJson = computed(() => {
      if (!itemsPreview.value) return "{}";
      return JSON.stringify(itemsPreview.value, null, 2);
    });
    const pathSummary = computed(() => {
      if (!pathMeta.value || !Array.isArray(pathMeta.value.waypoints)) return "없음";
      const n = pathMeta.value.waypoints.length;
      const cost =
        pathMeta.value.total_cost !== undefined
          ? ` · cost ${Number(pathMeta.value.total_cost).toFixed(2)}`
          : "";
      return `${n} points${cost}`;
    });
    const pathAgeText = computed(() => {
      if (!pathMeta.value || !pathMeta.value.created_ms) return "";
      return timeAgo(pathMeta.value.created_ms);
    });

    function timeAgo(ts) {
      if (!ts) return "-";
      const diff = Date.now() - ts;
      if (diff < 1000) return "방금";
      const sec = Math.floor(diff / 1000);
      if (sec < 60) return `${sec}초`;
      const min = Math.floor(sec / 60);
      if (min < 60) return `${min}분`;
      const hr = Math.floor(min / 60);
      if (hr < 24) return `${hr}시간`;
      return `${Math.floor(hr / 24)}일`;
    }

    function detectAction(text) {
      if (!text) return null;
      const lower = text.toLowerCase();
      for (const k of COMMAND_KEYWORDS.go) {
        if (lower.includes(k.toLowerCase())) return "go";
      }
      for (const k of COMMAND_KEYWORDS.stop) {
        if (lower.includes(k.toLowerCase())) return "stop";
      }
      return null;
    }

    async function fetchMap() {
      mapLoading.value = true;
      try {
        const res = await fetch("/api/map");
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        map.value = data;
        error.value = "";
        draw();
      } catch (e) {
        error.value = `지도 로드 실패: ${e.message}`;
      } finally {
        mapLoading.value = false;
      }
    }

    async function fetchConfig() {
      try {
        const res = await fetch("/api/config");
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        mqttHost.value = data.broker || mqttHost.value;
        mqttPort.value = data.port || mqttPort.value;
      } catch (_) {
        // optional
      }
    }

    async function fetchState() {
      try {
        const res = await fetch("/api/state");
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        telemetry.connected = Boolean(data.connected);
        telemetry.last_error = data.last_error || "";
        telemetry.pose_topic = data.pose_topic || telemetry.pose_topic;
        telemetry.command_topic = data.command_topic || telemetry.command_topic;
        telemetry.path_topic = data.path_topic || telemetry.path_topic;
        telemetry.last_seen_ms = data.last_seen_ms || data.updated_ms || telemetry.last_seen_ms;
        pose.value = data.pose || null;
        status.value = data.status || "";
        if (data.path) {
          const stamp = data.path.created_ms || Date.now();
          if (!lastPathStamp || stamp !== lastPathStamp) {
            lastPathStamp = stamp;
            pathMeta.value = data.path;
            const names = [];
            if (Array.isArray(pathMeta.value.waypoints)) {
              // use itemsPreview if present
              if (itemsPreview.value && Array.isArray(itemsPreview.value.items)) {
                itemsPreview.value.items.forEach((it) => {
                  if (it.name) names.push(it.name);
                });
              }
            }
            targetPoiIds = names;
            planning.value = false;
            pathProgress.value = 0;
            startPathAnimation();
            startPathLoop();
          } else if (!pathAnimLoopId) {
            startPathLoop();
          }
        }
        draw();
      } catch (e) {
        error.value = `상태 조회 실패: ${e.message}`;
      }
    }

    async function sendCommand(action, source = "ui", utterance = "") {
      commandBusy.value = true;
      info.value = "";
      error.value = "";
      try {
        const res = await fetch("/api/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action, source, utterance }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(data.detail || `HTTP ${res.status}`);
        }
        lastCommand.value = { action, source, utterance, at: Date.now() };
        info.value = action === "go" ? "Go 명령을 전송했습니다." : "Stop 명령을 전송했습니다.";
      } catch (e) {
        error.value = `명령 전송 실패: ${e.message}`;
      } finally {
        commandBusy.value = false;
      }
    }

    const sendGo = () => sendCommand("go", "button");
    const sendStop = () => sendCommand("stop", "button");
    const refreshState = () => {
      fetchState();
      info.value = "상태 갱신";
    };

    function initSpeech() {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        info.value = "이 브라우저는 음성 인식을 지원하지 않습니다.";
        speechSupported.value = false;
        return;
      }
      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      speechSupported.value = true;

      recognition.onstart = () => {
        listening.value = true;
        interim.value = "";
        info.value = "듣는 중…";
      };
      recognition.onerror = (e) => {
        error.value = `음성인식 오류: ${e.error || "unknown"}`;
      };
      recognition.onend = () => {
        listening.value = false;
      };
      recognition.onresult = (event) => {
        let finalText = "";
        let interimText = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          const transcriptStr = (result[0] && result[0].transcript ? result[0].transcript : "").trim();
          if (!transcriptStr) continue;
          if (result.isFinal) {
            finalText += transcriptStr + " ";
          } else {
            interimText += transcriptStr + " ";
          }
        }
        interim.value = interimText.trim();
        if (finalText.trim()) {
          transcript.value = finalText.trim();
          const action = detectAction(finalText);
          if (action) {
            sendCommand(action, "voice", finalText.trim());
          } else {
            itemsText.value = finalText.trim();
            requestPathFromText("voice");
          }
        }
      };
    }

    const startListening = () => {
      if (!recognition) initSpeech();
      if (!recognition) return;
      recognition.lang = lang.value;
      recognition.start();
    };

    const stopListening = () => {
      if (recognition) recognition.stop();
    };

    async function clearPath() {
      clearingPath.value = true;
      try {
        await fetch("/api/clear_path", { method: "POST" });
        pathMeta.value = null;
        stopPathAnimation();
        stopPathLoop();
        info.value = "경로를 지웠습니다.";
        draw();
      } catch (_) {
        // optional UI feedback
      } finally {
        clearingPath.value = false;
      }
    }

    async function previewItems() {
      const text = itemsText.value.trim();
      if (!text) {
        error.value = "문장을 입력하세요.";
        return;
      }
      info.value = "AI로 items 파싱 중…";
      error.value = "";
      planning.value = true;
      try {
        const res = await fetch("/api/parse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        itemsPreview.value = data;
        info.value = "items 미리보기 완료";
      } catch (e) {
        error.value = `파싱 실패: ${e.message}`;
      } finally {
        planning.value = false;
      }
    }

    async function requestPathFromText(source = "ui") {
      const text = itemsText.value.trim();
      if (!text) {
        error.value = "문장을 입력하거나 음성으로 말해주세요.";
        return;
      }
      // Clear existing path while waiting for planner to publish a new one.
      pathMeta.value = null;
      pathProgress.value = 0;
      draw();
      info.value = "items 발행 → planner 경로 대기 중…";
      error.value = "";
      planning.value = true;
      try {
        const res = await fetch("/api/publish", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        if (data.items) itemsPreview.value = data.items;
        lastCommand.value = { action: "items", source, utterance: text, at: Date.now() };
        info.value = "발행 완료. planner가 global_path를 보내면 지도에 표시됩니다.";
      } catch (e) {
        error.value = `경로 요청 실패: ${e.message}`;
        planning.value = false;
      }
    }

    function clearItems() {
      itemsText.value = "";
      itemsPreview.value = null;
      info.value = "";
      error.value = "";
    }

    function startPathAnimation() {
      if (pathAnimId) cancelAnimationFrame(pathAnimId);
      const duration = 1400;
      const startTs = performance.now();
      const step = (ts) => {
        const t = Math.min(1, (ts - startTs) / duration);
        pathProgress.value = t;
        draw();
        if (t < 1) pathAnimId = requestAnimationFrame(step);
      };
      pathAnimId = requestAnimationFrame(step);
    }

    function stopPathAnimation() {
      if (pathAnimId) cancelAnimationFrame(pathAnimId);
      pathAnimId = null;
    }

    function startPathLoop() {
      stopPathLoop();
      // kick off immediately
      startPathAnimation();
      pathAnimLoopId = setInterval(() => {
        if (!pathMeta.value) return;
        pathProgress.value = 0;
        startPathAnimation();
      }, 5000);
    }

    function stopPathLoop() {
      if (pathAnimLoopId) clearInterval(pathAnimLoopId);
      pathAnimLoopId = null;
    }

    function draw() {
      const canvas = mapCanvas.value;
      if (!canvas || !map.value) return;
      const ctx = canvas.getContext("2d");
      const dpr = window.devicePixelRatio || 1;
      const viewW = canvas.clientWidth || 720;
      const viewH = canvas.clientHeight || 420;
      canvas.width = viewW * dpr;
      canvas.height = viewH * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, viewW, viewH);

      const padding = 20;
      const mapWidthRaw = map.value.width || 20;
      const mapHeightRaw = map.value.height || 20;
      const mapWidth = ROTATE_MAP ? mapHeightRaw : mapWidthRaw;
      const mapHeight = ROTATE_MAP ? mapWidthRaw : mapHeightRaw;
      const scale = Math.min((viewW - padding * 2) / mapWidth, (viewH - padding * 2) / mapHeight);
      const offsetX = (viewW - mapWidth * scale) / 2;
      const offsetY = (viewH - mapHeight * scale) / 2;

      const rotCell = (cx, cy) => {
        if (!ROTATE_MAP) return { rx: cx, ry: cy };
        return { rx: cy, ry: mapWidthRaw - cx - 1 };
      };

      const poiMap = {};
      if (Array.isArray(map.value.poi)) {
        for (const p of map.value.poi) {
          if (!p.id) continue;
          let cx = null;
          let cy = null;
          if (p.cell) {
            cx = Number(p.cell.x);
            cy = Number(p.cell.y);
          } else if (p.x !== undefined && p.y !== undefined && map.value.resolution) {
            const origin = map.value.origin || { x: 0, y: 0 };
            cx = (Number(p.x) - origin.x) / map.value.resolution;
            cy = (Number(p.y) - origin.y) / map.value.resolution;
          }
          if (cx === null || cy === null) continue;
          poiMap[p.id] = { cx, cy };
        }
      }

      ctx.fillStyle = "rgba(255,255,255,0.02)";
      ctx.fillRect(offsetX, offsetY, mapWidth * scale, mapHeight * scale);

      // grid lines
      ctx.strokeStyle = "rgba(255,255,255,0.04)";
      ctx.lineWidth = 1;
      for (let x = 0; x <= mapWidth; x++) {
        const px = offsetX + x * scale;
        ctx.beginPath();
        ctx.moveTo(px, offsetY);
        ctx.lineTo(px, offsetY + mapHeight * scale);
        ctx.stroke();
      }
      for (let y = 0; y <= mapHeight; y++) {
        const py = offsetY + y * scale;
        ctx.beginPath();
        ctx.moveTo(offsetX, py);
        ctx.lineTo(offsetX + mapWidth * scale, py);
        ctx.stroke();
      }

      // obstacles
      if (Array.isArray(map.value.obstacles)) {
        ctx.fillStyle = "rgba(255,74,110,0.8)";
        for (const obs of map.value.obstacles) {
          const cx = Number(obs.x ?? obs[0]);
          const cy = Number(obs.y ?? obs[1]);
          const { rx, ry } = rotCell(cx, cy);
          const px = offsetX + rx * scale;
          const py = offsetY + (mapHeight - ry - 1) * scale;
          ctx.fillRect(px, py, scale, scale);
        }
      }

      // POIs
      if (Array.isArray(map.value.poi)) {
        ctx.fillStyle = "#4ef3c9";
        for (const p of map.value.poi) {
          const pos = poiMap[p.id];
          if (!pos) continue;
          const { rx, ry } = rotCell(pos.cx, pos.cy);
          const px = offsetX + rx * scale + scale / 2;
          const py = offsetY + (mapHeight - ry - 1) * scale + scale / 2;
          const isTarget = targetPoiIds.includes(p.id);
          if (isTarget) {
            ctx.fillStyle = "rgba(255,255,255,0.2)";
            ctx.beginPath();
            ctx.arc(px, py, Math.max(12, scale * 0.6), 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = "rgba(102,255,226,0.9)";
            ctx.beginPath();
            ctx.arc(px, py, Math.max(5, scale * 0.28), 0, Math.PI * 2);
            ctx.fill();
          } else {
            ctx.fillStyle = "#4ef3c9";
            ctx.beginPath();
            ctx.arc(px, py, Math.max(3, scale * 0.2), 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      // Path
      if (pathMeta.value && Array.isArray(pathMeta.value.waypoints) && map.value.resolution) {
        const origin = map.value.origin || { x: 0, y: 0 };
        const res = map.value.resolution || 1;
        const pts = pathMeta.value.waypoints
          .map((w) => {
            const cx = (Number(w.x) - origin.x) / res;
            const cy = (Number(w.y) - origin.y) / res;
            const { rx, ry } = rotCell(cx, cy);
            return { cx: rx, cy: ry };
          })
          .filter((p) => Number.isFinite(p.cx) && Number.isFinite(p.cy));
        if (pts.length >= 2) {
          // apply progress cut
          const clipped = [];
          let remaining = pathProgress.value * (pts.length - 1);
          for (let i = 0; i < pts.length - 1; i++) {
            const start = pts[i];
            const end = pts[i + 1];
            if (remaining >= 1) {
              clipped.push(start);
              if (i === pts.length - 2) clipped.push(end);
              remaining -= 1;
            } else {
              const t = Math.max(0, remaining);
              clipped.push(start);
              clipped.push({
                cx: start.cx + (end.cx - start.cx) * t,
                cy: start.cy + (end.cy - start.cy) * t,
              });
              break;
            }
          }
          const drawPts = clipped.length >= 2 ? clipped : pts;
          const baseWidth = Math.max(3, scale * 0.2);
          const nSeg = drawPts.length - 1;
          for (let i = 0; i < nSeg; i++) {
            const start = drawPts[i];
            const end = drawPts[i + 1];
            const px1 = offsetX + start.cx * scale + scale / 2;
            const py1 = offsetY + (mapHeight - start.cy - 1) * scale + scale / 2;
            const px2 = offsetX + end.cx * scale + scale / 2;
            const py2 = offsetY + (mapHeight - end.cy - 1) * scale + scale / 2;
            const t = nSeg > 0 ? i / nSeg : 1;
            const glowAlpha = 0.08 + 0.8 * t;
            const lineAlpha = 0.2 + 0.8 * t;

            // gradient along the segment
            const grad = ctx.createLinearGradient(px1, py1, px2, py2);
            grad.addColorStop(0, `rgba(102,255,226,${Math.max(0.05, glowAlpha - 0.1)})`);
            grad.addColorStop(1, `rgba(255,255,255,${Math.min(1, lineAlpha)})`);

            // glow stroke
            ctx.strokeStyle = grad;
            ctx.lineWidth = baseWidth + 4;
            ctx.lineJoin = "round";
            ctx.shadowColor = `rgba(102,255,226,${glowAlpha})`;
            ctx.shadowBlur = 14;
            ctx.beginPath();
            ctx.moveTo(px1, py1);
            ctx.lineTo(px2, py2);
            ctx.stroke();

            // main stroke
            ctx.shadowBlur = 0;
            ctx.strokeStyle = grad;
            ctx.lineWidth = baseWidth;
            ctx.beginPath();
            ctx.moveTo(px1, py1);
            ctx.lineTo(px2, py2);
            ctx.stroke();

            // waypoint dot at end
            ctx.fillStyle = `rgba(255,255,255,${Math.min(1, lineAlpha + 0.2)})`;
            ctx.beginPath();
            ctx.arc(px2, py2, Math.max(3, baseWidth * 0.7), 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      // AGV pose
      if (pose.value && pose.value.x !== undefined && pose.value.y !== undefined) {
        const origin = map.value.origin || { x: 0, y: 0 };
        const res = map.value.resolution || 1;
        const cx = (Number(pose.value.x) - origin.x) / res;
        const cy = (Number(pose.value.y) - origin.y) / res;
        const { rx, ry } = rotCell(cx, cy);
        const px = offsetX + rx * scale + scale / 2;
        const py = offsetY + (mapHeight - ry - 1) * scale + scale / 2;
        ctx.fillStyle = "#7ea1ff";
        ctx.strokeStyle = "#e8ecff";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(px, py, Math.max(6, scale * 0.35), 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        if (pose.value.theta !== undefined && pose.value.theta !== null) {
          const len = Math.max(10, scale * 0.8);
          const angle = Number(pose.value.theta);
          const ax = px + len * Math.cos(angle);
          const ay = py - len * Math.sin(angle);
          ctx.strokeStyle = "#e8ecff";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(px, py);
          ctx.lineTo(ax, ay);
          ctx.stroke();
        }
      }
    }

    onMounted(() => {
      fetchMap();
      fetchConfig();
      fetchState();
      pollTimer = setInterval(fetchState, POLL_MS);
      initSpeech();
      window.addEventListener("resize", draw);
    });

    onBeforeUnmount(() => {
      if (pollTimer) clearInterval(pollTimer);
      window.removeEventListener("resize", draw);
      if (recognition) recognition.stop();
    });

    return {
      mapCanvas,
      map,
      mapLoading,
      telemetry,
      commandBusy,
      planning,
      info,
      error,
      speechSupported,
      listening,
      lang,
      transcript,
      interim,
      lastCommand,
      itemsText,
      itemsJson,
      pathMeta,
      mqttHost,
      mqttPort,
      statusText,
      poseText,
      lastSeenText,
      commandTopic,
      poseTopic,
      pathTopic,
      startListening,
      stopListening,
      sendGo,
      sendStop,
      refreshState,
      clearPath,
      previewItems,
      requestPathFromText,
      clearItems,
      timeAgo,
      pathSummary,
      pathAgeText,
    };
  },
}).mount("#app");

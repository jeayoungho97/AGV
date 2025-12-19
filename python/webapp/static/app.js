const $ = (id) => document.getElementById(id);

function setStatus(msg) {
  $("status").textContent = msg || "";
}

function pretty(obj) {
  return JSON.stringify(obj, null, 2);
}

let recognition = null;
let listening = false;

function createRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return null;
  const r = new SpeechRecognition();
  r.continuous = true;
  r.interimResults = true;
  r.maxAlternatives = 1;
  return r;
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

function setItems(obj) {
  $("items").textContent = pretty(obj);
}

function enableButtons() {
  $("btnStart").disabled = listening;
  $("btnStop").disabled = !listening;
}

function appendFinalText(text) {
  const current = $("text").value.trim();
  $("text").value = current ? `${current} ${text}`.trim() : text;
}

function startListening() {
  if (!recognition) {
    setStatus("이 브라우저는 SpeechRecognition을 지원하지 않습니다. 텍스트를 직접 입력하세요.");
    return;
  }

  recognition.lang = $("lang").value;
  recognition.onstart = () => {
    listening = true;
    enableButtons();
    setStatus("듣는 중…");
  };

  recognition.onerror = (e) => {
    setStatus(`음성인식 오류: ${e.error || "unknown"}`);
  };

  recognition.onend = () => {
    listening = false;
    enableButtons();
    setStatus("중지됨");
  };

  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      const transcript = (result[0] && result[0].transcript ? result[0].transcript : "").trim();
      if (!transcript) continue;
      if (result.isFinal) appendFinalText(transcript);
      else interim += transcript + " ";
    }
    if (interim.trim()) setStatus(`듣는 중… (임시) ${interim.trim()}`);
    else setStatus("듣는 중…");
  };

  recognition.start();
}

function stopListening() {
  if (recognition) recognition.stop();
}

async function parseItems() {
  const text = $("text").value.trim();
  if (!text) return setStatus("텍스트가 비어있습니다.");
  setStatus("AI 파싱 중…");
  try {
    const items = await apiPost("/api/parse", { text });
    setItems(items);
    setStatus("완료");
  } catch (e) {
    setStatus(`실패: ${e.message}`);
  }
}

async function publishItems() {
  const text = $("text").value.trim();
  let items = {};
  try {
    items = JSON.parse($("items").textContent || "{}");
  } catch (_) {
    items = {};
  }

  setStatus("발행 중…");
  try {
    const body = items.items ? { items } : { text };
    const res = await apiPost("/api/publish", body);
    setItems(res.items || items);
    setStatus("발행 완료");
  } catch (e) {
    setStatus(`실패: ${e.message}`);
  }
}

function clearAll() {
  $("text").value = "";
  setItems({});
  setStatus("");
}

recognition = createRecognition();
if (!recognition) setStatus("SpeechRecognition 미지원 브라우저입니다. 텍스트 입력 후 발행하세요.");

$("btnStart").addEventListener("click", startListening);
$("btnStop").addEventListener("click", stopListening);
$("btnClear").addEventListener("click", clearAll);
$("btnParse").addEventListener("click", parseItems);
$("btnPublish").addEventListener("click", publishItems);

enableButtons();


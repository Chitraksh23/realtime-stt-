/* ---------- helpers ---------- */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.status === 204 ? null : res.json();
}

/* ---------- health badge ---------- */
async function checkHealth() {
  const badge = $("engine-badge");
  try {
    const h = await api("/api/health");
    if (h.model_ready) { badge.textContent = `${h.engine}${h.model ? " · " + h.model : ""} ready`; badge.className = "badge ok"; }
    else { badge.textContent = "loading speech model…"; badge.className = "badge warn"; setTimeout(checkHealth, 2000); }
  } catch { badge.textContent = "server unreachable"; badge.className = "badge warn"; }
}

/* ---------- live transcription ---------- */
let ws = null, audioCtx = null, stream = null, node = null, recording = false;
let finals = [], partial = "";

function renderTranscript() {
  const el = $("transcript");
  if (!finals.length && !partial) { el.innerHTML = '<span class="placeholder">Listening… start speaking.</span>'; return; }
  el.innerHTML = esc(finals.join(" ")) + (partial ? ` <span class="partial">${esc(partial)}</span>` : "");
}

function setStatus(t) { $("status").textContent = t; }

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) { alert("Microphone access needs HTTPS (or localhost) and a modern browser."); return; }
  finals = []; partial = ""; renderTranscript();
  $("record").disabled = true; setStatus("Requesting microphone…");

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (e) { setStatus("Microphone permission denied"); $("record").disabled = false; return; }

  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/transcribe`);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => ws.send(JSON.stringify({ type: "start", language: $("language").value, title: $("title").value }));
  ws.onmessage = (e) => handleServerMessage(JSON.parse(e.data));
  ws.onerror = () => setStatus("Connection error");
  ws.onclose = () => { if (recording) stopRecording(false); };
}

async function beginAudio() {
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  await audioCtx.audioWorklet.addModule("/static/worklet.js");
  const src = audioCtx.createMediaStreamSource(stream);
  node = new AudioWorkletNode(audioCtx, "pcm-processor");
  node.port.onmessage = (e) => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(e.data);
    // simple level meter
    const s = new Int16Array(e.data); let sum = 0;
    for (let i = 0; i < s.length; i += 8) sum += (s[i] / 32768) ** 2;
    $("level-bar").style.width = Math.min(100, Math.sqrt(sum / (s.length / 8)) * 400) + "%";
  };
  src.connect(node); // worklet outputs nothing, so no need to connect to destination (avoids echo)
  recording = true;
  const btn = $("record");
  btn.textContent = "■ Stop & save"; btn.classList.add("recording"); btn.disabled = false;
  setStatus("● Listening…"); renderTranscript();
}

function handleServerMessage(m) {
  switch (m.type) {
    case "loading": setStatus(m.message); break;
    case "ready": beginAudio().catch((e) => { setStatus("Audio error: " + e.message); stopRecording(false); }); break;
    case "partial": partial = m.text; renderTranscript(); break;
    case "final": finals.push(m.text); partial = ""; renderTranscript(); break;
    case "saved": setStatus("✔ Saved to history"); loadList(); break;
    case "empty": setStatus(m.message); break;
    case "error": setStatus("Error: " + m.message); break;
  }
}

function stopRecording(sendStop = true) {
  if (sendStop && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "stop" }));
    setStatus("Finishing up…");
  }
  recording = false;
  node?.disconnect(); node = null;
  audioCtx?.close(); audioCtx = null;
  stream?.getTracks().forEach((t) => t.stop()); stream = null;
  $("level-bar").style.width = "0";
  const btn = $("record");
  btn.textContent = "● Start recording"; btn.classList.remove("recording"); btn.disabled = false;
}

$("record").addEventListener("click", () => (recording ? stopRecording(true) : startRecording()));

/* ---------- history dashboard (CRUD) ---------- */
let offset = 0; const LIMIT = 10; let total = 0; let searchTimer = null;

async function loadList() {
  const q = encodeURIComponent($("search").value.trim());
  const data = await api(`/api/transcriptions?limit=${LIMIT}&offset=${offset}&q=${q}`);
  total = data.total;
  $("count").textContent = `${total} transcription${total === 1 ? "" : "s"}`;
  $("list").innerHTML = data.items.length
    ? data.items.map(itemHtml).join("")
    : '<p class="muted">Nothing here yet. Record something or create a note.</p>';
  const pages = Math.max(1, Math.ceil(total / LIMIT));
  $("page-info").textContent = `Page ${Math.floor(offset / LIMIT) + 1} / ${pages}`;
  $("prev").disabled = offset === 0;
  $("next").disabled = offset + LIMIT >= total;
}

function itemHtml(t) {
  const d = new Date(t.created_at).toLocaleString();
  const dur = t.duration_seconds ? ` · ${t.duration_seconds.toFixed(1)}s` : "";
  return `<article class="item" data-id="${t.id}">
    <h4>${esc(t.title)}</h4>
    <div class="meta"><span class="tag">${esc(t.source)}</span>${t.language ? `<span class="tag">${esc(t.language)}</span>` : ""}${d}${dur}</div>
    <div class="body">${esc(t.text) || '<span class="muted">(empty)</span>'}</div>
    <div class="actions">
      <button data-act="edit">Edit</button>
      <button data-act="copy">Copy</button>
      <button data-act="delete" class="danger">Delete</button>
    </div></article>`;
}

$("list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = btn.closest(".item").dataset.id;
  const act = btn.dataset.act;
  try {
    if (act === "delete") {
      if (!confirm("Delete this transcription?")) return;
      await api(`/api/transcriptions/${id}`, { method: "DELETE" });
      if (offset > 0 && offset >= total - 1) offset -= LIMIT;
      loadList();
    } else if (act === "copy") {
      const t = await api(`/api/transcriptions/${id}`);
      await navigator.clipboard.writeText(t.text);
      btn.textContent = "Copied ✓"; setTimeout(() => (btn.textContent = "Copy"), 1200);
    } else if (act === "edit") {
      openEditor(await api(`/api/transcriptions/${id}`));
    }
  } catch (err) { alert("Error: " + err.message); }
});

/* editor dialog: used for both edit and create */
let editingId = null;
function openEditor(t) {
  editingId = t ? t.id : null;
  $("editor-heading").textContent = t ? "Edit transcription" : "New note";
  $("ed-title").value = t?.title ?? "";
  $("ed-lang").value = t?.language ?? "";
  $("ed-text").value = t?.text ?? "";
  $("editor").showModal();
}
$("new-note").addEventListener("click", () => openEditor(null));

$("editor-form").addEventListener("submit", async (e) => {
  if (e.submitter?.value !== "save") return;
  const body = { title: $("ed-title").value, text: $("ed-text").value, language: $("ed-lang").value || null };
  try {
    if (editingId) await api(`/api/transcriptions/${editingId}`, { method: "PUT", body: JSON.stringify(body) });
    else await api("/api/transcriptions", { method: "POST", body: JSON.stringify(body) });
    loadList();
  } catch (err) { alert("Error: " + err.message); }
});

$("search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { offset = 0; loadList(); }, 250); });
$("prev").addEventListener("click", () => { offset = Math.max(0, offset - LIMIT); loadList(); });
$("next").addEventListener("click", () => { offset += LIMIT; loadList(); });

checkHealth();
loadList();

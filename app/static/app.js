// Transkribering och anonymisering — frontend
"use strict";

const AUDIO_EXT = ["mp3", "wav", "m4a", "flac", "ogg", "aac", "wma"];
const VIDEO_EXT = ["mp4", "mov", "avi", "mkv", "webm", "wmv"];
const DOC_EXT = ["pdf", "docx", "doc", "xlsx", "xls"];

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const pendingList = document.getElementById("pending-list");
const jobList = document.getElementById("job-list");
const jobsHeading = document.getElementById("jobs-heading");
const pendingTemplate = document.getElementById("pending-template");
const jobTemplate = document.getElementById("job-template");

const pollers = new Map();
let visionAvailable = false;

function fileKind(name) {
  const ext = name.split(".").pop().toLowerCase();
  if (AUDIO_EXT.includes(ext)) return "audio";
  if (VIDEO_EXT.includes(ext)) return "video";
  if (DOC_EXT.includes(ext)) return "document";
  return null;
}

// ---------------------------------------------------------------- hälsa

fetch("/api/health")
  .then((r) => r.json())
  .then((h) => {
    visionAvailable = Boolean(h.vision_available);
    const device = h.device === "cuda" ? "GPU (CUDA)" : "CPU";
    document.getElementById("device-info").textContent =
      `Beräkningsenhet: ${device} · Whisper: ${h.whisper_model} · NER: ${h.ner_model}` +
      (visionAvailable ? ` · Skärmbeskrivning: ${h.vision_model}` : "");
  })
  .catch(() => {});

// ------------------------------------------------------------ dropzone

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
});
fileInput.addEventListener("change", () => {
  addFiles([...fileInput.files]);
  fileInput.value = "";
});
["dragenter", "dragover"].forEach((type) =>
  dropzone.addEventListener(type, (e) => { e.preventDefault(); dropzone.classList.add("dragover"); })
);
["dragleave", "drop"].forEach((type) =>
  dropzone.addEventListener(type, (e) => { e.preventDefault(); dropzone.classList.remove("dragover"); })
);
dropzone.addEventListener("drop", (e) => addFiles([...e.dataTransfer.files]));

function addFiles(files) {
  for (const file of files) {
    const kind = fileKind(file.name);
    if (kind === null) {
      alert(`"${file.name}" har ett format som inte stöds.\n\nTillåtna format:\n` +
        `Ljud: ${AUDIO_EXT.join(", ")}\nFilm: ${VIDEO_EXT.join(", ")}\nDokument: ${DOC_EXT.join(", ")}`);
      continue;
    }
    pendingList.appendChild(buildPendingCard(file, kind));
  }
}

// -------------------------------------------------------- väntande kort

function buildPendingCard(file, kind) {
  const card = pendingTemplate.content.firstElementChild.cloneNode(true);
  const isMedia = kind !== "document";

  card.querySelector(".filename").textContent = file.name;
  card.querySelector(".filekind").textContent =
    kind === "audio" ? "Ljudfil — transkriberas" :
    kind === "video" ? "Filmfil — ljudspåret transkriberas" :
    "Dokument — konverteras/anonymiseras";

  card.querySelector(".opt-original span").textContent =
    isMedia ? "Transkription (oanonymiserad)" : "Oanonymiserad (konverterad) version";
  if (!isMedia) card.querySelector(".opt-timestamps").hidden = true;

  const visionLabel = card.querySelector(".opt-vision");
  if (kind !== "video") {
    visionLabel.hidden = true;
  } else if (!visionAvailable) {
    visionLabel.querySelector("input").disabled = true;
    visionLabel.classList.add("disabled");
    visionLabel.querySelector(".vision-note").textContent = "kräver ANTHROPIC_API_KEY i .env";
  }

  const boxes = {};
  card.querySelectorAll("input[data-opt]").forEach((box) => (boxes[box.dataset.opt] = box));
  const errorEl = card.querySelector(".option-error");

  function syncKeyfile() {
    boxes.keyfile.disabled = !boxes.anonymized.checked;
    if (!boxes.anonymized.checked) boxes.keyfile.checked = false;
    boxes.keyfile.closest("label").classList.toggle("disabled", boxes.keyfile.disabled);
  }
  boxes.anonymized.addEventListener("change", syncKeyfile);
  syncKeyfile();

  card.querySelector(".remove").addEventListener("click", () => card.remove());
  card.querySelector(".start").addEventListener("click", async () => {
    errorEl.hidden = true;
    if (!boxes.original.checked && !boxes.anonymized.checked) {
      errorEl.textContent = isMedia
        ? "Välj minst ett resultat: transkription eller anonymiserad transkription."
        : "Välj minst ett resultat: konverterad eller anonymiserad version.";
      errorEl.hidden = false;
      return;
    }
    card.querySelector(".start").disabled = true;
    try {
      const job = await uploadFile(file, {
        original: boxes.original.checked,
        anonymized: boxes.anonymized.checked,
        keyfile: boxes.keyfile.checked,
        timestamps: boxes.timestamps.checked,
        vision: boxes.vision.checked,
      });
      card.remove();
      showJob(job);
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.hidden = false;
      card.querySelector(".start").disabled = false;
    }
  });
  return card;
}

async function uploadFile(file, options) {
  const form = new FormData();
  form.append("file", file);
  for (const [key, value] of Object.entries(options)) form.append(key, value);
  const response = await fetch("/api/jobs", { method: "POST", body: form });
  if (!response.ok) {
    let message = "Uppladdningen misslyckades.";
    try { message = (await response.json()).detail || message; } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

// ------------------------------------------------------------ jobbkort

function showJob(job) {
  jobsHeading.hidden = false;
  const card = jobTemplate.content.firstElementChild.cloneNode(true);
  card.dataset.jobId = job.id;
  card.querySelector(".filename").textContent = job.filename;
  jobList.prepend(card);
  renderJob(card, job);
  const timer = setInterval(() => pollJob(job.id), 1500);
  pollers.set(job.id, timer);
}

async function pollJob(jobId) {
  const card = jobList.querySelector(`[data-job-id="${jobId}"]`);
  if (!card) { clearInterval(pollers.get(jobId)); return; }
  try {
    const response = await fetch(`/api/jobs/${jobId}`);
    if (!response.ok) throw new Error();
    const job = await response.json();
    renderJob(card, job);
    if (job.status === "done" || job.status === "error") {
      clearInterval(pollers.get(jobId));
      pollers.delete(jobId);
    }
  } catch (_) { /* servern tillfälligt onåbar — fortsätt polla */ }
}

const STATUS_TEXT = { queued: "I kö", processing: "Bearbetar", done: "Klar", error: "Fel" };

function renderJob(card, job) {
  card.classList.toggle("done", job.status === "done");
  const badge = card.querySelector(".status-badge");
  badge.textContent = STATUS_TEXT[job.status] || job.status;
  badge.className = `status-badge ${job.status}`;
  card.querySelector(".progress-bar").style.width = `${job.progress}%`;
  card.querySelector(".step").textContent = job.status === "done" ? "" : job.step || "";

  const errorEl = card.querySelector(".job-error");
  errorEl.hidden = !job.error;
  if (job.error) errorEl.textContent = job.error;

  const list = card.querySelector(".files");
  list.innerHTML = "";
  for (const name of job.files) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = `/api/jobs/${job.id}/files/${encodeURIComponent(name)}`;
    link.textContent = name;
    link.download = name;
    item.appendChild(link);
    if (name.endsWith("_kodnyckel.docx")) {
      const warning = document.createElement("span");
      warning.className = "file-warning";
      warning.textContent = "⚠ Innehåller ursprungliga personuppgifter — hantera separat";
      item.appendChild(warning);
    }
    list.appendChild(item);
  }

  const downloadAll = card.querySelector(".download-all-wrap");
  downloadAll.hidden = !(job.status === "done" && job.files.length > 1);
  if (!downloadAll.hidden) {
    card.querySelector(".download-all").href = `/api/jobs/${job.id}/download-all`;
  }
}

// Visa ev. befintliga jobb vid sidladdning (t.ex. efter omladdning av sidan)
fetch("/api/jobs")
  .then((r) => r.json())
  .then((jobs) => jobs.reverse().forEach(showJob))
  .catch(() => {});

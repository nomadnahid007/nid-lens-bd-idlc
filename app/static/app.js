(() => {
  "use strict";

  const FIELD_LABELS = {
    name: "Name",
    fatherName: "Father's Name",
    motherName: "Mother's Name",
    dateOfBirth: "Date of Birth",
    nidNumber: "NID Number",
    presentAddress: "Present Address",
    permanentAddress: "Permanent Address",
  };

  const ACCEPTED_TYPES = ["image/jpeg", "image/png"];

  const state = {
    front: null, // File
    back: null, // File
    lastResponse: null,
  };

  // Object URLs created for preview thumbnails, tracked per side so they can
  // be revoked on remove/reset/replace instead of leaking.
  const previewUrls = { front: null, back: null };

  const el = (id) => document.getElementById(id);

  const modeBadge = el("modeBadge");
  const dropzones = {
    front: el("dropzoneFront"),
    back: el("dropzoneBack"),
  };
  const fileInputs = {
    front: el("fileFront"),
    back: el("fileBack"),
  };
  const extractBtn = el("extractBtn");
  const resetBtn = el("resetBtn");
  const sampleLink = el("sampleLink");
  const errorBanner = el("errorBanner");
  const resultsPanel = el("resultsPanel");
  const statusPill = el("statusPill");
  const fieldsList = el("fieldsList");
  const rawTextFront = el("rawTextFront");
  const rawTextBack = el("rawTextBack");
  const warningsList = el("warningsList");
  const metaFooter = el("metaFooter");
  const copyJsonBtn = el("copyJsonBtn");
  const downloadJsonBtn = el("downloadJsonBtn");
  const toast = el("toast");

  // ---- Health badge -------------------------------------------------

  async function loadHealth() {
    try {
      const res = await fetch("/health");
      const body = await res.json();

      if (body.status === "no_api_key") {
        setBadge("Live mode: API key missing", "badge-warn");
      } else if (body.mode === "live") {
        setBadge(`Live mode · ${body.model}`, "badge-ready");
      } else {
        setBadge("Demo mode · fixture data", "badge-ready");
      }
    } catch (err) {
      setBadge("Service unreachable", "badge-warn");
    }
  }

  function setBadge(text, variant) {
    modeBadge.querySelector(".badge-text").textContent = text;
    modeBadge.className = `badge ${variant}`;
  }

  // ---- Upload zones ---------------------------------------------------

  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function isAcceptedFile(file) {
    if (ACCEPTED_TYPES.includes(file.type)) return true;
    // Some browsers omit type for drag-drop; fall back to extension check.
    return /\.(jpe?g|png)$/i.test(file.name);
  }

  function setFile(side, file) {
    if (!file) return;
    if (!isAcceptedFile(file)) {
      showError({
        code: "UNSUPPORTED_FILE",
        message: `${file.name} is not a JPG or PNG file.`,
        suggestion: "Choose a .jpg, .jpeg, or .png image.",
      });
      return;
    }

    if (previewUrls[side]) {
      URL.revokeObjectURL(previewUrls[side]);
    }

    state[side] = file;

    const zone = dropzones[side];
    const empty = zone.querySelector(".dropzone-empty");
    const filled = zone.querySelector(".dropzone-filled");
    const thumb = zone.querySelector(".preview-thumb");
    const nameEl = zone.querySelector(".file-name");
    const sizeEl = zone.querySelector(".file-size");

    const url = URL.createObjectURL(file);
    previewUrls[side] = url;
    thumb.src = url;
    nameEl.textContent = file.name;
    sizeEl.textContent = formatBytes(file.size);

    empty.hidden = true;
    filled.hidden = false;
    zone.classList.add("has-file");

    updateExtractButton();
  }

  function clearFile(side) {
    state[side] = null;
    fileInputs[side].value = "";

    if (previewUrls[side]) {
      URL.revokeObjectURL(previewUrls[side]);
      previewUrls[side] = null;
    }

    const zone = dropzones[side];
    const thumb = zone.querySelector(".preview-thumb");
    thumb.removeAttribute("src");
    zone.querySelector(".file-name").textContent = "";
    zone.querySelector(".file-size").textContent = "";

    zone.querySelector(".dropzone-empty").hidden = false;
    zone.querySelector(".dropzone-filled").hidden = true;
    zone.classList.remove("has-file");

    updateExtractButton();
  }

  function updateExtractButton() {
    extractBtn.disabled = !(state.front && state.back);
  }

  Object.entries(dropzones).forEach(([side, zone]) => {
    const input = fileInputs[side];

    zone.addEventListener("click", (e) => {
      if (e.target.closest(".remove-btn")) return;
      if (zone.classList.contains("has-file")) return;
      input.click();
    });

    zone.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && !zone.classList.contains("has-file")) {
        e.preventDefault();
        input.click();
      }
    });

    input.addEventListener("change", () => {
      if (input.files[0]) setFile(side, input.files[0]);
    });

    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("dragover");
    });

    zone.addEventListener("dragleave", () => {
      zone.classList.remove("dragover");
    });

    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
      const file = e.dataTransfer.files[0];
      if (file) setFile(side, file);
    });

    zone.querySelector(".remove-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      clearFile(side);
    });
  });

  // ---- Sample images ----------------------------------------------------

  async function loadSample(side) {
    const res = await fetch(`/api/v1/samples/${side}`);
    if (!res.ok) throw new Error(`Failed to load sample ${side} image`);
    const blob = await res.blob();
    return new File([blob], `nid_${side}_synthetic.png`, { type: "image/png" });
  }

  sampleLink.addEventListener("click", async (e) => {
    e.preventDefault();
    try {
      const [frontFile, backFile] = await Promise.all([loadSample("front"), loadSample("back")]);
      setFile("front", frontFile);
      setFile("back", backFile);
    } catch (err) {
      showError({
        code: "SAMPLE_LOAD_FAILED",
        message: "Could not load the bundled sample images.",
        suggestion: "Check the server logs, or upload your own front/back images.",
      });
    }
  });

  // ---- Reset -------------------------------------------------------------

  resetBtn.addEventListener("click", () => {
    clearFile("front");
    clearFile("back");
    hideError();
    resultsPanel.hidden = true;
    state.lastResponse = null;
  });

  // ---- Error banner --------------------------------------------------

  function showError({ code, message, suggestion }) {
    errorBanner.querySelector(".error-code").textContent = code || "ERROR";
    errorBanner.querySelector(".error-message").textContent = message || "Something went wrong.";
    errorBanner.querySelector(".error-suggestion").textContent = suggestion || "";
    errorBanner.hidden = false;
    errorBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function hideError() {
    errorBanner.hidden = true;
  }

  // ---- Extraction ------------------------------------------------------

  extractBtn.addEventListener("click", async () => {
    if (!state.front || !state.back) return;

    hideError();
    setLoading(true);

    const formData = new FormData();
    formData.append("front", state.front);
    formData.append("back", state.back);

    try {
      const res = await fetch("/api/v1/nid/extract", {
        method: "POST",
        body: formData,
      });

      const body = await res.json();

      if (!res.ok) {
        const err = body.detail && typeof body.detail === "object" ? body.detail : body;
        showError({
          code: err.code || `HTTP_${res.status}`,
          message: err.message || summarizeValidationError(body) || "Extraction failed.",
          suggestion: err.suggestion || "",
        });
        resultsPanel.hidden = true;
        return;
      }

      renderResults(body);
    } catch (err) {
      showError({
        code: "NETWORK_ERROR",
        message: "Could not reach the extraction service.",
        suggestion: "Check that the API container is running and try again.",
      });
    } finally {
      setLoading(false);
    }
  });

  function summarizeValidationError(body) {
    if (Array.isArray(body.detail)) {
      return body.detail.map((d) => `${(d.loc || []).join(".")}: ${d.msg}`).join("; ");
    }
    return null;
  }

  function setLoading(isLoading) {
    extractBtn.disabled = isLoading || !(state.front && state.back);
    extractBtn.querySelector(".spinner").hidden = !isLoading;
    extractBtn.querySelector(".btn-label").textContent = isLoading ? "Extracting..." : "Extract";
  }

  // ---- Render results --------------------------------------------------

  function renderResults(data) {
    state.lastResponse = data;
    resultsPanel.hidden = false;

    statusPill.textContent = data.status;
    statusPill.className = `status-pill status-${data.status}`;

    fieldsList.innerHTML = "";
    Object.entries(FIELD_LABELS).forEach(([key, label]) => {
      const value = data.data ? data.data[key] : null;
      const confidence = data.confidence ? data.confidence[key] : null;

      const row = document.createElement("div");
      row.className = "field-row";

      const labelEl = document.createElement("div");
      labelEl.className = "field-label";
      labelEl.textContent = label;

      const valueEl = document.createElement("div");
      valueEl.className = "field-value";
      valueEl.textContent = value || "—";

      const track = document.createElement("div");
      track.className = "confidence-track";

      const bar = document.createElement("div");
      bar.className = "confidence-bar";
      const fill = document.createElement("div");
      fill.className = "confidence-fill";
      const pct = confidence != null ? Math.round(confidence * 100) : 0;
      fill.dataset.targetWidth = `${pct}%`;
      bar.appendChild(fill);

      const valueLabel = document.createElement("span");
      valueLabel.className = "confidence-value";
      valueLabel.textContent = confidence != null ? `${pct}%` : "—";

      track.appendChild(bar);
      track.appendChild(valueLabel);

      row.appendChild(labelEl);
      row.appendChild(valueEl);
      row.appendChild(track);
      fieldsList.appendChild(row);
    });

    // Animate confidence bars in on the next frame, after the elements are
    // actually in the DOM with width: 0 — animating from a fresh insert
    // needs one rendered frame first, or the transition never plays.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        fieldsList.querySelectorAll(".confidence-fill").forEach((fill) => {
          fill.style.width = fill.dataset.targetWidth;
        });
      });
    });

    rawTextFront.textContent = (data.rawText && data.rawText.front) || "—";
    rawTextBack.textContent = (data.rawText && data.rawText.back) || "—";

    warningsList.innerHTML = "";
    const warnings = data.warnings || [];
    if (warnings.length === 0) {
      const empty = document.createElement("div");
      empty.className = "warnings-empty";
      empty.textContent = "No warnings.";
      warningsList.appendChild(empty);
    } else {
      warnings.forEach((w) => {
        const item = document.createElement("div");
        item.className = "warning-item";
        item.innerHTML = `
          <svg class="warning-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M8 1.5 15 14H1L8 1.5Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
            <path d="M8 6.2v3.4M8 12.1v.1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
          </svg>
          <span>
            <span class="warning-code">${escapeHtml(w.code || "")}</span>
            ${escapeHtml(w.message || "")}
          </span>
        `;
        warningsList.appendChild(item);
      });
    }

    metaFooter.innerHTML = "";
    const metaItems = [
      ["Request ID", data.requestId],
      ["Processing time", `${data.processingTimeMs} ms`],
      ["Model", data.model],
      ["Prompt version", data.promptVersion],
    ];
    metaItems.forEach(([label, value]) => {
      const span = document.createElement("span");
      span.textContent = `${label}: ${value}`;
      metaFooter.appendChild(span);
    });

    resultsPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ---- Copy / download JSON --------------------------------------------

  copyJsonBtn.addEventListener("click", async () => {
    if (!state.lastResponse) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(state.lastResponse, null, 2));
      showToast("Copied JSON to clipboard");
    } catch (err) {
      showToast("Could not copy to clipboard");
    }
  });

  downloadJsonBtn.addEventListener("click", () => {
    if (!state.lastResponse) return;
    const blob = new Blob([JSON.stringify(state.lastResponse, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `nid-extraction-${state.lastResponse.requestId}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });

  let toastTimer = null;
  function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    requestAnimationFrame(() => toast.classList.add("visible"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove("visible");
      setTimeout(() => {
        toast.hidden = true;
      }, 200);
    }, 2000);
  }

  // ---- Init ----------------------------------------------------------

  loadHealth();
})();

(() => {
  let activeMode = "mp3"; // "mp3" | "video"
  let activeFilter = "all";
  let lastProbedUrl = "";
  let jobsCache = [];

  const tabMp3 = document.getElementById("tab-mp3");
  const tabVideo = document.getElementById("tab-video");
  const moduleBadge = document.getElementById("module-badge");
  const moduleHeading = document.getElementById("module-heading");
  const moduleDescription = document.getElementById("module-description");
  const controlsMp3 = document.getElementById("controls-mp3");
  const controlsVideo = document.getElementById("controls-video");
  const btnDownload = document.getElementById("btn-download");
  const btnDownloadText = document.getElementById("btn-download-text");

  const urlInput = document.getElementById("url-input");
  const btnPaste = document.getElementById("btn-paste");
  const btnClearUrl = document.getElementById("btn-clear-url");
  const btnProbe = document.getElementById("btn-probe");
  const probeSpinner = document.getElementById("probe-spinner");
  const probeBtnText = document.getElementById("probe-btn-text");
  const alertBox = document.getElementById("alert-box");

  const mediaPreview = document.getElementById("media-preview");
  const previewThumb = document.getElementById("preview-thumb");
  const previewDuration = document.getElementById("preview-duration");
  const previewSite = document.getElementById("preview-site");
  const previewUploader = document.getElementById("preview-uploader");
  const previewAudioInfo = document.getElementById("preview-audio-info");
  const customTitleInput = document.getElementById("custom-title-input");

  const mp3BitrateGrid = document.getElementById("mp3-bitrate-grid");
  const videoResolutionGrid = document.getElementById("video-resolution-grid");
  const videoContainer = document.getElementById("video-container");
  const trimStart = document.getElementById("trim-start");
  const trimEnd = document.getElementById("trim-end");

  const jobsList = document.getElementById("jobs-list");
  const engineStatusText = document.getElementById("engine-status-text");
  const btnOpenFolder = document.getElementById("btn-open-folder");

  const playerDrawer = document.getElementById("player-drawer");
  const playerTitle = document.getElementById("player-title");
  const playerMount = document.getElementById("player-mount");
  const btnClosePlayer = document.getElementById("btn-close-player");

  function showAlert(msg) {
    if (!msg) {
      alertBox.classList.add("hidden");
      alertBox.textContent = "";
      return;
    }
    alertBox.textContent = msg;
    alertBox.classList.remove("hidden");
  }

  function updateDownloadButtonLabel() {
    if (activeMode === "mp3") {
      const checked = document.querySelector('input[name="mp3_bitrate"]:checked');
      const br = checked ? checked.value : "320";
      btnDownloadText.textContent = `Extract ${br} kbps MP3`;
    } else {
      const checked = document.querySelector('input[name="video_resolution"]:checked');
      const res = checked ? checked.value : "best";
      const ext = videoContainer.value.toUpperCase();
      const resLabel = res === "best" ? "Best Quality" : `${res}p`;
      btnDownloadText.textContent = `Download ${resLabel} ${ext}`;
    }
  }

  function switchMode(mode) {
    activeMode = mode;
    document.body.setAttribute("data-mode", mode);

    if (mode === "mp3") {
      tabMp3.classList.add("active");
      tabMp3.setAttribute("aria-selected", "true");
      tabVideo.classList.remove("active");
      tabVideo.setAttribute("aria-selected", "false");

      moduleBadge.textContent = "MODULE 01 • STUDIO AUDIO EXTRACTOR";
      moduleHeading.textContent = "High-Quality MP3 Audio Extractor";
      moduleDescription.textContent =
        "Paste any YouTube link or video URL to extract crystal-clear 320 kbps MP3 audio with embedded cover art and ID3 tags.";

      controlsMp3.classList.remove("hidden");
      controlsVideo.classList.add("hidden");
    } else {
      tabVideo.classList.add("active");
      tabVideo.setAttribute("aria-selected", "true");
      tabMp3.classList.remove("active");
      tabMp3.setAttribute("aria-selected", "false");

      moduleBadge.textContent = "MODULE 02 • UNIVERSAL VIDEO DOWNLOADER";
      moduleHeading.textContent = "Universal Any-Website Video Downloader";
      moduleDescription.textContent =
        "Download videos from YouTube, TikTok, X/Twitter, Instagram, Reddit, Vimeo, Twitch, and 1,000+ sites in up to 4K MP4.";

      controlsVideo.classList.remove("hidden");
      controlsMp3.classList.add("hidden");
    }
    updateDownloadButtonLabel();
  }

  function bindRadioCards(container) {
    const cards = container.querySelectorAll(".quality-card");
    cards.forEach((card) => {
      card.addEventListener("click", () => {
        cards.forEach((c) => c.classList.remove("selected"));
        card.classList.add("selected");
        const input = card.querySelector("input[type='radio']");
        if (input) input.checked = true;
        updateDownloadButtonLabel();
      });
    });
  }

  bindRadioCards(mp3BitrateGrid);
  bindRadioCards(videoResolutionGrid);
  videoContainer.addEventListener("change", updateDownloadButtonLabel);

  tabMp3.addEventListener("click", () => switchMode("mp3"));
  tabVideo.addEventListener("click", () => switchMode("video"));

  urlInput.addEventListener("input", () => {
    btnClearUrl.classList.toggle("hidden", !urlInput.value.trim());
    showAlert("");
  });

  btnClearUrl.addEventListener("click", () => {
    urlInput.value = "";
    lastProbedUrl = "";
    btnClearUrl.classList.add("hidden");
    mediaPreview.classList.add("hidden");
    customTitleInput.value = "";
    showAlert("");
    urlInput.focus();
  });

  btnPaste.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        urlInput.value = text.trim();
        btnClearUrl.classList.remove("hidden");
        probeUrl();
      }
    } catch {
      urlInput.focus();
    }
  });

  function renderDynamicResolutions(resolutions) {
    if (!Array.isArray(resolutions) || resolutions.length === 0) return;

    const currentChecked = document.querySelector('input[name="video_resolution"]:checked')?.value || "best";
    const cardsHtml = [
      `<label class="quality-card ${currentChecked === "best" ? "selected" : ""}">
        <input type="radio" name="video_resolution" value="best" ${currentChecked === "best" ? "checked" : ""} />
        <span class="q-title">Best Available (${resolutions[0].height}p)</span>
        <span class="q-sub">${resolutions[0].label} • ${resolutions[0].filesize_text}</span>
      </label>`,
    ];

    resolutions.slice(0, 5).forEach((r) => {
      const val = String(r.height);
      const isSel = currentChecked === val;
      cardsHtml.push(
        `<label class="quality-card ${isSel ? "selected" : ""}">
          <input type="radio" name="video_resolution" value="${val}" ${isSel ? "checked" : ""} />
          <span class="q-title">${r.height}p ${r.fps > 30 ? `${r.fps}fps` : ""}</span>
          <span class="q-sub">${r.label} • ${r.filesize_text}</span>
        </label>`
      );
    });

    videoResolutionGrid.innerHTML = cardsHtml.join("");
    bindRadioCards(videoResolutionGrid);
    updateDownloadButtonLabel();
  }

  async function probeUrl() {
    const url = urlInput.value.trim();
    if (!url) {
      showAlert("Please paste a valid video URL first.");
      return;
    }
    showAlert("");
    probeSpinner.classList.remove("hidden");
    probeBtnText.textContent = "Inspecting...";
    btnProbe.disabled = true;

    try {
      const res = await fetch("/api/probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Could not inspect URL.");
      }

      lastProbedUrl = url;
      previewThumb.src = data.thumbnail || "";
      previewDuration.textContent = data.duration_text || "";
      previewSite.textContent = data.site || "Web";
      previewUploader.textContent = data.uploader || "";
      previewAudioInfo.textContent = `Native Audio Stream: ~${data.best_audio_kbps || 160} kbps`;
      customTitleInput.value = data.title || "";
      mediaPreview.classList.remove("hidden");

      if (data.resolutions && data.resolutions.length > 0) {
        renderDynamicResolutions(data.resolutions);
      }
    } catch (err) {
      showAlert(err.message || "Failed to inspect URL.");
    } finally {
      probeSpinner.classList.add("hidden");
      probeBtnText.textContent = "Inspect Link";
      btnProbe.disabled = false;
    }
  }

  btnProbe.addEventListener("click", probeUrl);
  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      probeUrl();
    }
  });

  async function startDownload() {
    const url = urlInput.value.trim();
    if (!url) {
      showAlert("Please paste a YouTube or video URL first.");
      urlInput.focus();
      return;
    }
    showAlert("");
    btnDownload.disabled = true;

    const customTitle = customTitleInput.value.trim() || null;
    const tStart = trimStart.value.trim() || null;
    const tEnd = trimEnd.value.trim() || null;

    try {
      let endpoint = "/api/download/mp3";
      let payload = {};

      if (activeMode === "mp3") {
        const bitrate = document.querySelector('input[name="mp3_bitrate"]:checked')?.value || "320";
        const embedThumb = document.getElementById("mp3-embed-thumb").checked;
        const embedMeta = document.getElementById("mp3-embed-meta").checked;
        payload = {
          url,
          bitrate,
          embed_thumbnail: embedThumb,
          embed_metadata: embedMeta,
          trim_start: tStart,
          trim_end: tEnd,
          custom_title: customTitle,
        };
      } else {
        endpoint = "/api/download/video";
        const resolution = document.querySelector('input[name="video_resolution"]:checked')?.value || "best";
        payload = {
          url,
          resolution,
          container: videoContainer.value,
          trim_start: tStart,
          trim_end: tEnd,
          custom_title: customTitle,
        };
      }

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to start download.");
      }

      await fetchJobs();
    } catch (err) {
      showAlert(err.message || "Could not start download.");
    } finally {
      btnDownload.disabled = false;
    }
  }

  btnDownload.addEventListener("click", startDownload);

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  window.openInlinePlayer = (filename, title, mode) => {
    const fileUrl = `/api/files/${encodeURIComponent(filename)}?inline=true`;
    playerTitle.textContent = title || filename;
    if (mode === "mp3" || filename.toLowerCase().endsWith(".mp3")) {
      playerMount.innerHTML = `<audio controls autoplay src="${fileUrl}"></audio>`;
    } else {
      playerMount.innerHTML = `<video controls autoplay src="${fileUrl}"></video>`;
    }
    playerDrawer.classList.remove("hidden");
    playerDrawer.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  btnClosePlayer.addEventListener("click", () => {
    playerMount.innerHTML = "";
    playerDrawer.classList.add("hidden");
  });

  window.deleteJobItem = async (jobId) => {
    try {
      await fetch(`/api/jobs/${encodeURIComponent(jobId)}?delete_file=true`, {
        method: "DELETE",
      });
      await fetchJobs();
    } catch {
      // ignore
    }
  };

  function renderJobs() {
    const filtered = jobsCache.filter((j) => {
      if (activeFilter === "all") return true;
      return j.mode === activeFilter;
    });

    if (filtered.length === 0) {
      jobsList.innerHTML = `
        <div class="empty-state">
          <p>No ${activeFilter === "all" ? "" : activeFilter.toUpperCase() + " "}downloads yet. Paste a link above to get started.</p>
        </div>`;
      return;
    }

    jobsList.innerHTML = filtered
      .map((job) => {
        const thumbHtml = job.thumbnail
          ? `<img class="job-thumb" src="${escapeHtml(job.thumbnail)}" alt="" />`
          : `<div class="job-thumb">${job.mode === "mp3" ? "MP3" : "VIDEO"}</div>`;

        let statusSection = "";
        if (job.status === "queued" || job.status === "downloading" || job.status === "processing") {
          const pct = job.progress || 0;
          const statusLabel =
            job.status === "processing"
              ? "Converting & embedding tags with FFmpeg..."
              : job.speed_text
              ? `${job.downloaded_text || ""} ${job.total_text ? "/ " + job.total_text : ""} • ${job.speed_text}${job.eta_text ? " • ETA " + job.eta_text : ""}`
              : "Starting stream extraction...";

          statusSection = `
            <div class="progress-wrap">
              <div class="progress-bar-track">
                <div class="progress-bar-fill" style="width: ${pct}%"></div>
              </div>
              <div class="progress-stats">
                <span>${escapeHtml(statusLabel)}</span>
                <span>${pct}%</span>
              </div>
            </div>`;
        } else if (job.status === "failed") {
          statusSection = `<div class="job-error">Failed: ${escapeHtml(job.error || "Unknown error")}</div>`;
        }

        let actionsHtml = "";
        if (job.status === "completed" && job.filename) {
          const dlUrl = `/api/files/${encodeURIComponent(job.filename)}`;
          const safeTitle = escapeHtml(job.title).replace(/'/g, "\\'");
          const safeFile = escapeHtml(job.filename).replace(/'/g, "\\'");
          actionsHtml = `
            <button class="btn-secondary" onclick="openInlinePlayer('${safeFile}', '${safeTitle}', '${job.mode}')">
              ▶ Play
            </button>
            <a class="btn-save" href="${dlUrl}" download="${escapeHtml(job.filename)}">
              ↓ Save File
            </a>
            <button class="btn-danger-ghost" title="Remove" onclick="deleteJobItem('${job.id}')">✕</button>
          `;
        } else {
          actionsHtml = `
            <button class="btn-danger-ghost" title="Remove" onclick="deleteJobItem('${job.id}')">✕</button>
          `;
        }

        return `
          <div class="job-card">
            ${thumbHtml}
            <div class="job-body">
              <div class="job-title-row">
                <span class="job-badge ${job.mode}">${escapeHtml(job.quality_label || job.mode.toUpperCase())}</span>
                <span class="job-title" title="${escapeHtml(job.title)}">${escapeHtml(job.title)}</span>
              </div>
              <div class="job-meta">
                ${job.site ? `<span>${escapeHtml(job.site)}</span>` : ""}
                ${job.uploader ? `<span>• ${escapeHtml(job.uploader)}</span>` : ""}
                ${job.duration_text ? `<span>• ${escapeHtml(job.duration_text)}</span>` : ""}
                ${job.file_size_text ? `<span>• <strong>${escapeHtml(job.file_size_text)}</strong></span>` : ""}
              </div>
              ${statusSection}
            </div>
            <div class="job-actions">
              ${actionsHtml}
            </div>
          </div>
        `;
      })
      .join("");
  }

  async function fetchJobs() {
    try {
      const res = await fetch("/api/jobs");
      if (!res.ok) return;
      const data = await res.json();
      jobsCache = data.jobs || [];
      renderJobs();
    } catch {
      // ignore transient network errors
    }
  }

  document.querySelectorAll(".filter-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-pill").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeFilter = btn.getAttribute("data-filter") || "all";
      renderJobs();
    });
  });

  btnOpenFolder.addEventListener("click", async () => {
    try {
      await fetch("/api/open-folder", { method: "POST" });
    } catch {
      // ignore
    }
  });

  async function checkEngine() {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      if (data.portable && data.has_ffmpeg && data.has_deno) {
        engineStatusText.textContent = "Portable Engine Ready (FFmpeg + Deno)";
      } else if (data.has_ffmpeg && data.has_deno) {
        engineStatusText.textContent = "FFmpeg + yt-dlp + Deno Ready";
      } else if (data.has_ffmpeg) {
        engineStatusText.textContent = "FFmpeg + yt-dlp Ready";
      } else {
        engineStatusText.textContent = "Engine Ready (Basic Mode)";
      }
    } catch {
      engineStatusText.textContent = "Server Offline";
    }
  }

  checkEngine();
  fetchJobs();
  setInterval(fetchJobs, 1200);
})();


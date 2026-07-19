"use strict";

const installedVersion = document.querySelector("#installed-version");
const availableVersion = document.querySelector("#available-version");
const updateStatus = document.querySelector("#update-status");
const checkButton = document.querySelector("#check-update-button");

const releaseCard = document.querySelector("#release-card");
const releaseName = document.querySelector("#release-name");
const publishedAt = document.querySelector("#published-at");
const releaseNotes = document.querySelector("#release-notes");
const releaseLink = document.querySelector("#release-link");

const errorCard = document.querySelector("#update-error");
const errorMessage = document.querySelector("#update-error-message");

const downloadButton = document.querySelector("#download-update-button");
const downloadState = document.querySelector("#download-state");
const downloadProgress = document.querySelector("#download-progress");
const downloadProgressBar = document.querySelector("#download-progress-bar");
const downloadMessage = document.querySelector("#download-message");
const verifiedVersion = document.querySelector("#verified-version");

function formatDate(value) {
  if (!value) {
    return "Nicht angegeben";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

async function loadInstalledVersion() {
  const response = await fetch("/api/system/version", {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Versionsabfrage fehlgeschlagen: HTTP ${response.status}`);
  }

  const payload = await response.json();
  installedVersion.textContent = payload.version;
}

async function checkForUpdate() {
  checkButton.disabled = true;
  updateStatus.textContent = "GitHub wird geprüft …";
  availableVersion.textContent = "–";
  releaseCard.hidden = true;
  errorCard.hidden = true;

  try {
    await loadInstalledVersion();

    const response = await fetch("/api/update/check", {
      headers: {
        Accept: "application/json",
      },
    });

    const payload = await response.json();

    if (!response.ok || payload.status !== "ok") {
      throw new Error(
        payload.message || `Updateprüfung fehlgeschlagen: HTTP ${response.status}`,
      );
    }

    installedVersion.textContent = payload.installed_version;
    availableVersion.textContent = payload.available_version;

    if (payload.update_available) {
      updateStatus.textContent = "Neue Version verfügbar";
    } else {
      updateStatus.textContent = "SolarInspector ist aktuell";
    }

    releaseName.textContent =
      payload.release_name || `SolarInspector ${payload.available_version}`;

    publishedAt.textContent = formatDate(payload.published_at);
    releaseNotes.textContent =
      payload.release_notes || "Für dieses Release sind keine Hinweise vorhanden.";

    if (payload.release_url) {
      releaseLink.href = payload.release_url;
      releaseLink.hidden = false;
    } else {
      releaseLink.hidden = true;
    }

    releaseCard.hidden = false;
  } catch (error) {
    updateStatus.textContent = "Fehler";
    errorMessage.textContent = error.message;
    errorCard.hidden = false;
  } finally {
    checkButton.disabled = false;
  }
}

function renderDownloadStatus(payload) {
  const state = payload.state || "idle";
  const progress = Number(payload.progress || 0);

  downloadState.textContent = state;
  downloadProgress.textContent = `${progress} %`;
  downloadProgressBar.value = progress;
  downloadMessage.textContent =
    payload.message || "Kein Status verfügbar.";

  verifiedVersion.textContent =
    payload.state === "verified"
      ? payload.available_version || "–"
      : "–";
}

async function loadDownloadStatus() {
  const response = await fetch("/api/update/status", {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Statusabfrage fehlgeschlagen: HTTP ${response.status}`);
  }

  const payload = await response.json();
  renderDownloadStatus(payload);
}

async function downloadUpdate() {
  downloadButton.disabled = true;
  errorCard.hidden = true;

  renderDownloadStatus({
    state: "starting",
    progress: 5,
    message: "Update-Download wird gestartet.",
  });

  try {
    const response = await fetch("/api/update/download", {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    });

    const payload = await response.json();
    renderDownloadStatus(payload);

    if (!response.ok) {
      throw new Error(
        payload.message ||
          `Download fehlgeschlagen: HTTP ${response.status}`,
      );
    }
  } catch (error) {
    errorMessage.textContent = error.message;
    errorCard.hidden = false;
  } finally {
    downloadButton.disabled = false;
  }
}

checkButton.addEventListener("click", checkForUpdate);
checkForUpdate();
if (payload.update_available) {
  updateStatus.textContent = "Neue Version verfügbar";
}

downloadButton.disabled = !payload.update_available;

downloadButton.addEventListener("click", downloadUpdate);

loadDownloadStatus().catch((error) => {
  console.error(error);
});

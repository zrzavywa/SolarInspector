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

checkButton.addEventListener("click", checkForUpdate);
checkForUpdate();

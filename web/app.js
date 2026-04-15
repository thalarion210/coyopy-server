const API = "";
const WS_URL = `ws://${location.host}/ws`;

const $ = id => document.getElementById(id);

const ui = {
  statusDot: $("status-dot"),
  statusLabel: $("status-label"),
  batteryBadge: $("battery-badge"),
  batteryValue: $("battery-value"),
  btnScan: $("btn-scan"),
  btnConnect: $("btn-connect"),
  btnDisconnect: $("btn-disconnect"),
  deviceSelect: $("device-select"),
  scanStatus: $("scan-status"),
  errorBanner: $("error-banner"),
  channels: {
    a: {
      powerSlider: $("power-a"),
      powerValue: $("power-value-a"),
      powerAdj: [$("pow-a-m5"), $("pow-a-m1"), $("pow-a-p1"), $("pow-a-p5")],
      modeSelect: $("mode-a"),
      paramRow: $("param-row-a"),
      speedSlider: $("speed-a"),
      speedValue: $("speed-value-a"),
      speedAdj: [$("spd-a-m5"), $("spd-a-m1"), $("spd-a-p1"), $("spd-a-p5")],
      freqSlider: $("freq-a"),
      freqValue: $("freq-value-a"),
      freqAdj: [$("frq-a-m5"), $("frq-a-m1"), $("frq-a-p1"), $("frq-a-p5")],
      freqDynCheck: $("freq-dyn-a"),
      ampFill: $("amp-fill-a"),
      liveAmp: $("live-amp-a"),
      liveFreq: $("live-freq-a"),
      customRow: $("custom-row-a"),
      customInput: $("custom-a"),
      btnCustom: $("btn-custom-a"),
    },
    b: {
      powerSlider: $("power-b"),
      powerValue: $("power-value-b"),
      powerAdj: [$("pow-b-m5"), $("pow-b-m1"), $("pow-b-p1"), $("pow-b-p5")],
      modeSelect: $("mode-b"),
      paramRow: $("param-row-b"),
      speedSlider: $("speed-b"),
      speedValue: $("speed-value-b"),
      speedAdj: [$("spd-b-m5"), $("spd-b-m1"), $("spd-b-p1"), $("spd-b-p5")],
      freqSlider: $("freq-b"),
      freqValue: $("freq-value-b"),
      freqAdj: [$("frq-b-m5"), $("frq-b-m1"), $("frq-b-p1"), $("frq-b-p5")],
      freqDynCheck: $("freq-dyn-b"),
      ampFill: $("amp-fill-b"),
      liveAmp: $("live-amp-b"),
      liveFreq: $("live-freq-b"),
      customRow: $("custom-row-b"),
      customInput: $("custom-b"),
      btnCustom: $("btn-custom-b"),
    },
  },
};

let connected = false;
let ws = null;
const powerDebounce = { a: null, b: null };
const speedDebounce = { a: null, b: null };
const freqDebounce = { a: null, b: null };

async function apiFetch(method, path, body) {
  const options = {
    method,
    headers: { "Content-Type": "application/json" },
  };

  if (body !== undefined) {
    options.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(API + path, options);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail ?? `HTTP ${response.status}`);
    }
    return data;
  } catch (error) {
    showError(error.message);
    throw error;
  }
}

function showError(message) {
  ui.errorBanner.textContent = message;
  ui.errorBanner.classList.remove("hidden");
  window.setTimeout(() => ui.errorBanner.classList.add("hidden"), 5000);
}

function setStatus(message) {
  ui.scanStatus.textContent = message;
}

function setConnected(isConnected, battery) {
  connected = isConnected;
  ui.statusDot.className = `dot ${isConnected ? "connected" : "disconnected"}`;
  ui.statusLabel.textContent = isConnected ? "Connected" : "Disconnected";
  ui.btnConnect.classList.toggle("hidden", isConnected);
  ui.btnDisconnect.classList.toggle("hidden", !isConnected);
  ui.btnScan.disabled = isConnected;
  ui.deviceSelect.disabled = isConnected;

  if (isConnected && battery !== undefined) {
    ui.batteryBadge.classList.remove("hidden");
    ui.batteryValue.textContent = battery;
  } else {
    ui.batteryBadge.classList.add("hidden");
  }

  for (const channel of Object.values(ui.channels)) {
    channel.powerSlider.disabled = !isConnected;
    channel.powerAdj.forEach(button => {
      button.disabled = !isConnected;
    });
    channel.modeSelect.disabled = !isConnected;
    channel.speedSlider.disabled = !isConnected;
    channel.speedAdj.forEach(button => {
      button.disabled = !isConnected;
    });
    const freqEnabled = isConnected && !channel.freqDynCheck.checked;
    channel.freqSlider.disabled = !freqEnabled;
    channel.freqAdj.forEach(button => {
      button.disabled = !freqEnabled;
    });

    if (!isConnected) {
      channel.ampFill.style.width = "0%";
      channel.liveAmp.textContent = "-- %";
      channel.liveFreq.textContent = "-- Hz";
    }
  }
}

function updateChannelUI(name, state) {
  const channel = ui.channels[name];
  if (!channel) {
    return;
  }

  channel.powerSlider.value = state.power_pct;
  channel.powerValue.textContent = `${state.power_pct}%`;
  channel.modeSelect.value = state.mode;
  channel.customRow.classList.toggle("hidden", state.mode !== "custom");

  const showParams = state.mode !== "none" && state.mode !== "custom";
  channel.paramRow.classList.toggle("hidden", !showParams);

  if (state.speed !== undefined) {
    channel.speedSlider.value = state.speed;
    channel.speedValue.textContent = `${Number(state.speed).toFixed(1)}x`;
  }

  if (state.frequency !== undefined) {
    const isDynamic = state.frequency === 0;
    channel.freqDynCheck.checked = isDynamic;
    channel.freqValue.textContent = isDynamic ? "Dyn" : `${state.frequency} Hz`;
    if (!isDynamic) {
      channel.freqSlider.value = state.frequency;
    }
    channel.freqSlider.disabled = isDynamic || !connected;
    channel.freqAdj.forEach(button => {
      button.disabled = isDynamic || !connected;
    });
  }
}

function updateLiveTelemetry(name, payload) {
  const channel = ui.channels[name];
  if (!channel) {
    return;
  }

  channel.ampFill.style.width = `${payload.amplitude}%`;
  channel.liveAmp.textContent = `${payload.amplitude}%`;
  channel.liveFreq.textContent = `${payload.frequency} Hz`;
}

function connectWS() {
  if (ws) {
    ws.close();
  }

  ws = new WebSocket(WS_URL);

  ws.onmessage = ({ data }) => {
    let event;
    try {
      event = JSON.parse(data);
    } catch {
      return;
    }

    switch (event.event) {
      case "connected":
        setConnected(true, event.battery);
        break;
      case "disconnected":
        setConnected(false);
        break;
      case "battery":
        ui.batteryValue.textContent = event.level;
        break;
      case "power":
        if (ui.channels[event.channel]) {
          ui.channels[event.channel].powerSlider.value = event.value;
          ui.channels[event.channel].powerValue.textContent = `${event.value}%`;
        }
        break;
      case "mode":
        if (ui.channels[event.channel]) {
          updateChannelUI(event.channel, {
            power_pct: Number(ui.channels[event.channel].powerSlider.value),
            mode: event.mode,
            speed: event.speed,
            frequency: event.frequency,
          });
        }
        break;
      case "frame":
        if (event.a) {
          updateLiveTelemetry("a", event.a);
        }
        if (event.b) {
          updateLiveTelemetry("b", event.b);
        }
        break;
      case "error":
        showError(`Device error: ${event.detail}`);
        break;
      default:
        break;
    }
  };

  ws.onclose = () => {
    window.setTimeout(connectWS, 3000);
  };
}

async function refreshStatus() {
  const status = await apiFetch("GET", "/api/status");
  setConnected(status.connected, status.battery);
  updateChannelUI("a", status.channel_a);
  updateChannelUI("b", status.channel_b);
}

function sendModeParams(name) {
  const channel = ui.channels[name];
  const mode = channel.modeSelect.value;
  if (mode === "none" || mode === "custom") {
    return Promise.resolve();
  }

  const speed = parseFloat(channel.speedSlider.value);
  const frequency = channel.freqDynCheck.checked ? 0 : parseInt(channel.freqSlider.value, 10);
  return apiFetch("PUT", `/api/channel/${name}/mode`, { mode, speed, frequency });
}

function setupPowerSlider(name) {
  const channel = ui.channels[name];
  channel.powerSlider.addEventListener("input", () => {
    const value = Number(channel.powerSlider.value);
    channel.powerValue.textContent = `${value}%`;
    clearTimeout(powerDebounce[name]);
    powerDebounce[name] = window.setTimeout(() => {
      apiFetch("PUT", `/api/channel/${name}/power`, { value }).catch(() => { });
    }, 80);
  });
}

function setupModeSelect(name) {
  const channel = ui.channels[name];
  channel.modeSelect.addEventListener("change", () => {
    const mode = channel.modeSelect.value;
    const showParams = mode !== "none" && mode !== "custom";
    channel.paramRow.classList.toggle("hidden", !showParams);
    channel.customRow.classList.toggle("hidden", mode !== "custom");

    if (mode === "custom") {
      return;
    }

    apiFetch("PUT", `/api/channel/${name}/mode`, {
      mode,
      speed: parseFloat(channel.speedSlider.value),
      frequency: channel.freqDynCheck.checked ? 0 : parseInt(channel.freqSlider.value, 10),
    }).catch(async () => {
      await refreshStatus().catch(() => { });
    });
  });
}

function setupSpeedSlider(name) {
  const channel = ui.channels[name];
  channel.speedSlider.addEventListener("input", () => {
    channel.speedValue.textContent = `${parseFloat(channel.speedSlider.value).toFixed(1)}x`;
    clearTimeout(speedDebounce[name]);
    speedDebounce[name] = window.setTimeout(() => {
      sendModeParams(name).catch(() => { });
    }, 120);
  });
}

function setupFreqSlider(name) {
  const channel = ui.channels[name];
  channel.freqSlider.addEventListener("input", () => {
    channel.freqValue.textContent = `${channel.freqSlider.value} Hz`;
    clearTimeout(freqDebounce[name]);
    freqDebounce[name] = window.setTimeout(() => {
      sendModeParams(name).catch(() => { });
    }, 120);
  });
}

function setupAdjustments(name) {
  const channel = ui.channels[name];

  [
    [channel.powerAdj[0], -5],
    [channel.powerAdj[1], -1],
    [channel.powerAdj[2], 1],
    [channel.powerAdj[3], 5],
  ].forEach(([button, delta]) => {
    button.addEventListener("click", () => {
      const next = Math.max(0, Math.min(100, Number(channel.powerSlider.value) + delta));
      channel.powerSlider.value = next;
      channel.powerValue.textContent = `${next}%`;
      clearTimeout(powerDebounce[name]);
      powerDebounce[name] = window.setTimeout(() => {
        apiFetch("PUT", `/api/channel/${name}/power`, { value: next }).catch(() => { });
      }, 80);
    });
  });

  [
    [channel.speedAdj[0], -0.5],
    [channel.speedAdj[1], -0.1],
    [channel.speedAdj[2], 0.1],
    [channel.speedAdj[3], 0.5],
  ].forEach(([button, delta]) => {
    button.addEventListener("click", () => {
      const next = Math.max(0.1, Math.min(5.0, Math.round((parseFloat(channel.speedSlider.value) + delta) * 10) / 10));
      channel.speedSlider.value = next;
      channel.speedValue.textContent = `${next.toFixed(1)}x`;
      clearTimeout(speedDebounce[name]);
      speedDebounce[name] = window.setTimeout(() => {
        sendModeParams(name).catch(() => { });
      }, 120);
    });
  });

  [
    [channel.freqAdj[0], -5],
    [channel.freqAdj[1], -1],
    [channel.freqAdj[2], 1],
    [channel.freqAdj[3], 5],
  ].forEach(([button, delta]) => {
    button.addEventListener("click", () => {
      if (channel.freqDynCheck.checked) {
        return;
      }
      const next = Math.max(10, Math.min(240, parseInt(channel.freqSlider.value, 10) + delta));
      channel.freqSlider.value = next;
      channel.freqValue.textContent = `${next} Hz`;
      clearTimeout(freqDebounce[name]);
      freqDebounce[name] = window.setTimeout(() => {
        sendModeParams(name).catch(() => { });
      }, 120);
    });
  });

  channel.freqDynCheck.addEventListener("change", () => {
    const isDynamic = channel.freqDynCheck.checked;
    channel.freqSlider.disabled = isDynamic || !connected;
    channel.freqAdj.forEach(button => {
      button.disabled = isDynamic || !connected;
    });
    channel.freqValue.textContent = isDynamic ? "Dyn" : `${channel.freqSlider.value} Hz`;
    sendModeParams(name).catch(() => { });
  });
}

function setupCustomPattern(name) {
  const channel = ui.channels[name];
  channel.btnCustom.addEventListener("click", async () => {
    let frames;
    try {
      frames = JSON.parse(channel.customInput.value);
      if (!Array.isArray(frames) || frames.length === 0) {
        throw new Error("must be a non-empty array");
      }
    } catch (error) {
      showError(`Invalid JSON: ${error.message}`);
      return;
    }

    await apiFetch("PUT", `/api/channel/${name}/pattern`, { frames }).catch(() => { });
  });
}

ui.btnScan.addEventListener("click", async () => {
  ui.btnScan.disabled = true;
  ui.deviceSelect.innerHTML = '<option value="">Scanning...</option>';
  setStatus("Scanning for nearby Coyote devices...");

  try {
    const result = await apiFetch("POST", "/api/scan", { timeout: 5.0 });
    ui.deviceSelect.innerHTML = "";
    if (result.devices.length === 0) {
      ui.deviceSelect.innerHTML = '<option value="">No devices found</option>';
      ui.btnConnect.disabled = true;
      setStatus("No Coyote devices found nearby.");
      return;
    }

    result.devices.forEach(device => {
      const option = document.createElement("option");
      option.value = device.address;
      option.textContent = `${device.name} (${device.address}) ${device.rssi} dBm`;
      ui.deviceSelect.appendChild(option);
    });
    ui.btnConnect.disabled = false;
    setStatus(`Found ${result.devices.length} device(s).`);
  } finally {
    ui.btnScan.disabled = false;
  }
});

ui.btnConnect.addEventListener("click", async () => {
  const address = ui.deviceSelect.value || null;
  if (!address) {
    showError("Select a device first.");
    return;
  }

  ui.btnConnect.disabled = true;
  ui.statusDot.className = "dot connecting";
  ui.statusLabel.textContent = "Connecting...";

  try {
    await apiFetch("POST", "/api/connect", { address });
    await refreshStatus();
  } catch {
    setConnected(false);
  } finally {
    ui.btnConnect.disabled = false;
  }
});

ui.btnDisconnect.addEventListener("click", async () => {
  await apiFetch("POST", "/api/disconnect");
  setConnected(false);
});

["a", "b"].forEach(name => {
  setupPowerSlider(name);
  setupModeSelect(name);
  setupSpeedSlider(name);
  setupFreqSlider(name);
  setupAdjustments(name);
  setupCustomPattern(name);
});

(async () => {
  await refreshStatus().catch(() => { });
  connectWS();
})();

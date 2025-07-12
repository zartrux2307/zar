// main.js
window.updateStatus = function (data) {
    document.getElementById("cpu-usage").textContent = "CPU: " + data.cpu_usage;
    document.getElementById("cpu-speed").textContent = "Frecuencia: " + data.cpu_speed;
    document.getElementById("cpu-temp").textContent = "Temp: " + data.cpu_temp;
    document.getElementById("mining-time").textContent = data.mining_time;
    document.getElementById("threads").textContent = data.threads;
    document.getElementById("ram").textContent = data.ram;
    document.getElementById("hashrate").textContent = data.hashrate;
    document.getElementById("hash-trend").textContent = data.hash_trend;
    document.getElementById("shares").textContent = data.shares;
    document.getElementById("shares-trend").textContent = data.shares_trend;
    document.getElementById("diff").textContent = data.difficulty;
    document.getElementById("diff-trend").textContent = data.diff_trend;
    document.getElementById("block").textContent = data.block;
    document.getElementById("block-status").textContent = data.block_status;
    document.getElementById("uptime").textContent = new Date(data.uptime_seconds * 1000).toISOString().substr(11, 8);
    // progresos
    document.getElementById("threads-progress").style.width = data.threads_progress + "%";
    document.getElementById("ram-progress").style.width = data.ram_progress + "%";
    // temp status
    document.getElementById("temp").textContent = data.cpu_temp;
    document.getElementById("temp-status").textContent = (parseInt(data.cpu_temp) > 80) ? "¡Alta!" : "Normal";
};

window.updateConsole = function (lines) {
    const consoleDiv = document.getElementById("console");
    consoleDiv.innerHTML = lines.map(line =>
        `<div class="console-line">${line.replace(/\n/g, "")}</div>`
    ).join("");
    consoleDiv.scrollTop = consoleDiv.scrollHeight;
};

window.onload = function () {
    // Botones de cambio de modo
    document.getElementById("pool-btn").onclick = () => setMode("POOL");
    document.getElementById("ia-btn").onclick = () => setMode("IA");
    document.getElementById("hybrid-btn").onclick = () => setMode("HYBRID");
};

function setMode(mode) {
    fetch("/api/set_mode", {
        method: "POST",
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
    })
    .then(res => res.json())
    .then(resp => {
        if (resp.result === "ok") {
            // success visual (toast, color, etc)
        } else {
            alert("Error cambiando de modo: " + resp.msg);
        }
    });
}

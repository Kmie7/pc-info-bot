import { createServer } from "http";
import { exec } from "child_process";
import { promisify } from "util";
import { readFile } from "fs/promises";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const execAsync = promisify(exec);
const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = 3000;

// ─── System command runners ───────────────────────────────────────────────────

async function run(cmd) {
  try {
    const { stdout } = await execAsync(cmd, { timeout: 8000 });
    return stdout.trim();
  } catch {
    return null;
  }
}

// ─── Windows spec readers ─────────────────────────────────────────────────────

async function getSpecsWindows() {
  const [cpu, ramRaw, gpuRaw, diskRaw, osRaw] = await Promise.all([
    run(`wmic cpu get Name /value`),
    run(`wmic computersystem get TotalPhysicalMemory /value`),
    run(`wmic path win32_VideoController get Name,AdapterRAM /value`),
    run(`wmic logicaldisk get DeviceID,Size,FreeSpace /value`),
    run(`wmic os get Caption,Version /value`),
  ]);

  // CPU
  const cpuName = extractWmic(cpu, "Name") || "Unknown";

  // RAM — convert bytes to GB
  const ramBytes = parseInt(extractWmic(ramRaw, "TotalPhysicalMemory") || "0");
  const ramGB = ramBytes ? Math.round(ramBytes / (1024 ** 3)) + " GB" : "Unknown";

  // GPU — may have multiple entries
  const gpuEntries = parseWmicMulti(gpuRaw, ["Name", "AdapterRAM"]);
  const gpus = gpuEntries.map(g => {
    const vram = parseInt(g.AdapterRAM || "0");
    const vramStr = vram > 0 ? ` (${Math.round(vram / (1024 ** 3))} GB VRAM)` : "";
    return (g.Name || "Unknown") + vramStr;
  });

  // Disk — list all drives
  const diskEntries = parseWmicMulti(diskRaw, ["DeviceID", "Size", "FreeSpace"]);
  const disks = diskEntries
    .filter(d => d.DeviceID && parseInt(d.Size || "0") > 0)
    .map(d => {
      const total = Math.round(parseInt(d.Size) / (1024 ** 3));
      const free  = Math.round(parseInt(d.FreeSpace || "0") / (1024 ** 3));
      const used  = total - free;
      return { drive: d.DeviceID, total: total + " GB", used: used + " GB", free: free + " GB" };
    });

  // OS
  const osName    = extractWmic(osRaw, "Caption") || "Windows";
  const osVersion = extractWmic(osRaw, "Version") || "";

  return { os: `${osName} (${osVersion})`, cpu: cpuName, ram: ramGB, gpu: gpus, disks, platform: "windows" };
}

// ─── macOS spec readers ───────────────────────────────────────────────────────

async function getSpecsMac() {
  const [cpuRaw, ramRaw, gpuRaw, diskRaw, osRaw] = await Promise.all([
    run(`sysctl -n machdep.cpu.brand_string`),
    run(`sysctl -n hw.memsize`),
    run(`system_profiler SPDisplaysDataType | grep "Chipset Model:" | head -1`),
    run(`df -h / | tail -1`),
    run(`sw_vers -productVersion`),
  ]);

  const cpu  = cpuRaw || "Unknown";
  const ramB = parseInt(ramRaw || "0");
  const ram  = ramB ? Math.round(ramB / (1024 ** 3)) + " GB" : "Unknown";
  const gpu  = gpuRaw ? gpuRaw.replace(/.*Chipset Model:\s*/, "").trim() : "Unknown";

  // df output: Filesystem Size Used Avail Capacity Mounted
  const parts = (diskRaw || "").split(/\s+/);
  const disks = parts.length >= 4
    ? [{ drive: "/", total: parts[1], used: parts[2], free: parts[3] }]
    : [];

  const osVersion = osRaw || "Unknown";

  return { os: `macOS ${osVersion}`, cpu, ram, gpu: [gpu], disks, platform: "mac" };
}

// ─── Linux spec readers ───────────────────────────────────────────────────────

async function getSpecsLinux() {
  const [cpuRaw, ramRaw, gpuRaw, diskRaw, osRaw] = await Promise.all([
    run(`grep "model name" /proc/cpuinfo | head -1`),
    run(`grep MemTotal /proc/meminfo`),
    run(`lspci 2>/dev/null | grep -i "vga\\|3d\\|display" | head -3`),
    run(`df -h --output=target,size,used,avail | tail -n +2`),
    run(`cat /etc/os-release | grep PRETTY_NAME`),
  ]);

  const cpu = cpuRaw ? cpuRaw.replace(/.*model name\s*:\s*/i, "").trim() : "Unknown";

  const ramKB = parseInt((ramRaw || "").replace(/[^0-9]/g, "") || "0");
  const ram   = ramKB ? Math.round(ramKB / (1024 ** 2)) + " GB" : "Unknown";

  const gpus  = (gpuRaw || "Unknown").split("\n").map(l => l.replace(/^.*:\s*/, "").trim()).filter(Boolean);

  const disks = (diskRaw || "").split("\n")
    .map(line => { const p = line.trim().split(/\s+/); return p.length >= 4 ? { drive: p[0], total: p[1], used: p[2], free: p[3] } : null; })
    .filter(Boolean);

  const osName = osRaw ? osRaw.replace(/PRETTY_NAME=|"/g, "").trim() : "Linux";

  return { os: osName, cpu, ram, gpu: gpus, disks, platform: "linux" };
}

// ─── Platform detection & dispatch ───────────────────────────────────────────

async function getSpecs() {
  const plat = process.platform;
  if (plat === "win32")  return await getSpecsWindows();
  if (plat === "darwin") return await getSpecsMac();
  return await getSpecsLinux();
}

// ─── WMIC helpers ─────────────────────────────────────────────────────────────

function extractWmic(output, key) {
  if (!output) return null;
  const match = output.match(new RegExp(`${key}=(.+)`));
  return match ? match[1].trim() : null;
}

function parseWmicMulti(output, keys) {
  if (!output) return [];
  const results = [];
  let current = {};
  for (const line of output.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (Object.keys(current).length) { results.push(current); current = {}; }
      continue;
    }
    for (const key of keys) {
      if (trimmed.startsWith(key + "=")) {
        current[key] = trimmed.slice(key.length + 1).trim();
      }
    }
  }
  if (Object.keys(current).length) results.push(current);
  return results;
}

// ─── HTTP Server ──────────────────────────────────────────────────────────────

const server = createServer(async (req, res) => {
  // CORS — allow the HTML file to call this from file:// or localhost
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") { res.writeHead(204); res.end(); return; }

  const url = new URL(req.url, `http://localhost:${PORT}`);

  // GET /api/specs — return PC specs as JSON
  if (url.pathname === "/api/specs" && req.method === "GET") {
    try {
      const specs = await getSpecs();
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(specs));
    } catch (err) {
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: err.message }));
    }
    return;
  }

  // GET / — serve index.html
  if (url.pathname === "/" && req.method === "GET") {
    try {
      const html = await readFile(join(__dirname, "index.html"), "utf8");
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(html);
    } catch {
      res.writeHead(404); res.end("index.html not found");
    }
    return;
  }

  res.writeHead(404); res.end("Not found");
});

server.listen(PORT, () => {
  console.log(`✅  PC Info Bot server running → http://localhost:${PORT}`);
  console.log(`   API endpoint: http://localhost:${PORT}/api/specs`);
});

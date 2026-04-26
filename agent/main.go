package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"
)

type Metric struct {
	Host          string  `json:"host"`
	CPU           float64 `json:"cpu"`
	Memory        float64 `json:"memory"`
	DiskUsed      float64 `json:"disk_used"`
	DiskTotal     float64 `json:"disk_total"`
	DiskPercent   float64 `json:"disk_percent"`
	NetRxBytes    uint64  `json:"net_rx_bytes"`
	NetTxBytes    uint64  `json:"net_tx_bytes"`
	LatencyMs     float64 `json:"latency_ms"`
	UptimeSeconds int64   `json:"uptime_seconds"`
	LoadAvg       float64 `json:"load_avg"`
	Processes     int     `json:"processes"`
	Temperature   float64 `json:"temperature"`
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" { return v }
	return fallback
}

func readCPU() (float64, error) {
	readStat := func() (idle, total uint64, err error) {
		f, err := os.Open("/proc/stat")
		if err != nil { return }
		defer f.Close()
		data, _ := io.ReadAll(f)
		for _, line := range strings.Split(string(data), "\n") {
			if strings.HasPrefix(line, "cpu ") {
				fields := strings.Fields(line)[1:]
				var vals [10]uint64
				for i, f := range fields {
					if i >= 10 { break }
					vals[i], _ = strconv.ParseUint(f, 10, 64)
				}
				idle = vals[3]
				for _, v := range vals { total += v }
				return
			}
		}
		return
	}
	idle1, total1, err := readStat()
	if err != nil { return 0, err }
	time.Sleep(500 * time.Millisecond)
	idle2, total2, _ := readStat()
	idleDelta := float64(idle2 - idle1)
	totalDelta := float64(total2 - total1)
	if totalDelta == 0 { return 0, nil }
	return (1 - idleDelta/totalDelta) * 100, nil
}

func readMemory() (float64, error) {
	f, err := os.Open("/proc/meminfo")
	if err != nil { return 0, err }
	defer f.Close()
	data, _ := io.ReadAll(f)
	vals := map[string]uint64{}
	for _, line := range strings.Split(string(data), "\n") {
		parts := strings.Fields(line)
		if len(parts) >= 2 {
			key := strings.TrimSuffix(parts[0], ":")
			val, _ := strconv.ParseUint(parts[1], 10, 64)
			vals[key] = val
		}
	}
	total := vals["MemTotal"]
	available := vals["MemAvailable"]
	if total == 0 { return 0, fmt.Errorf("no MemTotal") }
	return float64(total-available) / float64(total) * 100, nil
}

func readDisk() (used, total, percent float64) {
	df, err := os.Open("/proc/diskstats")
	if err != nil { return }
	defer df.Close()
	data, _ := io.ReadAll(df)
	var readSectors, writeSectors uint64
	for _, line := range strings.Split(string(data), "\n") {
		parts := strings.Fields(line)
		if len(parts) < 14 { continue }
		name := parts[2]
		if (strings.HasPrefix(name,"sd")||strings.HasPrefix(name,"vd")||
			strings.HasPrefix(name,"xvd")||strings.HasPrefix(name,"nvme")) && len(name)<=7 {
			r, _ := strconv.ParseUint(parts[5], 10, 64)
			w, _ := strconv.ParseUint(parts[9], 10, 64)
			readSectors += r; writeSectors += w
		}
	}
	totalSectors := readSectors + writeSectors
	used = float64(totalSectors*512) / (1024*1024*1024)
	total = used * 1.5
	if total > 0 { percent = used / total * 100 }
	return
}

func readNetwork() (rxBytes, txBytes uint64) {
	f, err := os.Open("/proc/net/dev")
	if err != nil { return }
	defer f.Close()
	data, _ := io.ReadAll(f)
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line,"eth")||strings.HasPrefix(line,"en") {
			parts := strings.Fields(line)
			if len(parts) >= 10 {
				rx, _ := strconv.ParseUint(parts[1], 10, 64)
				tx, _ := strconv.ParseUint(parts[9], 10, 64)
				rxBytes += rx; txBytes += tx
			}
		}
	}
	return
}

func readUptime() int64 {
	f, err := os.Open("/proc/uptime")
	if err != nil { return 0 }
	defer f.Close()
	data, _ := io.ReadAll(f)
	parts := strings.Fields(string(data))
	if len(parts) == 0 { return 0 }
	v, _ := strconv.ParseFloat(parts[0], 64)
	return int64(v)
}

func readLoadAvg() float64 {
	f, err := os.Open("/proc/loadavg")
	if err != nil { return 0 }
	defer f.Close()
	data, _ := io.ReadAll(f)
	parts := strings.Fields(string(data))
	if len(parts) == 0 { return 0 }
	v, _ := strconv.ParseFloat(parts[0], 64)
	return v
}

func readProcesses() int {
	entries, err := os.ReadDir("/proc")
	if err != nil { return 0 }
	count := 0
	for _, e := range entries {
		if e.IsDir() {
			if _, err := strconv.Atoi(e.Name()); err == nil { count++ }
		}
	}
	return count
}

func readTemperature() float64 {
	paths := []string{
		"/sys/class/thermal/thermal_zone0/temp",
		"/sys/class/hwmon/hwmon0/temp1_input",
	}
	for _, p := range paths {
		data, err := os.ReadFile(p)
		if err != nil { continue }
		v, err := strconv.ParseFloat(strings.TrimSpace(string(data)), 64)
		if err != nil { continue }
		if v > 1000 { v /= 1000 }
		return v
	}
	return 0
}

func measureLatency(apiURL string) float64 {
	start := time.Now()
	client := &http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get(strings.Replace(apiURL, "/metrics", "/health", 1))
	if err != nil { return 9999 }
	defer resp.Body.Close()
	return float64(time.Since(start).Milliseconds())
}

func sendMetric(client *http.Client, apiURL, deviceToken string, metric Metric) error {
	body, _ := json.Marshal(metric)
	req, err := http.NewRequest("POST", apiURL, bytes.NewBuffer(body))
	if err != nil { return err }
	req.Header.Set("Content-Type", "application/json")
	if deviceToken != "" { req.Header.Set("X-Device-Token", deviceToken) }
	resp, err := client.Do(req)
	if err != nil { return err }
	defer resp.Body.Close()
	if resp.StatusCode >= 400 { return fmt.Errorf("API status %d", resp.StatusCode) }
	return nil
}

func main() {
	host, _ := os.Hostname()
	apiURL      := getEnv("INGEST_URL",    "http://ingest-api:3000/metrics")
	deviceToken := getEnv("DEVICE_TOKEN",  "")
	client := &http.Client{Timeout: 5 * time.Second}
	log.Printf("ETI SENTINEL Agent | host=%s | api=%s", host, apiURL)

	for {
		cpu, _           := readCPU()
		mem, _           := readMemory()
		du, dt, dp       := readDisk()
		rx, tx           := readNetwork()
		latency          := measureLatency(apiURL)
		uptime           := readUptime()
		load             := readLoadAvg()
		procs            := readProcesses()
		temp             := readTemperature()

		metric := Metric{
			Host: host, CPU: cpu, Memory: mem,
			DiskUsed: du, DiskTotal: dt, DiskPercent: dp,
			NetRxBytes: rx, NetTxBytes: tx,
			LatencyMs: latency, UptimeSeconds: uptime,
			LoadAvg: load, Processes: procs, Temperature: temp,
		}

		if err := sendMetric(client, apiURL, deviceToken, metric); err != nil {
			log.Printf("Send error: %v", err)
		} else {
			log.Printf("OK | cpu=%.1f%% mem=%.1f%% lat=%.0fms load=%.2f procs=%d", cpu, mem, latency, load, procs)
		}
		time.Sleep(5 * time.Second)
	}
}

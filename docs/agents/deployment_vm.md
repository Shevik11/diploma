# VM Deployment Guide: From Model Install to Running Benchmarks

This guide describes every step to deploy a model on a Virtual Machine and run benchmark tests that collect metrics and save results as JSON.

---

## Prerequisites

- **Hypervisor** installed: KVM/QEMU, VirtualBox, VMware, or Hyper-V
- **Terraform** and **Ansible** installed (for automated provisioning)
- VM with **Ubuntu 22.04+** (or compatible Linux distro)
- Minimum VM specs: 4 vCPUs, 8 GB RAM, 40 GB disk (for small models)
- Network connectivity between host and VM (SSH access)

---

## Step 1: Provision the VM

### Option A: Terraform (automated)

```bash
cd vm/terraform

# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Create the VM
terraform apply -auto-approve
```

This uses `vm/terraform/main.tf` to create a VM with the specs defined in `vm/terraform/variables.tf`.

### Option B: Manual VM Creation

1. Create a new VM in your hypervisor (KVM, VirtualBox, VMware, or Hyper-V)
2. Allocate resources:
   - **Small models (≤3B):** 4 vCPUs, 8 GB RAM, 20 GB disk
   - **Medium models (3B–7B):** 8 vCPUs, 16 GB RAM, 40 GB disk
   - **Large models (7B+):** 8+ vCPUs, 32 GB RAM, 60 GB disk
3. Install Ubuntu 22.04 LTS
4. Enable SSH access
5. Note the VM's IP address

---

## Step 2: Configure the VM

### Option A: Ansible (automated)

```bash
cd vm/ansible

# Update inventory with VM IP
# Edit vm/ansible/inventory/hosts.ini with your VM's IP address

# Run the full setup
ansible-playbook -i inventory/hosts.ini playbooks/setup-vm.yml
ansible-playbook -i inventory/hosts.ini playbooks/install-dependencies.yml
```

### Option B: Manual Setup Script

```bash
# SSH into the VM
ssh user@<VM_IP>

# Run the setup script
bash vm/scripts/setup-vm.sh
```

### What Gets Installed

The setup installs:
- Python 3.11+
- pip / uv package manager
- ML framework dependencies (based on chosen framework)
- System monitoring tools (htop, sar, vmstat, iostat)
- NVIDIA drivers + CUDA (if GPU available)
- Ollama / llama.cpp / vLLM (based on configuration)

---

## Step 3: Install the ML Framework

### Ollama (recommended)

```bash
# SSH into VM
ssh user@<VM_IP>

# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
systemctl start ollama

# Verify Ollama is running
curl http://localhost:11434/api/tags
```

### llama.cpp

```bash
# Clone and build llama.cpp
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
make -j$(nproc)

# Start the server
./server --model /path/to/model.gguf --port 8080 --host 0.0.0.0
```

### vLLM (requires GPU)

```bash
pip install vllm

# Start vLLM server
python -m vllm.entrypoints.openai.api_server \
  --model microsoft/phi-3.5-mini-instruct \
  --port 8000 \
  --host 0.0.0.0
```

---

## Step 4: Download the Model

### Ollama

```bash
# Pull models (run inside VM)
ollama pull phi3:mini
ollama pull gemma2:2b
ollama pull llama3.2:1b
ollama pull mistral:7b
ollama pull qwen2.5:0.5b
```

### Ansible (automated)

```bash
ansible-playbook -i inventory/hosts.ini playbooks/deploy-model.yml \
  -e "model_name=phi3:mini"
```

### Manual GGUF Download

```bash
# Download from HuggingFace
wget https://huggingface.co/<repo>/resolve/main/<model>.gguf -O /models/<model>.gguf
```

---

## Step 5: Verify the Model is Running

### Health check from host machine

```bash
# Ollama
curl http://<VM_IP>:11434/api/tags

# llama.cpp
curl http://<VM_IP>:8080/health

# vLLM
curl http://<VM_IP>:8000/health
```

### Test inference from host machine

```bash
# Ollama
curl http://<VM_IP>:11434/api/generate \
  -d '{"model": "phi3:mini", "prompt": "Hello", "stream": false}'

# llama.cpp
curl http://<VM_IP>:8080/completion \
  -d '{"prompt": "Hello", "n_predict": 50}'

# vLLM
curl http://<VM_IP>:8000/v1/completions \
  -d '{"model": "phi-3.5-mini", "prompt": "Hello", "max_tokens": 50}'
```

**Expected:** A JSON response with generated text. If you get a response, the model is loaded and ready.

---

## Step 6: Set Up Monitoring on the VM

### Ansible (automated)

```bash
ansible-playbook -i inventory/hosts.ini playbooks/configure-monitoring.yml
```

### Manual

```bash
# SSH into VM
ssh user@<VM_IP>

# Install monitoring
bash vm/scripts/install-monitoring.sh
```

This sets up:
- **Node Exporter** — system metrics for Prometheus
- **nvidia-smi** monitoring (if GPU present)
- System tools: `htop`, `sar`, `vmstat`, `iostat`

---

## Step 7: Run Benchmark Tests

With the model verified and running on the VM, execute the benchmark test suite from the host machine. Each test collects metrics using monitoring tools and saves all data as JSON to `results/`.

### Run all tests for a model

```bash
# Cold start test
python benchmarks/load-generator/cold-start-test.py --model phi3:mini --platform vm --endpoint http://<VM_IP>:11434 --output results/vm/phi3-mini/cold_start.json

# Warm test
python benchmarks/load-generator/warm-test.py --model phi3:mini --platform vm --endpoint http://<VM_IP>:11434 --output results/vm/phi3-mini/warm.json

# Sequential request test
python benchmarks/load-generator/sequential-test.py --model phi3:mini --platform vm --endpoint http://<VM_IP>:11434 --output results/vm/phi3-mini/sequential.json

# Concurrent request test
python benchmarks/load-generator/concurrent-test.py --model phi3:mini --platform vm --endpoint http://<VM_IP>:11434 --output results/vm/phi3-mini/concurrent.json

# Stress test
python benchmarks/load-generator/stress-test.py --model phi3:mini --platform vm --endpoint http://<VM_IP>:11434 --output results/vm/phi3-mini/stress.json
```

See [`testing.md`](./testing.md) for the full list of test types and execution rules.

---

## Step 8: Collect Metrics During Tests

Metrics are collected automatically during each test run using these tools:

| Tool | What It Collects | Where It Runs |
|------|------------------|---------------|
| `psutil` (Python) | CPU, RAM, disk I/O | Host (test runner) |
| `htop` / `top` | CPU, memory per process | VM (via SSH) |
| `sar` / `vmstat` / `iostat` | System-level metrics | VM (via SSH) |
| `nvidia-smi` | GPU utilization, VRAM | VM (if GPU present) |
| `node_exporter` | Prometheus-compatible metrics | VM |
| `time` (Python) | Latency, throughput, response times | Host (test runner) |

The test scripts SSH into the VM to collect resource metrics alongside inference measurements.

See [`metrics.md`](./metrics.md) for the full list of metrics to collect.

---

## Step 9: JSON Output Format

All test results are saved as JSON in `results/` with this structure:

```
results/
  vm/
    phi3-mini/
      cold_start.json
      warm.json
      sequential.json
      concurrent.json
      stress.json
    gemma2-2b/
      ...
```

Each JSON file follows this schema:

```json
{
  "model": "phi3:mini",
  "platform": "vm",
  "framework": "ollama",
  "test_type": "cold_start",
  "timestamp": "2026-04-04T15:30:00Z",
  "hardware": {
    "cpu": "Intel i7-12700, 8 vCPUs",
    "ram_gb": 16,
    "gpu": "none",
    "disk": "Virtual SSD",
    "hypervisor": "KVM"
  },
  "metrics": {
    "cold_start_time_s": 8.5,
    "first_token_latency_ms": 450,
    "tokens_per_second": 22.1,
    "total_response_time_s": 3.2,
    "cpu_usage_percent": 82.1,
    "memory_usage_mb": 2048,
    "peak_memory_mb": 2800,
    "disk_io_read_mb": 1200,
    "gpu_utilization_percent": null,
    "vm_boot_time_s": 12.3,
    "energy_consumption_wh": null
  },
  "quality": {
    "bleu_score": 0.42,
    "rouge_score": 0.55
  },
  "iterations": 3,
  "raw_results": []
}
```

This JSON format is designed for future graph visualization and cross-model comparison.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| VM won't start | Check hypervisor logs, verify resource allocation |
| SSH connection refused | Verify VM is running, check firewall rules, verify SSH service |
| Ansible fails | Check `inventory/hosts.ini` IP, verify SSH key authentication |
| Model download fails | Check VM disk space, verify network connectivity |
| Out of memory | Increase VM RAM allocation, use smaller model/quantization |
| Inference timeout | VMs have higher cold start — increase timeout to 180s+ |
| Test script can't reach VM | Check VM firewall (`ufw allow <port>`), verify IP routing, test with `curl` |
| Slow performance | Check CPU pinning, disable memory ballooning, verify no noisy neighbors |

---

## Quick Reference: Full Command Sequence

```bash
# 1. Provision VM (Terraform)
cd vm/terraform && terraform apply -auto-approve

# 2. Configure VM (Ansible)
cd vm/ansible
ansible-playbook -i inventory/hosts.ini playbooks/setup-vm.yml
ansible-playbook -i inventory/hosts.ini playbooks/install-dependencies.yml

# 3. Deploy model (Ansible)
ansible-playbook -i inventory/hosts.ini playbooks/deploy-model.yml -e "model_name=phi3:mini"

# 4. Set up monitoring
ansible-playbook -i inventory/hosts.ini playbooks/configure-monitoring.yml

# 5. Verify model is ready
curl http://<VM_IP>:11434/api/generate -d '{"model": "phi3:mini", "prompt": "test", "stream": false}'

# 6. Run benchmark tests (on host)
python benchmarks/load-generator/cold-start-test.py --model phi3:mini --platform vm --endpoint http://<VM_IP>:11434 --output results/vm/phi3-mini/cold_start.json

# 7. View results
python -m json.tool results/vm/phi3-mini/cold_start.json
```

---

## VM vs Docker: Key Differences

| Aspect | Docker | VM |
|--------|--------|----|
| Cold start time | Seconds | Minutes |
| Resource overhead | Low | Higher (full OS) |
| Isolation | Process-level | Hardware-level |
| Setup complexity | Low | Medium-High |
| Timeout recommendations | 120s cold start | 180s+ cold start |
| Provisioning | `docker run` | Terraform + Ansible |

---

## Related Files

- `vm/terraform/` — VM provisioning configuration
- `vm/ansible/` — VM configuration and deployment playbooks
- `vm/scripts/` — Manual setup and monitoring scripts
- `agents/metrics.md` — Metrics to collect during tests
- `agents/testing.md` — Test types to run
- `agents/deployment_docker.md` — Docker deployment guide (for comparison)

# 📘 Аналіз ефективності розгортання малих мовних моделей у контейнеризованому середовищі

> Дослідження оптимальних конфігурацій CPU/RAM для інференсу SLM через платформу Ollama у Docker-контейнерах з метою мінімізації вартості при збереженні прийнятної продуктивності.

---

## 👤 Автор

| | |
|---|---|
| **ПІБ** | Шевчук Максим Вікторович |
| **Група** | ФЕІ-42с |
| **Спеціальність** | 122 — Комп'ютерні науки |
| **Науковий керівник** | ас. Гусак Олег Васильович |
| **Рецензент** | доц. Іван Куньо |
| **Дата захисту** | 2026 р. |

---

## 📌 Загальна інформація

| | |
|---|---|
| **Тип проєкту** | Дослідницька платформа + веб-застосунок |
| **Мова програмування** | Python 3.11, JavaScript (React 18) |
| **Фреймворки / Бібліотеки** | FastAPI, Uvicorn, Docker SDK for Python, psutil, httpx, Vite |
| **Інфраструктура** | Docker Engine 26.1.4, Ollama 0.3.x, cgroups v2 |
| **Кількість тестів** | 22 автоматизованих модулі, 176 конфігурацій |

---

## 🧠 Опис функціоналу

- 🤖 Автоматизоване тестування 11 малих мовних моделей (SLM) у форматі Q4_K_M
- ⚙️ Динамічне обмеження ресурсів контейнера (CPU/RAM) через Docker SDK без перезапуску
- 📊 Вимірювання TPS (Tokens Per Second), TTFT (Time To First Token) та затримки відповіді
- 🧪 Бенчмарки якості: MMLU, GSM8K, HumanEval, ARC/HellaSwag, TruthfulQA
- 💰 Калькулятор вартості $/1M токенів для конфігурацій AWS, Azure, GCP
- 📈 Аналіз OOM-відмов, ефекту квантизації Q4 vs Q8, cold start
- 🌐 React-дашборд із WebSocket-стрімінгом метрик у реальному часі
- 📝 Автоматична агрегація результатів у CSV/JSON

---

## Screenshots

# Dashboard page

<img width="1528" height="846" alt="image" src="https://github.com/user-attachments/assets/f549af11-fc4e-465f-89d7-94f7a999aeef" />

<img width="1626" height="778" alt="image" src="https://github.com/user-attachments/assets/1f9b3f95-9a49-484e-bb79-b61c6e699f7b" />

<img width="1612" height="748" alt="image" src="https://github.com/user-attachments/assets/b7d3b6dd-6676-41aa-aa0a-99d4ddecad9c" />


# Test page

<img width="1818" height="758" alt="image" src="https://github.com/user-attachments/assets/dc78696f-c22e-496f-a839-04503eee4ed8" />

<img width="1543" height="535" alt="image" src="https://github.com/user-attachments/assets/ecb7b189-d16d-4699-bbea-ed874c66b50d" />

<img width="1601" height="580" alt="image" src="https://github.com/user-attachments/assets/a8c652a0-6908-46d5-bb77-e89960ac7223" />

<img width="1562" height="596" alt="image" src="https://github.com/user-attachments/assets/125e8710-2574-47f6-a17a-8a2232162e2e" />


# Compare page

<img width="1512" height="863" alt="image" src="https://github.com/user-attachments/assets/1b3a543f-9cd3-4bad-be59-061c683f3af6" />

# Top models page

<img width="1557" height="872" alt="image" src="https://github.com/user-attachments/assets/c18c14ec-f39c-4d80-987c-dcc7d20623f7" />

<img width="1558" height="842" alt="image" src="https://github.com/user-attachments/assets/94109502-66fe-4294-a2a0-d07bdea51d9d" />

---

## 🧱 Опис основних файлів

| Файл / Модуль | Призначення |
|---|---|
| `backend/benchmarks.py` | Клас OllamaBenchmark: вимірювання TPS, TTFT, серіалізація результатів |
| `backend/docker_manager.py` | Динамічне оновлення cgroups v2 контейнера Ollama через Docker SDK |
| `backend/main.py` | FastAPI-сервер, REST API, WebSocket-ендпоінти |
| `scripts/run_all_tests.py` | Оркестратор матриці 176 конфігурацій із відновленням після збоїв |
| `scripts/tests/performance_test.py` | Базові виміри пропускної здатності та TTFT |
| `scripts/tests/config_matrix_test.py` | Тестування матриці CPU × RAM |
| `scripts/tests/oom_detection_test.py` | Виявлення OOM-відмов при недостатніх конфігураціях |
| `scripts/tests/benchmark_mmlu_test.py` | Бенчмарк MMLU (57 категорій знань) |
| `scripts/tests/benchmark_gsm8k_test.py` | Математичні задачі (GSM8K) |
| `scripts/tests/benchmark_humaneval_test.py` | Генерація коду (HumanEval, pass@1) |
| `scripts/tests/quantization_compare_test.py` | Порівняння Q4_K_M vs Q8_0 |
| `scripts/tests/cloud_cost_calculator.py` | Розрахунок TCO та $/1M токенів |
| `analysis/data-processing/metrics_aggregator.py` | Агрегація JSON-результатів у CSV |
| `monitor/resource_collector.py` | Паралельний збір метрик CPU/RAM через psutil |
| `config/inference_params.yml` | Уніфіковані параметри генерації (seed, temperature, num_ctx) |
| `config/infrastructure.yml` | Цінові профілі AWS, Azure, GCP |
| `docker-compose.yml` | Розгортання Ollama з постійним томом для моделей |
| `frontend/` | React 18 + Vite дашборд |

---

## ▶️ Як запустити проєкт «з нуля»

### 1. Вимоги

| | |
|---|---|
| **OS** | Ubuntu 22.04+ / Debian 12+ (Linux kernel 6.x, cgroups v2) |
| **Docker Engine** | 26.x (`docker --version`) |
| **Python** | 3.11+ з менеджером пакетів uv |
| **Node.js** | 20+ (для фронтенду) |
| **RAM хоста** | мінімум 16 ГБ (для запуску моделей 7B) |
| **Диск** | ~30 ГБ (усі моделі у форматі Q4_K_M) |

### 2. Клонування репозиторію

```bash
git clone https://github.com/Shevik11/diploma.git
cd diploma
```

### 3. Налаштування хостової системи

```bash
# Встановлення режиму performance для ЦП (знижує джитер вимірювань)
sudo bash scripts/setup_host.sh

# Перевірка, що swap вимкнено або налаштовано коректно
sudo sysctl vm.swappiness=0
```

### 4. Запуск Ollama у Docker

```bash
docker compose up -d

# Перевірка, що Ollama доступна
curl http://localhost:11434/api/tags
```

### 5. Завантаження моделей

```bash
# Усі 11 досліджуваних моделей (~15 ГБ загалом)
bash scripts/pull_all_models.sh

# Або окремо, наприклад:
docker exec ollama_inference ollama pull qwen2.5:1.5b
docker exec ollama_inference ollama pull llama3.2:3b
docker exec ollama_inference ollama pull mistral:7b
```

### 6. Встановлення Python-залежностей

```bash
# За допомогою uv (рекомендовано — відтворює точні версії з uv.lock)
pip install uv
uv sync

# Або через pip
pip install -r requirements.txt
```

### 7. Запуск бекенду

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 8. Запуск фронтенду (опційно)

```bash
cd frontend
npm install
npm run dev
# Відкрити http://localhost:5173
```

### 9. Запуск повної матриці тестів

```bash
# Усі конфігурації 
python scripts/run_all_tests.py

# Моніторинг прогресу в окремому терміналі
python scripts/progress_monitor.py

# Або окремий тест, наприклад performance_test для qwen2.5:1.5b
python scripts/tests/performance_test.py --model qwen2.5:1.5b --ram 4 --cpu 2
```

---

## 🔌 API приклади

### Запуск бенчмарку через REST API

**`POST /api/benchmark/run`**

```json
{
  "model": "qwen2.5:1.5b",
  "ram_gb": 4,
  "cpu_cores": 2,
  "num_warmup": 10,
  "num_measure": 20
}
```

**Response:**

```json
{
  "model": "qwen2.5:1.5b",
  "ram_gb": 4,
  "cpu_cores": 2,
  "median_tps": 28.9,
  "stddev_tps": 1.2,
  "median_ttft_ms": 88,
  "peak_ram_mb": 1317,
  "avg_cpu_pct": 76.0,
  "failure_rate": 0.0,
  "completed": true
}
```

### Отримання результатів

| Метод | Опис |
|---|---|
| `GET /api/results` | Повертає список всіх збережених JSON-файлів із результатами. |
| `GET /api/results/{filename}` | Повертає конкретний файл результатів. |

### WebSocket — метрики в реальному часі

**`ws://localhost:8000/ws/metrics`**

Надсилає JSON кожні 2 секунди:

```json
{
  "cpu_percent": 76.3,
  "ram_used_mb": 1284,
  "ram_percent": 64.2,
  "timestamp_ms": 1234567890
}
```

---

## 📊 Досліджувані моделі

| Модель | Параметри | Мін. RAM (Q4_K_M) |
|---|---|---|
| Qwen 2.5 | 0.5B | 2 ГБ |
| Qwen 2.5 | 1.5B | 2 ГБ |
| Qwen 2.5 | 3B | 4 ГБ |
| Qwen 2.5 | 7B | 6 ГБ |
| Qwen 2.5-Coder | 1.5B | 2 ГБ |
| Qwen 2.5-Coder | 7B | 6 ГБ |
| Llama 3.2 | 1B | 2 ГБ |
| Llama 3.2 | 3B | 4 ГБ |
| Gemma 2 | 2B | 2 ГБ |
| Phi-3 Mini | 3.8B | 4 ГБ |
| Mistral | 7B | 6 ГБ |

---

## 🖱️ Інструкція для користувача (дашборд)

### Головна сторінка — вибір моделі та конфігурації ресурсів

- **Dropdown Модель** — вибір однієї з 11 моделей
- **Слайдер CPU** — від 1 до 8 ядер
- **Слайдер RAM** — від 1 до 8 ГБ

### Запуск тесту

- **Кнопка ▶ Запустити бенчмарк** — запускає серію з 20 вимірювань
- Графіки оновлюються в реальному часі через WebSocket

### Результати

- **Таблиця TPS / TTFT** — медіана та стандартне відхилення
- **Теплова карта Ефективність E(m,p,c)** — по всіх конфігураціях
- **Кнопка 📥 Експорт CSV** — вивантаження зведеної таблиці

### Калькулятор вартості

- **Вкладка 💰 Вартість** — розрахунок $/1M токенів для AWS/Azure/GCP

---

## 🔑 Ключові результати

| Сценарій | Рекомендована модель | Конфігурація | TPS | $/1M токенів |
|---|---|---|---|---|
| Чат-бот, прості відповіді | Qwen 2.5 (1.5B) | 2 CPU / 4 ГБ | 28.9 | $0.033 |
| Класифікація тексту | Qwen 2.5 (0.5B) | 2 CPU / 4 ГБ | 31.2 | $0.031 |
| Автодоповнення коду | Qwen 2.5-Coder (1.5B) | 2 CPU / 4 ГБ | 27.8 | $0.035 |
| Генерація коду | Qwen 2.5-Coder (7B) | 8 CPU / 8 ГБ | 5.6 | $1.660 |
| Довгі контексти (>8K) | Mistral 7B | 8 CPU / 8 ГБ | 5.7 | $1.644 |
| Edge / IoT | Llama 3.2 (1B) | 2 CPU / 2 ГБ | 20.6 | $0.047 |

> **Головний висновок:** самостійне хмарне розгортання SLM у 1.5–4.8× дешевше за API-сервіси. Локальне розгортання досягає точки беззбитковості за 10–13 місяців.

---

## 🧪 Відомі проблеми та рішення

| Проблема | Рішення |
|---|---|
| OOM-відмова при запуску моделі | Збільшити `--memory` або перейти на меншу модель (дивись таблицю мін. RAM) |
| Ollama не відповідає на порті 11434 | `docker compose restart` або `docker logs ollama_inference` |
| Низький TPS при 8 ядрах | Нормально для моделей <2B — точка насичення настає на 4 ядрах |
| mem_swappiness не застосовується | Потрібні права root: `sudo sysctl vm.swappiness=0` |
| Тест зупинився посередині матриці | `run_all_tests.py` автоматично продовжить із останньої незавершеної конфігурації |
| Помилка Docker SDK APIError | Перевірити, що поточний користувач у групі docker: `sudo usermod -aG docker $USER` |

---

## 🧾 Використані джерела

- Kaplan et al. (2020). Scaling Laws for Neural Language Models. arXiv:2001.08361
- Frantar et al. (2022). GPTQ: Post-Training Quantization. arXiv:2210.17323
- Kwon et al. (2023). Efficient Memory Management with PagedAttention. arXiv:2309.06180
- Abdin et al. (2024). Phi-3 Technical Report. arXiv:2404.14219
- Qwen Team (2025). Qwen2.5 Technical Report. arXiv:2412.15115
- Ollama — Open-source LLM inference server
- Docker Engine Documentation
- AWS EC2 Pricing / Azure VM Pricing / GCP Compute Engine Pricing (2025–2026)

Повний список із 39 джерел — у розділі «Список використаних джерел» дипломної роботи.

---

## 📁 Репозиторій

🔗 https://github.com/Shevik11/diploma

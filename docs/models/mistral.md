# ⚡ Mistral 7B - Тестування через Ollama

## 📝 Про модель

**Mistral 7B** - це високоефективна мовна модель від французької компанії Mistral AI. Незважаючи на компактний розмір (7B параметрів), вона демонструє продуктивність на рівні значно більших моделей завдяки архітектурі Sliding Window Attention.

### Характеристики
- **Розробник:** Mistral AI
- **Розмір:** 7B параметрів (4.1GB)
- **Контекст:** 8192 токени (вдвічі більше ніж Llama 2)
- **Ліцензія:** Apache 2.0
- **Спеціалізація:** Універсальні задачі з високою швидкістю

### Сильні сторони
✅ Дуже швидка робота  
✅ Чудова якість при малому розмірі  
✅ Великий контекст (8K токенів)  
✅ Відмінна для коду  
✅ Ефективне використання пам'яті

### Слабкі сторони
❌ Менше версій (тільки 7B)  
❌ Менше навченої на спеціалізованих задачах  

## ⚡ Швидкий старт

### Базове використання
```powershell
# Повний тест з Mistral
.\make.ps1 test -ModelName mistral

# Або швидкий тест
.\make.ps1 test-quick -ModelName mistral
```

### Покрокове тестування
```powershell
# 1. Запустити контейнер
.\make.ps1 start

# 2. Завантажити Mistral
.\make.ps1 pull -ModelName mistral

# 3. Швидкий тест
.\make.ps1 test-quick -ModelName mistral

# 4. Статус
.\make.ps1 status
```

## 🎯 Доступні версії

### Mistral 7B (базова)
```powershell
# Стандартна модель
.\make.ps1 test -ModelName mistral

# Або явно
.\make.ps1 test -ModelName mistral:7b
```

**Вимоги:** ~8GB RAM  
**Швидкість:** ~30-40 токенів/сек (CPU)  
**Використання:** Універсальні задачі

### Mistral 7B Instruct (рекомендовано)
```powershell
# Інструкційна версія (краща для задач)
.\make.ps1 test -ModelName mistral:7b-instruct
```

**Особливості:**
- Краще слідує інструкціям
- Оптимізована для задач
- Кращий формат відповідей

### Mistral 7B Q4 (швидка)
```powershell
# 4-bit quantized версія
.\make.ps1 test -ModelName mistral:7b-q4_0
```

**Особливості:**
- Менше RAM (~4GB)
- Швидша робота
- Трохи нижча якість

## 📊 Приклади тестування

### Тест 1: Швидкість відповіді
```powershell
.\make.ps1 test-quick -ModelName mistral
```

**Очікуваний результат:**
- Швидка відповідь (2-3 секунди)
- 40-50 токенів/сек
- Якісна відповідь

### Тест 2: Генерація коду
```powershell
$body = @{
    model = "mistral"
    prompt = "Write a Python function to calculate fibonacci numbers using memoization"
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

**Mistral особливо добре справляється з кодом!**

### Тест 3: Довгий контекст (8K токенів)
```powershell
$body = @{
    model = "mistral"
    prompt = "Analyze this long document: [текст до 8K токенів]"
    stream = $false
    options = @{
        num_ctx = 8192  # Використати весь контекст
    }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

### Тест 4: Структуровані інструкції
```powershell
$body = @{
    model = "mistral:7b-instruct"
    prompt = @"
[INST] You are a helpful assistant. 
Task: Extract key information from this text.
Format: Return as JSON.
Text: John Doe works at Tech Corp as a Senior Developer since 2020.
[/INST]
"@
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

### Тест 5: Streaming відповіді
```powershell
# PowerShell з streaming
$body = @{
    model = "mistral"
    prompt = "Write a short story about AI"
    stream = $true
} | ConvertTo-Json

# Streaming через curl (встановити окремо)
curl -N -X POST http://localhost:11434/api/generate `
    -H "Content-Type: application/json" `
    -d $body
```

## 🔧 Налаштування параметрів

### Оптимальні параметри для Mistral
```powershell
$body = @{
    model = "mistral"
    prompt = "Your prompt here"
    stream = $false
    options = @{
        temperature = 0.7     # Збалансовано
        top_k = 40           # За замовчуванням
        top_p = 0.9          # Nucleus sampling
        num_ctx = 8192       # Повний контекст
        num_predict = 512    # Довгі відповіді
        repeat_penalty = 1.1 # Уникати повторів
    }
} | ConvertTo-Json
```

### Для генерації коду
```powershell
$body = @{
    model = "mistral"
    prompt = "Write a function..."
    options = @{
        temperature = 0.2    # Низька для точності
        top_p = 0.95
        stop = @("}```", "\n\n\n")  # Зупинка після коду
    }
} | ConvertTo-Json
```

### Для творчого письма
```powershell
$body = @{
    model = "mistral"
    prompt = "Write a creative story..."
    options = @{
        temperature = 0.9    # Висока для креативності
        top_k = 50
        top_p = 0.95
    }
} | ConvertTo-Json
```

## 📈 Бенчмарки

### Продуктивність (CPU - 8 cores)
| Метрика | Значення |
|---------|----------|
| Токени/сек | 30-40 |
| Час першого токена | ~1.5 сек |
| RAM (7B) | ~8GB |
| RAM (Q4) | ~4GB |
| Контекст | 8192 токени |

### Порівняння з Llama 2
| Параметр | Mistral 7B | Llama 2 7B |
|----------|------------|------------|
| Швидкість | ⚡⚡⚡⚡⚡ | ⚡⚡⚡ |
| Якість | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Контекст | 8K | 4K |
| RAM | 4.1GB | 3.8GB |
| Код | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |

### Якість відповідей
| Задача | Оцінка | Примітка |
|--------|--------|----------|
| Загальні питання | ⭐⭐⭐⭐⭐ | Відмінно |
| Написання коду | ⭐⭐⭐⭐⭐ | Найкраща |
| Творче письмо | ⭐⭐⭐⭐ | Дуже добре |
| Аналіз тексту | ⭐⭐⭐⭐⭐ | Відмінно |
| Математика | ⭐⭐⭐⭐ | Добре |
| Довгий контекст | ⭐⭐⭐⭐⭐ | Відмінно (8K) |

## 🎓 Рекомендації використання

### Коли використовувати Mistral
✅ Потрібна висока швидкість  
✅ Генерація коду  
✅ Довгий контекст (до 8K)  
✅ Аналіз документів  
✅ Структуровані задачі  
✅ API інтеграція  

### Коли НЕ використовувати
❌ Потрібна модель більше 7B  
❌ Специфічні domain задачі  
❌ Критично важливі медичні дані  

### Порівняння з іншими моделями

**Mistral vs Llama 2:**
- ✅ Mistral швидша на 30-50%
- ✅ Mistral має вдвічі більший контекст
- ✅ Mistral краща для коду
- ➖ Llama 2 має більше версій (13B, 70B)

**Mistral vs Gemma:**
- ✅ Mistral якісніша
- ➖ Gemma швидша (2B версія)
- ✅ Mistral краща для складних задач

**Mistral vs Phi:**
- ✅ Mistral універсальніша
- ➖ Phi швидша та менша
- ✅ Mistral має більший контекст

## 🚀 Продуктивність поради

### 1. Використовуйте Instruct версію для задач
```powershell
.\make.ps1 pull -ModelName mistral:7b-instruct
```

### 2. Quantized версія для швидкості
```powershell
.\make.ps1 pull -ModelName mistral:7b-q4_0
```

### 3. Оптимізуйте batch size
```powershell
$body = @{
    model = "mistral"
    prompt = "Your prompt"
    options = @{
        num_batch = 512  # Більший batch = швидше
    }
} | ConvertTo-Json
```

### 4. Використовуйте весь контекст
```powershell
# Mistral підтримує 8K!
options = @{ num_ctx = 8192 }
```

## 🔍 Діагностика

### Модель працює повільно
```powershell
# 1. Перевірити версію
.\make.ps1 list-models

# 2. Спробувати Q4 версію
.\make.ps1 clean
.\make.ps1 test -ModelName mistral:7b-q4_0

# 3. Перевірити ресурси
docker stats ollama-test
```

### Неточні відповіді
```powershell
# Спробувати Instruct версію
.\make.ps1 pull -ModelName mistral:7b-instruct

# Або зменшити temperature
$body = @{
    options = @{ temperature = 0.3 }
} | ConvertTo-Json
```

### Out of Memory
```powershell
# Використати меншу версію
.\make.ps1 test -ModelName mistral:7b-q4_0

# Зменшити контекст
options = @{ num_ctx = 4096 }
```

## 🎯 Практичні use cases

### 1. Code Assistant
```powershell
$body = @{
    model = "mistral"
    prompt = "Debug this Python code: [ваш код]"
    options = @{ temperature = 0.2 }
} | ConvertTo-Json
```

### 2. Document Analysis
```powershell
$body = @{
    model = "mistral"
    prompt = "Summarize this 5-page document: [текст]"
    options = @{ num_ctx = 8192 }
} | ConvertTo-Json
```

### 3. API Assistant
```powershell
$body = @{
    model = "mistral:7b-instruct"
    prompt = "Generate OpenAPI spec for user management API"
} | ConvertTo-Json
```

## 📚 Додаткові ресурси

- [Mistral AI Website](https://mistral.ai/)
- [Mistral 7B Paper](https://arxiv.org/abs/2310.06825)
- [Ollama Mistral Page](https://ollama.ai/library/mistral)
- [GitHub - Mistral](https://github.com/mistralai)

## 🔄 Повернутись до головної документації

[← Повернутись до README-OLLAMA.md](../../README-OLLAMA.md)

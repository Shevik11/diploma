# 💎 Gemma - Тестування через Ollama

## 📝 Про модель

**Gemma** - це сімейство компактних мовних моделей від Google DeepMind. Створені на основі досліджень Gemini, ці моделі оптимізовані для ефективності та швидкості при збереженні високої якості відповідей.

### Характеристики
- **Розробник:** Google DeepMind
- **Розміри:** 2B (1.4GB), 7B (4.8GB)
- **Контекст:** 8192 токени
- **Ліцензія:** Gemma Terms of Use
- **Спеціалізація:** Швидкі задачі, edge deployment

### Сильні сторони
✅ Дуже компактна (особливо 2B)  
✅ Висока швидкість  
✅ Низьке споживання пам'яті  
✅ Відмінна для edge пристроїв  
✅ Добра якість при малому розмірі

### Слабкі сторони
❌ 2B версія має обмежені можливості  
❌ Менша точність у складних задачах  
❌ Обмежена творчість  

## ⚡ Швидкий старт

### Базове використання
```powershell
# Тест з Gemma 2B (швидка)
.\make.ps1 test -ModelName gemma:2b

# Або з Gemma 7B (якісніша)
.\make.ps1 test -ModelName gemma:7b
```

### Покрокове тестування
```powershell
# 1. Запустити контейнер
.\make.ps1 start

# 2. Завантажити Gemma 2B
.\make.ps1 pull -ModelName gemma:2b

# 3. Швидкий тест
.\make.ps1 test-quick -ModelName gemma:2b

# 4. Статус
.\make.ps1 status
```

## 🎯 Доступні версії

### Gemma 2B (ультра-швидка) ⭐ Рекомендовано для початку
```powershell
# Найменша версія
.\make.ps1 test -ModelName gemma:2b

# Instruct версія
.\make.ps1 test -ModelName gemma:2b-instruct
```

**Вимоги:** ~4GB RAM  
**Швидкість:** ~50-70 токенів/сек (CPU)  
**Використання:** Швидкі прості задачі, прототипування, тестування

### Gemma 7B (збалансована)
```powershell
# Більша версія
.\make.ps1 test -ModelName gemma:7b

# Instruct версія (краща для задач)
.\make.ps1 test -ModelName gemma:7b-instruct
```

**Вимоги:** ~8GB RAM  
**Швидкість:** ~25-35 токенів/сек (CPU)  
**Використання:** Універсальні задачі з балансом швидкості та якості

### Gemma Q4 (економна)
```powershell
# Quantized версії для ще більшої швидкості
.\make.ps1 test -ModelName gemma:2b-q4_0
.\make.ps1 test -ModelName gemma:7b-q4_0
```

**Особливості:**
- Ще менше RAM
- Швидша робота
- Мінімальна втрата якості

## 📊 Приклади тестування

### Тест 1: Ультра-швидка відповідь (2B)
```powershell
.\make.ps1 test-quick -ModelName gemma:2b
```

**Очікуваний результат:**
- Дуже швидка відповідь (1-2 секунди)
- 60-70 токенів/сек
- Проста але коректна відповідь

### Тест 2: Прості питання
```powershell
$body = @{
    model = "gemma:2b"
    prompt = "What is the capital of France? Answer briefly."
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

### Тест 3: Класифікація тексту
```powershell
$body = @{
    model = "gemma:2b-instruct"
    prompt = @"
Classify the sentiment of this text as positive, negative, or neutral:
"I love this product! It works great."

Answer with just one word: positive, negative, or neutral.
"@
    stream = $false
    options = @{
        temperature = 0.1  # Низька для точності
    }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

### Тест 4: Короткі резюме
```powershell
$body = @{
    model = "gemma:7b"
    prompt = "Summarize in 2-3 sentences: [ваш текст тут]"
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

### Тест 5: Екстракція інформації
```powershell
$body = @{
    model = "gemma:2b-instruct"
    prompt = @"
Extract the following information:
Text: "John Doe, age 30, lives in New York"
Format: name, age, city
"@
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

## 🔧 Налаштування параметрів

### Оптимальні параметри для Gemma 2B
```powershell
$body = @{
    model = "gemma:2b"
    prompt = "Your prompt here"
    stream = $false
    options = @{
        temperature = 0.5     # Помірна
        top_k = 40
        top_p = 0.9
        num_ctx = 2048       # Менший контекст для швидкості
        num_predict = 256    # Короткі відповіді
    }
} | ConvertTo-Json
```

### Для Gemma 7B (більша якість)
```powershell
$body = @{
    model = "gemma:7b"
    prompt = "Your prompt here"
    options = @{
        temperature = 0.7
        num_ctx = 8192       # Повний контекст
        num_predict = 512    # Довші відповіді
    }
} | ConvertTo-Json
```

### Для точних відповідей
```powershell
$body = @{
    model = "gemma:2b-instruct"
    prompt = "Calculate: 15 * 23"
    options = @{
        temperature = 0.1    # Дуже низька
        top_k = 10           # Обмежений вибір
    }
} | ConvertTo-Json
```

## 📈 Бенчмарки

### Продуктивність (CPU - 8 cores)
| Версія | Токени/сек | Час першого | RAM | Розмір |
|--------|------------|-------------|-----|---------|
| 2B | 50-70 | ~1 сек | 4GB | 1.4GB |
| 7B | 25-35 | ~2 сек | 8GB | 4.8GB |
| 2B Q4 | 70-90 | ~0.5 сек | 2GB | 0.9GB |

### Порівняння версій
| Параметр | Gemma 2B | Gemma 7B |
|----------|----------|----------|
| Швидкість | ⚡⚡⚡⚡⚡ | ⚡⚡⚡⚡ |
| Якість | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| RAM | 4GB | 8GB |
| Use case | Швидкість | Баланс |

### Якість відповідей
| Задача | Gemma 2B | Gemma 7B | Примітка |
|--------|----------|----------|----------|
| Прості питання | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 2B достатньо |
| Класифікація | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Відмінно для обох |
| Написання коду | ⭐⭐ | ⭐⭐⭐ | 7B краща |
| Творче письмо | ⭐⭐ | ⭐⭐⭐⭐ | Потрібна 7B |
| Аналіз тексту | ⭐⭐⭐ | ⭐⭐⭐⭐ | 7B детальніша |
| Математика | ⭐⭐ | ⭐⭐⭐ | Обидві обмежені |
| Резюмування | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Добре для обох |

## 🎓 Рекомендації використання

### Коли використовувати Gemma 2B
✅ Потрібна максимальна швидкість  
✅ Обмежені ресурси (4GB RAM)  
✅ Прості задачі (QA, класифікація)  
✅ Прототипування  
✅ Edge/mobile пристрої  
✅ Batch processing великих обсягів

### Коли використовувати Gemma 7B
✅ Потрібна краща якість  
✅ Складніші задачі  
✅ Генерація тексту  
✅ Детальний аналіз  
✅ Є 8GB+ RAM  

### Коли НЕ використовувати Gemma
❌ Дуже складні задачі  
❌ Творче письмо (краще Mistral/Llama)  
❌ Складний код (краще Phi/Mistral)  
❌ Потрібна найвища точність  

### Порівняння з іншими моделями

**Gemma 2B vs Phi 2.7B:**
- ✅ Gemma швидша
- ➖ Phi краща для коду
- ✅ Gemma менше RAM
- ➖ Phi розумніша

**Gemma 7B vs Mistral 7B:**
- ➖ Mistral якісніша
- ✅ Gemma трохи швидша
- ➖ Mistral краща для коду
- ✅ Gemma простіша у використанні

**Gemma 2B vs Llama 2 7B:**
- ✅ Gemma значно швидша
- ➖ Llama якісніша
- ✅ Gemma менше RAM (вдвічі)
- ➖ Llama універсальніша

## 🚀 Продуктивність поради

### 1. Починайте з 2B для прототипування
```powershell
.\make.ps1 test -ModelName gemma:2b
```

### 2. Використовуйте Instruct для задач
```powershell
.\make.ps1 pull -ModelName gemma:2b-instruct
```

### 3. Q4 для максимальної швидкості
```powershell
.\make.ps1 pull -ModelName gemma:2b-q4_0
```

### 4. Обмежуйте довжину відповіді
```powershell
$body = @{
    options = @{
        num_predict = 128  # Короткі відповіді = швидше
    }
} | ConvertTo-Json
```

### 5. Batch processing
```powershell
# Gemma 2B чудово підходить для обробки багатьох простих запитів
foreach ($item in $items) {
    $body = @{
        model = "gemma:2b"
        prompt = "Classify: $item"
        stream = $false
    } | ConvertTo-Json
    
    Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
        -Method Post -ContentType "application/json" -Body $body
}
```

## 🔍 Діагностика

### Модель працює повільно
```powershell
# 1. Спробувати 2B версію
.\make.ps1 clean
.\make.ps1 test -ModelName gemma:2b

# 2. Або Q4 версію
.\make.ps1 test -ModelName gemma:2b-q4_0

# 3. Перевірити ресурси
docker stats ollama-test
```

### Неточні відповіді (2B)
```powershell
# Перейти на 7B версію
.\make.ps1 clean
.\make.ps1 test -ModelName gemma:7b-instruct

# Або зменшити temperature
options = @{ temperature = 0.3 }
```

### Надто прості відповіді
```powershell
# Спробувати більш деталізовані промпти
prompt = @"
Think step by step:
1. Analyze the question
2. Consider all aspects
3. Provide detailed answer

Question: [ваше питання]
"@
```

## 🎯 Практичні use cases

### 1. Швидка класифікація
```powershell
$body = @{
    model = "gemma:2b-instruct"
    prompt = "Classify as spam/not-spam: [текст email]"
    options = @{ temperature = 0.1; num_predict = 10 }
} | ConvertTo-Json
```

### 2. Екстракція даних
```powershell
$body = @{
    model = "gemma:2b"
    prompt = "Extract email and phone from: [текст]"
} | ConvertTo-Json
```

### 3. Прості питання-відповіді
```powershell
$body = @{
    model = "gemma:2b"
    prompt = "Q: What is Python? A:"
} | ConvertTo-Json
```

### 4. Резюмування новин
```powershell
$body = @{
    model = "gemma:7b"
    prompt = "Summarize this news article in 3 bullet points: [стаття]"
} | ConvertTo-Json
```

### 5. Sentiment analysis
```powershell
$body = @{
    model = "gemma:2b-instruct"
    prompt = "Rate sentiment 1-5: [текст відгуку]"
    options = @{ temperature = 0.2 }
} | ConvertTo-Json
```

## 💡 Поради для edge deployment

### Docker з обмеженими ресурсами
```powershell
# Обмежити RAM для контейнера
docker run -d `
    --name ollama-edge `
    -p 11434:11434 `
    -v ollama-data:/root/.ollama `
    --memory="4g" `
    --cpus="2" `
    ollama/ollama
```

### Оптимальна конфігурація для Raspberry Pi / Edge
```powershell
# Використати Q4 версію
.\make.ps1 pull -ModelName gemma:2b-q4_0

# З мінімальними параметрами
$body = @{
    model = "gemma:2b-q4_0"
    options = @{
        num_ctx = 1024       # Малий контекст
        num_predict = 64     # Короткі відповіді
        num_thread = 2       # Обмежена кількість потоків
    }
} | ConvertTo-Json
```

## 📚 Додаткові ресурси

- [Google DeepMind Blog - Gemma](https://blog.google/technology/developers/gemma-open-models/)
- [Gemma Technical Report](https://storage.googleapis.com/deepmind-media/gemma/gemma-report.pdf)
- [Ollama Gemma Page](https://ollama.ai/library/gemma)
- [Gemma on Hugging Face](https://huggingface.co/google/gemma-7b)

## 🔄 Повернутись до головної документації

[← Повернутись до README-OLLAMA.md](../../README-OLLAMA.md)

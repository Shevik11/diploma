# 🔬 Phi - Тестування через Ollama

## 📝 Про модель

**Phi** - це сімейство малих але потужних мовних моделей від Microsoft Research. Phi моделі демонструють вражаючу продуктивність у завданнях, пов'язаних з кодом, математикою та логікою, незважаючи на компактний розмір.

### Характеристики
- **Розробник:** Microsoft Research
- **Розміри:** Phi-2 (2.7B параметрів, 1.7GB)
- **Контекст:** 2048 токенів
- **Ліцензія:** MIT
- **Спеціалізація:** Код, математика, логічне мислення

### Сильні сторони
✅ Чудова для коду (Python, JavaScript, тощо)  
✅ Відмінна математика та логіка  
✅ Компактна але розумна  
✅ Швидка робота  
✅ Низьке споживання RAM (~4GB)  
✅ MIT ліцензія (дуже вільна)

### Слабкі сторони
❌ Малий контекст (2K токенів)  
❌ Обмежена творчість  
❌ Гірша для загальних діалогів  
❌ Менше знань про світ

## ⚡ Швидкий старт

### Базове використання
```powershell
# Повний тест з Phi
.\make.ps1 test -ModelName phi

# Або явно вказати версію
.\make.ps1 test -ModelName phi:2.7b
```

### Покрокове тестування
```powershell
# 1. Запустити контейнер
.\make.ps1 start

# 2. Завантажити Phi
.\make.ps1 pull -ModelName phi

# 3. Швидкий тест
.\make.ps1 test-quick -ModelName phi

# 4. Статус
.\make.ps1 status
```

## 🎯 Доступні версії

### Phi-2 (2.7B) - Основна версія
```powershell
# Стандартна модель
.\make.ps1 test -ModelName phi

# Або явно
.\make.ps1 test -ModelName phi:2.7b
```

**Вимоги:** ~4GB RAM  
**Швидкість:** ~40-60 токенів/сек (CPU)  
**Використання:** Код, математика, логіка

### Phi Q4 (швидка)
```powershell
# 4-bit quantized версія
.\make.ps1 test -ModelName phi:2.7b-q4_0
```

**Особливості:**
- Менше RAM (~2GB)
- Швидша робота (~70-80 токенів/сек)
- Мінімальна втрата якості

## 📊 Приклади тестування

### Тест 1: Генерація коду (найсильніша сторона)
```powershell
$body = @{
    model = "phi"
    prompt = @"
Write a Python function to find the longest palindrome in a string.
Include comments and handle edge cases.
"@
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

**Phi дає дуже якісний код!**

### Тест 2: Математичні задачі
```powershell
$body = @{
    model = "phi"
    prompt = @"
Solve step by step:
If a train travels 120 km in 2 hours, then stops for 30 minutes, 
then travels another 180 km in 3 hours, what is the average speed 
for the entire journey?
"@
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

### Тест 3: Логічні загадки
```powershell
$body = @{
    model = "phi"
    prompt = @"
Solve this logic puzzle:
You have 12 balls, one is heavier. You have a balance scale.
What's the minimum number of weighings needed to find the heavy ball?
Explain your reasoning.
"@
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

### Тест 4: Аналіз коду
```powershell
$body = @{
    model = "phi"
    prompt = @"
Analyze this code and suggest improvements:

def calculate(a, b):
    return a + b * 2

print(calculate(5, 3))
"@
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

### Тест 5: Дебагінг коду
```powershell
$body = @{
    model = "phi"
    prompt = @"
Find and fix the bug in this Python code:

def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-3)

print(fibonacci(10))
"@
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

### Тест 6: Алгоритмічні задачі
```powershell
$body = @{
    model = "phi"
    prompt = @"
Write an efficient algorithm to find duplicates in an array.
Analyze time and space complexity.
"@
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:11434/api/generate" `
    -Method Post -ContentType "application/json" -Body $body
```

## 🔧 Налаштування параметрів

### Оптимальні параметри для коду
```powershell
$body = @{
    model = "phi"
    prompt = "Write a function to..."
    stream = $false
    options = @{
        temperature = 0.2    # Низька для точного коду
        top_k = 40
        top_p = 0.9
        num_ctx = 2048      # Повний контекст
        num_predict = 512   # Довгі відповіді для коду
        repeat_penalty = 1.2 # Уникати повторів
    }
} | ConvertTo-Json
```

### Для математики
```powershell
$body = @{
    model = "phi"
    prompt = "Solve: ..."
    options = @{
        temperature = 0.1    # Дуже низька для точності
        top_k = 10
        num_predict = 256
    }
} | ConvertTo-Json
```

### Для пояснень
```powershell
$body = @{
    model = "phi"
    prompt = "Explain how..."
    options = @{
        temperature = 0.5    # Помірна
        num_predict = 400
    }
} | ConvertTo-Json
```

## 📈 Бенчмарки

### Продуктивність (CPU - 8 cores)
| Метрика | Phi 2.7B | Phi Q4 |
|---------|----------|---------|
| Токени/сек | 40-60 | 70-80 |
| Час першого токена | ~1 сек | ~0.5 сек |
| RAM | 4GB | 2GB |
| Розмір | 1.7GB | 1.1GB |
| Контекст | 2048 | 2048 |

### Порівняння з іншими моделями (2-3B розмір)
| Параметр | Phi 2.7B | Gemma 2B |
|----------|----------|----------|
| Швидкість | ⚡⚡⚡⚡ | ⚡⚡⚡⚡⚡ |
| Код | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| Математика | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| Загальне QA | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| RAM | 4GB | 4GB |

### Якість відповідей
| Задача | Оцінка | Примітка |
|--------|--------|----------|
| Генерація коду | ⭐⭐⭐⭐⭐ | Найкраща |
| Дебагінг коду | ⭐⭐⭐⭐⭐ | Відмінно |
| Математика | ⭐⭐⭐⭐⭐ | Відмінно |
| Логіка | ⭐⭐⭐⭐⭐ | Чудово |
| Загальні питання | ⭐⭐⭐ | Задовільно |
| Творче письмо | ⭐⭐ | Слабко |
| Діалог | ⭐⭐⭐ | Прийнятно |
| Аналіз тексту | ⭐⭐⭐ | Добре |

## 🎓 Рекомендації використання

### Коли використовувати Phi
✅ Генерація коду (Python, JS, Java, C++, тощо)  
✅ Code review та дебагінг  
✅ Математичні задачі  
✅ Логічні загадки  
✅ Алгоритмічні питання  
✅ Технічні пояснення  
✅ Навчання програмування  

### Коли НЕ використовувати Phi
❌ Творче письмо  
❌ Загальні діалоги  
❌ Довгий контекст (>2K токенів)  
❌ Емоційний інтелект  
❌ Широкі знання про світ  
❌ Переклади  

### Порівняння з іншими моделями

**Phi vs Mistral (для коду):**
- ✅ Phi спеціалізована на коді
- ➖ Mistral універсальніша
- ✅ Phi менша та швидша
- ➖ Mistral має більший контекст (8K vs 2K)

**Phi vs Gemma 2B:**
- ✅ Phi значно краща для коду
- ✅ Phi краща для математики
- ➖ Gemma швидша
- ➖ Gemma краща для загальних задач

**Phi vs Llama 2:**
- ✅ Phi краща для коду та математики
- ➖ Llama універсальніша
- ✅ Phi менша (2.7B vs 7B)
- ➖ Llama має більший контекст

## 🚀 Продуктивність поради

### 1. Використовуйте для коду
```powershell
# Phi створена саме для цього!
$prompt = "Write a Python function to..."
```

### 2. Чіткі технічні промпти
```powershell
# Добре
$prompt = "Write a function to sort array using quicksort"

# Погано
$prompt = "Can you help me with sorting?"
```

### 3. Q4 для швидкості
```powershell
.\make.ps1 pull -ModelName phi:2.7b-q4_0
```

### 4. Низька temperature для коду
```powershell
options = @{ temperature = 0.2 }
```

### 5. Покрокові інструкції
```powershell
$prompt = @"
Step 1: Define the problem
Step 2: Write the algorithm
Step 3: Implement in Python
Step 4: Test with examples
"@
```

## 🔍 Діагностика

### Phi не розуміє контекст
```powershell
# Phi має малий контекст (2K)
# Скоротіть промпт або використайте іншу модель
.\make.ps1 test -ModelName mistral  # 8K контекст
```

### Код містить помилки
```powershell
# Зменшити temperature
options = @{ temperature = 0.1 }

# Або додати детальніші інструкції
$prompt = "Write a function with error handling and type hints..."
```

### Повільна робота
```powershell
# Використати Q4 версію
.\make.ps1 clean
.\make.ps1 test -ModelName phi:2.7b-q4_0

# Перевірити ресурси
docker stats ollama-test
```

## 🎯 Практичні use cases

### 1. Code Assistant
```powershell
$body = @{
    model = "phi"
    prompt = @"
Create a REST API endpoint in Python Flask:
- POST /users
- Validate email and password
- Store in database
- Return JWT token
"@
    options = @{ temperature = 0.2 }
} | ConvertTo-Json
```

### 2. Code Review
```powershell
$body = @{
    model = "phi"
    prompt = @"
Review this code for:
1. Security issues
2. Performance problems
3. Best practices

[ваш код тут]
"@
} | ConvertTo-Json
```

### 3. Algorithm Explanation
```powershell
$body = @{
    model = "phi"
    prompt = "Explain Dijkstra's algorithm with code example in Python"
} | ConvertTo-Json
```

### 4. Unit Tests Generation
```powershell
$body = @{
    model = "phi"
    prompt = @"
Generate pytest unit tests for this function:

def calculate_discount(price, percentage):
    return price * (1 - percentage / 100)
"@
} | ConvertTo-Json
```

### 5. Refactoring Suggestions
```powershell
$body = @{
    model = "phi"
    prompt = @"
Refactor this code to be more Pythonic and efficient:

[ваш код]
"@
} | ConvertTo-Json
```

### 6. SQL Query Generation
```powershell
$body = @{
    model = "phi"
    prompt = @"
Write SQL query to:
- Find top 10 customers by total purchases
- Join users and orders tables
- Include customer name and total amount
- Sort by amount descending
"@
} | ConvertTo-Json
```

## 💡 Поради для розробників

### Формат промптів для кращих результатів
```powershell
# ✅ Добре - структуровано
$prompt = @"
Task: Write a Python function
Input: List of integers
Output: Sorted list
Requirements:
- Use merge sort
- Handle empty list
- Add type hints
"@

# ❌ Погано - розмито
$prompt = "Sort a list somehow"
```

### Включайте приклади
```powershell
$prompt = @"
Write a function to validate email.

Example:
valid_email("test@example.com") -> True
valid_email("invalid.email") -> False
"@
```

### Вказуйте мову програмування
```powershell
$prompt = "Write a function in Python to..."
# Не просто "Write a function..."
```

## 🔬 Технічні деталі

### Архітектура
- **Базова модель:** Transformer
- **Тренування:** Високоякісні дані (textbooks, код, математика)
- **Оптимізація:** Спеціально для reasoning задач
- **Розмір:** 2.7B параметрів

### Обмеження
- Контекст: 2048 токенів (можна вмістити ~1500 слів)
- Не multimodal (тільки текст)
- Дані до певної дати (перевіряйте актуальність)

## 📚 Додаткові ресурси

- [Microsoft Phi-2 Blog Post](https://www.microsoft.com/en-us/research/blog/phi-2-the-surprising-power-of-small-language-models/)
- [Phi-2 on Hugging Face](https://huggingface.co/microsoft/phi-2)
- [Ollama Phi Page](https://ollama.ai/library/phi)
- [Research Paper](https://arxiv.org/abs/2309.05463)

## 🔄 Повернутись до головної документації

[← Повернутись до README-OLLAMA.md](../../README-OLLAMA.md)

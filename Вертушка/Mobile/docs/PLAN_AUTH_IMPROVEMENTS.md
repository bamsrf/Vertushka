# План: Улучшение аутентификации Вертушка

## Контекст
Расширяем auth-систему: логин по username, сброс пароля через email-код, Google Sign In.

---

## Статус выполнения

### 1. Login по username или email — СДЕЛАНО, НО ЕСТЬ БАГ

**Что сделано:**
- Backend: `UserLogin` схема принимает `login` (новое) и `email` (обратная совместимость)
- Backend: endpoint `/auth/login` определяет по `@` — email или username, ищет case-insensitive
- Mobile: `LoginRequest.login`, store, UI обновлены — поле "Email или имя пользователя"
- Mobile: добавлена кнопка "Забыли пароль?" на экране логина

**БАГ: Internal Server Error при логине**
Причина: `@property` не работает в Pydantic v2 BaseModel — `login_value` не вычисляется.

**Исправление:** заменить `@property` на `@model_validator` в `Backend/app/schemas/user.py`:

```python
class UserLogin(BaseModel):
    """Схема для входа (email или username)"""
    login: str | None = Field(None, min_length=1)
    email: str | None = None  # обратная совместимость
    password: str

    @model_validator(mode='after')
    def set_login_from_email(self) -> 'UserLogin':
        """Если пришёл email (старый формат) — копируем в login"""
        if not self.login and self.email:
            self.login = self.email
        return self
```

И в `Backend/app/api/auth.py` (строка ~224) заменить:
```python
login_value = credentials.login_value.strip().lower()
```
на:
```python
login_value = (credentials.login or "").strip().lower()
```

**Файлы:**
- `Backend/app/schemas/user.py` — UserLogin (строки 21-31)
- `Backend/app/api/auth.py` — login endpoint (строка 224)
- `Mobile/app/(auth)/login.tsx` — UI (готово)
- `Mobile/lib/types.ts` — LoginRequest (готово)
- `Mobile/lib/api.ts` — login method (готово)
- `Mobile/lib/store.ts` — useAuthStore.login (готово)

---

### 2. Сброс пароля через код на почту — БЭКЕНД ГОТОВ, МОБИЛКА НЕТ

**Что сделано (Backend):**
- `Backend/app/models/user.py` — добавлены поля: `reset_code_hash`, `reset_code_expires_at`, `reset_code_attempts`
- `Backend/app/services/email.py` — **СОЗДАН**: отправка через Yandex SMTP (aiosmtplib, HTML-шаблон)
- `Backend/app/schemas/auth.py` — добавлены: `ForgotPasswordRequest`, `VerifyResetCodeRequest`, `ResetPasswordRequest`
- `Backend/app/api/auth.py` — 3 новых endpoint'а:
  - `POST /auth/forgot-password/` — генерирует 6-значный код, хеширует, отправляет email
  - `POST /auth/verify-reset-code/` — проверяет код (3 попытки, 15 мин TTL), выдаёт reset_token
  - `POST /auth/reset-password/` — устанавливает новый пароль, возвращает токены (автологин)
- `Backend/app/config.py` — SMTP настроен на Yandex (smtp.yandex.ru:465)
- `Backend/alembic/versions/20260227_add_password_reset_fields.py` — **СОЗДАНА** миграция

**ВАЖНО: Нужно настроить .env на сервере:**
```env
SMTP_HOST=smtp.yandex.ru
SMTP_PORT=465
SMTP_USER=your-email@yandex.ru
SMTP_PASSWORD=your-app-password
EMAIL_FROM=your-email@yandex.ru
```

**Что нужно сделать (Mobile) — 3 экрана:**

**API методы уже добавлены** в `Mobile/lib/api.ts`:
- `forgotPassword(email)` → POST /auth/forgot-password/
- `verifyResetCode(email, code)` → POST /auth/verify-reset-code/
- `resetPassword(resetToken, newPassword)` → POST /auth/reset-password/

**Создать экраны:**

1. **`Mobile/app/(auth)/forgot-password.tsx`** — ввод email
   - Поле email, кнопка "Отправить код"
   - При успехе → navigate to verify-code с передачей email
   - Дизайн: такой же стиль как login.tsx (градиент лого, форма)

2. **`Mobile/app/(auth)/verify-code.tsx`** — ввод 6-значного кода
   - 6 отдельных полей для цифр (OTP-стиль) ИЛИ одно поле с maxLength=6
   - Таймер обратного отсчёта (15 мин)
   - Кнопка "Отправить повторно" (вызов forgotPassword снова)
   - При успехе → navigate to reset-password с передачей resetToken

3. **`Mobile/app/(auth)/reset-password.tsx`** — ввод нового пароля
   - Два поля: новый пароль + подтверждение (как в register.tsx)
   - При успехе → автологин (сохранение токенов + setUser) → navigate to /(tabs)

**Обновить `Mobile/app/(auth)/_layout.tsx`** — добавить 3 экрана в Stack:
```tsx
<Stack.Screen name="forgot-password" />
<Stack.Screen name="verify-code" />
<Stack.Screen name="reset-password" />
```

---

### 3. Google Sign In — НЕ НАЧАТО

**Backend (доработать `Backend/app/api/auth.py`):**
- Заменить заглушку `/auth/google` (строка 391-403)
- Верифицировать `id_token` через Google API: `https://oauth2.googleapis.com/tokeninfo?id_token=...`
- Извлечь `sub` (google_id), `email`, `name`
- Поиск пользователя по `google_id` → если нет, создать нового с `is_verified=True`
- Модель уже имеет поле `google_id`

**Backend зависимости:** не нужны (используем httpx для проверки токена)

**Mobile:**
- Установить: `npx expo install @react-native-google-signin/google-signin`
- Настроить Google Cloud Console: OAuth Client ID для iOS и Android
- Добавить кнопку "Войти через Google" на экраны login.tsx и register.tsx
- Добавить метод `googleSignIn(idToken)` в `Mobile/lib/api.ts`
- Добавить `loginWithGoogle` в `useAuthStore` в `Mobile/lib/store.ts`

**ВАЖНО: Нужно настроить:**
- Google Cloud Console → OAuth consent screen + credentials
- `GOOGLE_CLIENT_ID` в .env бэкенда
- `app.json` / `app.config.js` — Google Services для Expo

---

### 4. Проверка всего auth флоу — НЕ НАЧАТО

После реализации проверить:
- [ ] Регистрация: email + username + password → токены → переход в приложение
- [ ] Логин по email → работает
- [ ] Логин по username → работает
- [ ] Забыл пароль: email → код на почту → ввод кода → новый пароль → автологин
- [ ] Google Sign In: кнопка → Google OAuth → токены → переход
- [ ] Token refresh: access token истёк → автообновление
- [ ] Rate limiting на всех auth endpoint'ах
- [ ] Edge cases: неверный код, истёкший код, 3+ попытки

---

## Ключевые файлы

**Backend (изменены):**
- `Backend/app/api/auth.py` — login endpoint + 3 reset endpoints
- `Backend/app/schemas/auth.py` — 3 новые схемы
- `Backend/app/schemas/user.py` — UserLogin с login+email полями (НУЖЕН ФИКС)
- `Backend/app/models/user.py` — 3 поля для reset
- `Backend/app/config.py` — SMTP Yandex

**Backend (созданы):**
- `Backend/app/services/email.py` — SMTP email сервис
- `Backend/alembic/versions/20260227_add_password_reset_fields.py` — миграция

**Mobile (изменены):**
- `Mobile/app/(auth)/login.tsx` — login по username + кнопка "Забыли пароль?"
- `Mobile/lib/api.ts` — login + 3 reset метода
- `Mobile/lib/store.ts` — useAuthStore.login(login, password)
- `Mobile/lib/types.ts` — LoginRequest.login

**Mobile (нужно создать):**
- `Mobile/app/(auth)/forgot-password.tsx`
- `Mobile/app/(auth)/verify-code.tsx`
- `Mobile/app/(auth)/reset-password.tsx`

**Mobile (нужно обновить):**
- `Mobile/app/(auth)/_layout.tsx` — добавить 3 экрана в Stack

---

## Безопасность

- Код сброса хешируется в БД (bcrypt), не хранится в открытом виде
- 15 минут TTL, максимум 3 попытки ввода
- Rate limiting на все auth endpoint'ы (3-5/минуту)
- Не раскрываем существование email (always success response)
- reset_token — одноразовый JWT с type="reset", TTL 10 минут
- Google id_token верифицируется через Google API

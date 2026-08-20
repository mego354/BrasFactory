# 🌹 إعداد وتشغيل بوت تليجرام على PythonAnywhere (Telegram + Django)

يعمل البوت بتقنية **Webhook** المباشرة مع تطبيق Django، مما يعني:
- **لا تحتاج** لتشغيل أي أمر إضافي أو نافذة Terminal تعمل بشكل دائم في الخلفية.
- البوت يعمل تلقائياً بمجرد تشغيل موقع Django واستقبال الطلبات عبر مسار:
  `/notifications/telegram/webhook/`

---

## 🚀 خطوات التفعيل على PythonAnywhere (في دقيقة واحدة)

### الخطوة 1: سحب الكود وتحديث قاعدة البيانات
في نافذة **Bash Console** على PythonAnywhere:
```bash
cd ~/BrasFactory    # أو المجلد الخاص بالمشروع
git pull origin main
python manage.py migrate
python manage.py collectstatic --noinput
```

---

### الخطوة 2: إعادة تحميل الموقع (Reload)
1. افتح لوحة تحكم **PythonAnywhere**.
2. اذهب إلى تبويب **Web**.
3. اضغط على الزر الأخضر: **Reload <your-domain>.pythonanywhere.com**.

---

### الخطوة 3: تفعيل الـ Webhook (تُنفذ لمرة واحدة فقط)
افتح المتصفح وضع الرابط التالي واضغط Enter (استبدل الدومين بالدومين الخاص بك):

```text
https://api.telegram.org/bot8932038793:AAGpPDZAiibxbnHo4-gcKcr8957fczyMhCY/setWebhook?url=https://megahd.pythonanywhere.com/notifications/telegram/webhook/
```

> 💡 **ملاحظة:** إذا كان دومين موقعك هو `BrasFactorySystem.pythonanywhere.com` استبدل `megahd.pythonanywhere.com` به.

#### ✅ النتيجة المتوقعة في المتصفح:
```json
{
  "ok": true,
  "result": true,
  "description": "Webhook was set"
}
```

---

## 🔍 كيف تتأكد أن البوت يعمل؟ (Diagnostics)

### 1) فحص حالة الاتصال:
افتح هذا الرابط في المتصفح:
```text
https://api.telegram.org/bot8932038793:AAGpPDZAiibxbnHo4-gcKcr8957fczyMhCY/getWebhookInfo
```
يجب أن يظهر:
- `"url": "https://.../notifications/telegram/webhook/"`
- `"has_custom_certificate": false`
- `"pending_update_count": 0` (أو رقم قليل)

### 2) تجربة البوت:
1. افتح تطبيق تليجرام وابحث عن البوت.
2. أرسل `/start`.
3. سيظهر زر **📱 تسجيل الدخول عبر رقم الهاتف**.
4. عند مشاركة الرقم المسجل لعامل، تظهر قائمة:
   - 📅 إنتاجي اليوم
   - 📊 إنتاج هذا الشهر
   - 📊 إنتاج الشهر الماضي
   - 🌐 فتح لوحة التحكم (رابط مباشر للويب بدون كلمة مرور)
   - 📱 تسجيل إنتاج جديد

---

## 🛠️ استكشاف الأخطاء الشائعة (Troubleshooting)

| المشكلة | السبب المحتمل | الحل |
|---|---|---|
| البوت لا يرد على `/start` | لم يتم ضبط الـ Webhook | قم بتنفيذ **الخطوة 3** في المتصفح |
| البوت يرد `رقم الهاتف غير مسجل` | رقم العامل في تليجرام لا يطابق رقم الهاتف في إدارة العمال | عدّل رقم هاتف العامل من لوحة إدارة العمال ليتطابق مع رقمه |
| خطأ `pending_update_count` يتراكم | مسار الـ Webhook في جانغو يعطي خطأ | تأكد من عمل **Reload** للموقع من تبويب Web وافحص Error Log |

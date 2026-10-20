# SLSU-JGE Integrated System

Flask web application para sa student information at campus office workflows.

## Mga bahagi

- Student at admin accounts, role-based access, at approval ng student registration
- Student profiles at registered student records
- Registrar document requests at announcements
- Guard logs at QR code support
- Maintenance reports
- Dashboard at notifications
- Lokal na JSON storage kapag walang database URL; PostgreSQL storage kapag may `DATABASE_URL`

## Pagpapatakbo sa computer

Sa terminal na nakabukas sa folder na ito:

```powershell
py -m pip install -r requirements.txt
py web.py
```

Kung walang `DATABASE_URL`, lokal na `data.json` ang ginagamit. Para sa Render, gamitin ang start command na `gunicorn web:app`.

## Pag-save ng accounts sa Render

Kailangan ng PostgreSQL database na hiwalay sa web service. Pagkatapos gumawa ng database sa Render:

1. Buksan ang Render Dashboard at piliin ang web service ng SLSU-JGE.
2. Sa **Environment**, magdagdag ng environment variable na `DATABASE_URL`.
3. Ilagay ang **Internal Database URL** ng PostgreSQL service bilang value.
4. I-save ang environment variable at mag-deploy muli.

Sa unang koneksyon, i-iimport ng app ang `data.json` kung kasama ito sa deployment at walang data pa sa database. Pagkatapos, lahat ng pagbabago ay isusulat sa PostgreSQL. Kapag walang `DATABASE_URL`, local JSON file pa rin ang gagamitin.

**Paalala:** Kung Free Postgres database ang pipiliin sa Render, ine-expire ito 30 araw mula nang gawin. Para sa pangmatagalang records, gumamit ng database plan na hindi nag-e-expire o regular na mag-backup at mag-upgrade bago ito mag-expire. Ang accounts na nawala na sa naunang Render filesystem ay hindi awtomatikong maibabalik; kailangan ang kopya/backup ng dating data kung mayroon.

Palitan din ang default admin credentials at secret key bago ilagay sa live na serbisyo.

